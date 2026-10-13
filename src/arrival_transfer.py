"""Mesure du transfert local -> periode notee, sur les ARRIVEES reellement etiquetees (D-036).

Les fichiers officiels d'evaluation livrent les temps de roulage des ARRIVEES pour les mois notes
(janvier et juillet 2026 dans `ranking.parquet`, quatre mois dans `final_ranking.parquet`). Aucune
etiquette de DEPART n'existe en 2026 : les departements restent donc sans verite locale. Les arrivees,
elles, en portent une — et suffisent a repondre a la seule question que nos chiffres locaux ne peuvent
pas trancher : **un score mesure sur 2025 se reporte-t-il tel quel sur 2026 ?**

Dispositif (critere ecrit avant execution, cf. DECISIONS.md D-036) :
  - une seule recette, discipline identique a la piste prediction : calendrier, categories, champs de
    planification, encodages par cible appris sur l'entrainement seul, congestion PLANIFIEE ;
  - entrainement STRICTEMENT identique dans les deux mesures : mois 2025 hors janvier, juillet (les deux
    mois notes) et hors reserve interne (novembre, decembre) ;
  - mesure A (locale) : RMSE sur janvier + juillet **2025** ;
  - mesure B (periode notee) : RMSE sur janvier + juillet **2026**, verites fournies par l'organisateur ;
  - facteur de transfert = B / A, avec un predicteur de reference (moyenne par aéroport lisse) pour
    voir si le facteur depend ou non de la recette.

Aucun reglage n'est fait sur 2026 : c'est une mesure unique, lue une fois.

Usage : PYTHONPATH=. .venv/bin/python -m src.arrival_transfer
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src import data as D
from src.config import load_config, load_paths, training_file
from src.features import SHRINK_K
from src.metrics import summary
from src.prepare import diff_minutes, epoch, slot
from src.splits import Protocol

ARR_COLS = ["ADES_mvt", "MVT_TIME_UTC_mvt", "SCHED_TIME_UTC_mvt", "TAXITIME_SEC_mvt",
            "AIRCRAFT_TYPE_mvt", "RUNWAY_mvt", "STAND_mvt", "PHASE_mvt", "EOBT_1_flt", "IOBT_flt",
            "LOBT_flt", "WK_TBL_CAT_flt", "MARKET_SEGMENT_flt", "FLIGHT_RULE_flt", "FLIGHT_TYPE_flt",
            "AIRCRAFT_OPERATOR_flt"]
CATS = ["ADES_mvt", "AIRCRAFT_TYPE_mvt", "WK_TBL_CAT_flt", "MARKET_SEGMENT_flt", "FLIGHT_RULE_flt",
        "FLIGHT_TYPE_flt"]
TE_KEYS = {"te_ap_hour": ["ADES_mvt", "hour"], "te_ap_dow_slot": ["ADES_mvt", "dow", "slot_group"],
           "te_operator": ["AIRCRAFT_OPERATOR_flt"]}
EVAL_LOCAL = ("2025-01", "2025-07")
EVAL_NOTEE = ("2026-01", "2026-07")


def _load_arr(path: Path, tag: str, tmp_dir: Path) -> pd.DataFrame:
    """Arrivees avec les colonnes de planification (la projection ARR standard ne les contient pas)."""
    from src.data import _cache_key                                    # meme convention de cache
    out = tmp_dir / f"{tag}-{_cache_key(path, 'arrx')}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    have = set(pq.ParquetFile(path).schema_arrow.names)
    cols = [c for c in ARR_COLS if c in have]
    df = pq.read_table(path, columns=cols)
    if "PHASE_mvt" in cols:
        df = df.filter(pc.equal(df["PHASE_mvt"], "ARR")).drop(["PHASE_mvt"])
    df = df.to_pandas()
    for c in ("ADES_mvt", "AIRCRAFT_TYPE_mvt", "WK_TBL_CAT_flt", "MARKET_SEGMENT_flt",
              "FLIGHT_RULE_flt", "FLIGHT_TYPE_flt", "AIRCRAFT_OPERATOR_flt"):
        if c in df.columns:
            df[c] = df[c].astype("object")
    for c in ("MVT_TIME_UTC_mvt", "SCHED_TIME_UTC_mvt", "EOBT_1_flt", "IOBT_flt", "LOBT_flt"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601", errors="coerce")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


class ArrivalSpec:
    """Encodages par cible + capacite, ajustes sur l'entrainement uniquement (discipline de la piste prediction)."""

    def __init__(self) -> None:
        self.cats: dict[str, list[str]] = {}
        self.enc: dict[str, tuple[dict, float]] = {}
        self.capacity: dict[str, float] = {}

    def fit(self, arr_train: pd.DataFrame, y: np.ndarray) -> "ArrivalSpec":
        keep = np.isfinite(y) & (y > 60) & (y < 7200)
        a = arr_train.loc[keep].copy()
        yy = np.asarray(y, dtype="float64")[keep]
        sched = pd.to_datetime(a["SCHED_TIME_UTC_mvt"], utc=True)
        a["hour"] = sched.dt.hour.astype("int32")
        a["dow"] = sched.dt.dayofweek.astype("int32")
        a["slot_group"] = (sched.dt.hour // 4).astype("int32")
        for c in CATS:
            if c in a.columns:
                self.cats[c] = sorted(map(str, a[c].dropna().astype("object").unique()))
        for name, keys in TE_KEYS.items():
            frame = a[keys].copy()
            for k in keys:
                frame[k] = frame[k].astype("object").fillna("__na__") if not pd.api.types.is_integer_dtype(frame[k]) else frame[k]
            grp = frame.assign(_y=yy).groupby(keys, dropna=False)["_y"].agg(["mean", "count"])
            parent = float(yy.mean())
            sm = (grp["mean"] * grp["count"] + parent * SHRINK_K) / (grp["count"] + SHRINK_K)
            self.enc[name] = ({(k if len(keys) > 1 else k[0]): float(v) for k, v in sm.items()}, parent)
        e = epoch(a["MVT_TIME_UTC_mvt"])
        ok = np.isfinite(e)
        cnt = (pd.DataFrame({"ap": a["ADES_mvt"].astype("object").to_numpy()[ok], "slot": slot(e[ok])})
               .groupby(["ap", "slot"]).size())
        self.capacity = {str(ap): float(max(v, 1.0)) for ap, v in cnt.groupby(level=0).quantile(0.95).items()}
        return self

    def transform(self, arr: pd.DataFrame, dep_period: pd.DataFrame) -> pd.DataFrame:
        sched = pd.to_datetime(arr["SCHED_TIME_UTC_mvt"], utc=True)
        hour = sched.dt.hour.astype("int32")
        dow = sched.dt.dayofweek.astype("int32")
        X = pd.DataFrame(index=range(len(arr)), dtype="float32")
        X["hour"] = hour.to_numpy()
        X["dow"] = dow.to_numpy()
        X["month"] = sched.dt.month.to_numpy()
        X["dom"] = sched.dt.day.to_numpy()
        X["is_weekend"] = (dow.to_numpy() >= 5).astype("int8")
        X["hour_sin"] = np.sin(2 * np.pi * hour / 24).to_numpy(dtype="float32")
        X["hour_cos"] = np.cos(2 * np.pi * hour / 24).to_numpy(dtype="float32")
        for c in CATS:
            if c in arr.columns:
                idx = {v: i for i, v in enumerate(self.cats.get(c, []))}
                X[f"c_{c}"] = arr[c].astype("object").map(idx).fillna(-1).to_numpy(dtype="int32")
        for out, col in (("d_eobt_min", "EOBT_1_flt"), ("d_iobt_min", "IOBT_flt"), ("d_lobt_min", "LOBT_flt")):
            v = diff_minutes(arr[col], arr["SCHED_TIME_UTC_mvt"])
            X[out] = np.clip(np.where(np.isfinite(v), v, np.nan), -180.0, 900.0).astype("float32")
            X[f"miss_{col}"] = (~np.isfinite(v)).astype("int8")
        tmp = arr.copy()
        tmp["hour"] = hour.to_numpy()
        tmp["dow"] = dow.to_numpy()
        tmp["slot_group"] = (hour // 4).to_numpy()
        for name, keys in TE_KEYS.items():
            table, parent = self.enc.get(name, ({}, float("nan")))
            frame = tmp[keys].copy()
            for k in keys:
                if not pd.api.types.is_integer_dtype(frame[k]):
                    frame[k] = frame[k].astype("object").fillna("__na__")
            if len(keys) == 1:
                mapped = frame[keys[0]].map(table)
            else:
                mapped = pd.Series([table.get(tuple(k), np.nan) for k in frame.to_numpy()], index=frame.index)
            X[name] = mapped.fillna(parent).to_numpy(dtype="float32")
        ap = arr["ADES_mvt"].astype("object").to_numpy()
        self_slot = slot(epoch(sched))
        counts = (pd.DataFrame({"ap": ap, "slot": self_slot}).groupby(["ap", "slot"]).size()
                  .rename("n").reset_index())
        key = pd.DataFrame({"ap": ap, "slot": self_slot})
        now = None
        for lag, tag in ((-1, "prev"), (0, "now"), (1, "next")):
            merged = (pd.DataFrame({"ap": ap, "slot": self_slot + lag})
                      .merge(counts, on=["ap", "slot"], how="left")["n"].fillna(0.0).to_numpy(dtype="float32"))
            X[f"arr_{tag}_sched"] = merged
            if tag == "now":
                now = merged
        cap = np.array([self.capacity.get(str(a), np.nan) for a in ap], dtype="float32")
        with np.errstate(invalid="ignore", divide="ignore"):
            X["arr_load_ratio"] = np.where(cap > 0, now / cap, np.nan).astype("float32")
        if len(dep_period):
            de = epoch(dep_period["SCHED_TIME_UTC_mvt"])
            dok = np.isfinite(de)
            dcnt = (pd.DataFrame({"ap": dep_period["ADEP_mvt"].astype("object").to_numpy()[dok],
                                  "slot": slot(de[dok])}).groupby(["ap", "slot"]).size().rename("n").reset_index())
            X["dep_now_sched"] = (key.merge(dcnt, on=["ap", "slot"], how="left")["n"].fillna(0.0)
                                  .to_numpy(dtype="float32"))
        return X


def _train_months() -> list[str]:
    prot = Protocol.from_config(load_config("splits.toml"))
    return [m for m in prot.all_months if m not in ("2025-01", "2025-07") and m not in prot.reserve_months]


def _arr_2025(month: str, tmp_dir: Path) -> pd.DataFrame:
    return _load_arr(training_file(load_paths()["_official"], month), f"arrx-{month}", tmp_dir).assign(month=month)


def main() -> None:
    t0 = time.perf_counter()
    paths = load_paths()
    tmp_dir = Path(paths["write"]["tmp"])
    train_months = _train_months()
    arr_tr = pd.concat([_arr_2025(m, tmp_dir) for m in train_months], ignore_index=True)
    dep_tr = D.dep_for_months(train_months, paths, tmp_dir)
    y_tr = pd.to_numeric(arr_tr["TAXITIME_SEC_mvt"], errors="coerce").to_numpy("float64")

    spec = ArrivalSpec().fit(arr_tr, y_tr)
    X_tr = spec.transform(arr_tr, dep_tr)
    keep = np.isfinite(y_tr) & (y_tr > 60) & (y_tr < 7200)
    cfg = load_config("tabular_causal.toml").get("lightgbm", {})
    params = {k: v for k, v in cfg.items() if k not in {"num_boost_round", "early_stopping_round"}}
    cats = [f"c_{c}" for c in spec.cats]

    # --- evaluation locale : janvier + juillet 2025 (jamais vus a l'entrainement)
    arr_a = pd.concat([_arr_2025(m, tmp_dir) for m in EVAL_LOCAL], ignore_index=True)
    dep_a = D.dep_for_months(list(EVAL_LOCAL), paths, tmp_dir)
    X_a = spec.transform(arr_a, dep_a)
    y_a = pd.to_numeric(arr_a["TAXITIME_SEC_mvt"], errors="coerce").to_numpy("float64")

    ds_tr = lgb.Dataset(X_tr.loc[keep], y_tr[keep], categorical_feature=cats, free_raw_data=False)
    ds_va = lgb.Dataset(X_a, y_a, reference=ds_tr)
    model = lgb.train(params, ds_tr, num_boost_round=int(cfg.get("num_boost_round", 4000)), valid_sets=[ds_va],
                      callbacks=[lgb.early_stopping(int(cfg.get("early_stopping_round", 150)), verbose=False),
                                 lgb.log_evaluation(0)])

    def evaluer(X, y, mois, ap) -> dict:
        p = model.predict(X, num_iteration=model.best_iteration)
        s = summary(p, y)
        df = pd.DataFrame({"month": mois, "ap": ap, "err2": (p - y) ** 2})
        par_mois = {m: float(np.sqrt(df[df.month == m].err2.mean())) for m in sorted(set(mois))}
        return {"rmse": s["rmse"], "n_rows": int(len(y)), "par_mois": par_mois,
                "par_aeroport": {str(a): round(float(np.sqrt(g.err2.mean())), 1) for a, g in df.groupby("ap")}}

    local = evaluer(X_a, y_a, arr_a["month"].astype("object").to_numpy(),
                    arr_a["ADES_mvt"].astype("object").to_numpy())

    # --- evaluation sur la periode notee : janvier + juillet 2026, verites de l'organisateur
    off_arr = _load_arr(paths["_official"] / paths["data"]["final_inputs"], "arrx-final", tmp_dir)
    off_arr = off_arr.assign(m=pd.to_datetime(off_arr["MVT_TIME_UTC_mvt"], utc=True).dt.strftime("%Y-%m"))
    off_arr = off_arr[off_arr.m.isin(EVAL_NOTEE)].reset_index(drop=True)
    off_dep, _ = D.final_frames(paths, tmp_dir)
    off_dep = off_dep.assign(m=pd.to_datetime(off_dep["MVT_TIME_UTC_mvt"], utc=True).dt.strftime("%Y-%m"))
    X_b = spec.transform(off_arr, off_dep[off_dep.m.isin(EVAL_NOTEE)])
    y_b = pd.to_numeric(off_arr["TAXITIME_SEC_mvt"], errors="coerce").to_numpy("float64")
    note = evaluer(X_b, y_b, off_arr.m.astype("object").to_numpy(), off_arr["ADES_mvt"].astype("object").to_numpy())

    # --- predicteur de reference (moyenne par aéroport lisse), memes deux evaluations
    glob = float(np.nanmean(y_tr[keep]))
    tab = pd.Series(y_tr[keep]).groupby(arr_tr.loc[keep, "ADES_mvt"].astype("object")).agg(["mean", "count"])
    lisse = {a: (r["mean"] * r["count"] + glob * 50.0) / (r["count"] + 50.0) for a, r in tab.iterrows()}
    ref_a = np.array([lisse.get(a, glob) for a in arr_a["ADES_mvt"].astype("object")])
    ref_b = np.array([lisse.get(a, glob) for a in off_arr["ADES_mvt"].astype("object")])
    ref_local = summary(ref_a, y_a)["rmse"]
    ref_note = summary(ref_b, y_b)["rmse"]

    rapport = {
        "run_id": "arrival-transfer",
        "dispositif": {"entrainement": train_months, "local": list(EVAL_LOCAL), "periode_notee": list(EVAL_NOTEE),
                       "note": "aucun reglage sur 2026 ; entrainement identique dans les deux mesures"},
        "modele": {"best_iteration": int(model.best_iteration), "n_features": int(X_tr.shape[1]),
                   "lignes_entrainement": int(keep.sum())},
        "local_2025": local, "periode_notee_2026": note,
        "facteur_transfert_modele": round(note["rmse"] / local["rmse"], 4),
        "reference_moyenne_aeroport": {"local_2025": round(ref_local, 1), "periode_notee_2026": round(ref_note, 1),
                                       "facteur": round(ref_note / ref_local, 4)},
        "runtime_s": round(time.perf_counter() - t0, 1),
    }
    out = Path(paths["write"]["reports"])
    (out / "ARRIVAL_TRANSFER.json").write_text(json.dumps(rapport, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: rapport[k] for k in ("local_2025", "periode_notee_2026", "facteur_transfert_modele",
                                              "reference_moyenne_aeroport")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
