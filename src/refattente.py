"""Piste « reference + attente » : la prediction causale augmentee du TRAFIC REELEMENT OBSERVE (D-037).

Fait 4 de la section 2 du README l'a montre : notre congestion est planifiee (horaires publies). Or les
fournitures officielles permettent mieux, sans toucher a la cible :

  * les ARRIVEES portent leur temps de touchee reel (`MVT_TIME_UTC_mvt`, phase ARR) — dans les fichiers
    d'entrainement 2025 comme dans les entrees de finale 2026 ;
  * les AUTRES DEPARTS portent aussi leur decollage reel.

Un vol dont l'ancre est l'horaire programme a donc le droit de savoir ce qui a reellement vole **avant**
cette ancre : c'est de l'historique, pas une anticipation. La discipline est stricte et verifiable :

  * fenetres strictement anterieures a l'ancre (`[ancre - w, ancre)`), jamais centrnees ;
  * le vol evalue lui-meme est exclu des compteurs de depart (son propre decollage reel n'entre dans
    aucune variable) ;
  * la cible du vol evalue, et toute colonne posterieure a son pushback, restent exclues — les garde-fous
    de la piste causale s'appliquent tels quels, puisqu'on part de ses variables.

Usage :
    PYTHONPATH=. .venv/bin/python -m src.refattente --config configs/tabular_causal.toml --run-id refattente-r1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.features import FeatureSpec
from src.metrics import grouped_report, out_of_domain, summary
from src.prepare import epoch
from src.splits import Protocol, fingerprint, save_fingerprint

FENETRES_MIN = (15, 45, 90)
PLAFOND_MIN = 360.0


def _index_par_aeroport(aps: np.ndarray, e: np.ndarray) -> dict[str, np.ndarray]:
    """Pour chaque aeroport, les instants realises tries (NaN exclus)."""
    ok = np.isfinite(e)
    df = pd.DataFrame({"ap": aps[ok], "e": e[ok]}).sort_values(["ap", "e"])
    return {str(a): g["e"].to_numpy("float64") for a, g in df.groupby("ap", sort=False)}


def _fenetres(ancre: np.ndarray, ap: np.ndarray, src: dict[str, np.ndarray], prefix: str,
              self_epoch: np.ndarray | None = None) -> pd.DataFrame:
    """Comptages dans [ancre - w, ancre) et delai depuis le dernier evenement realise."""
    n = len(ancre)
    out = np.zeros((n, len(FENETRES_MIN)), dtype="float32")
    idle = np.full(n, np.nan, dtype="float64")
    for a, e in src.items():
        rows = np.flatnonzero(ap == a)
        if not len(rows):
            continue
        t = ancre[rows]
        ok = np.isfinite(t)
        r_ok, t_ok = rows[ok], t[ok]
        hi = np.searchsorted(e, t_ok, side="left")                       # strictement avant l'ancre
        for k, w in enumerate(FENETRES_MIN):
            lo = np.searchsorted(e, t_ok - w * 60.0, side="left")
            c = (hi - lo).astype("float32")
            if self_epoch is not None:
                se = self_epoch[r_ok]
                dans = np.isfinite(se) & (se < t_ok) & (se >= t_ok - w * 60.0)
                c = c - dans.astype("float32")                            # jamais son propre decollage
            out[r_ok, k] = c
        prev = np.where(hi > 0, e[np.clip(hi - 1, 0, len(e) - 1)], np.nan)
        if self_epoch is not None:                                       # si l'unique evenement etait lui-meme
            se = self_epoch[r_ok]
            seul = (hi == 1) & np.isfinite(se) & (se < t_ok)
            prev = np.where(seul, np.nan, prev)
        idle[r_ok] = (t_ok - prev) / 60.0
    df = pd.DataFrame(out, columns=[f"obs_{prefix}_{w}" for w in FENETRES_MIN], index=range(n))
    df[f"obs_{prefix}_idle_min"] = np.minimum(idle, PLAFOND_MIN).astype("float32")
    return df


def observed_frame(dep: pd.DataFrame, arr_period: pd.DataFrame | None, dep_period: pd.DataFrame) -> pd.DataFrame:
    ancre = epoch(dep["SCHED_TIME_UTC_mvt"])
    ap = dep["ADEP_mvt"].astype("object").to_numpy()
    morceaux = []
    if arr_period is not None and len(arr_period):
        src = _index_par_aeroport(arr_period["ADES_mvt"].astype("object").to_numpy(),
                                  epoch(arr_period["MVT_TIME_UTC_mvt"]))
        morceaux.append(_fenetres(ancre, ap, src, "arr"))
    src_d = _index_par_aeroport(dep_period["ADEP_mvt"].astype("object").to_numpy(),
                                epoch(dep_period["MVT_TIME_UTC_mvt"]))
    morceaux.append(_fenetres(ancre, ap, src_d, "dep", self_epoch=epoch(dep["MVT_TIME_UTC_mvt"])))
    obs = pd.concat(morceaux, axis=1)
    if {"obs_dep_45", "obs_arr_45"} <= set(obs.columns):
        with np.errstate(invalid="ignore", divide="ignore"):
            obs["obs_ratio_dep_arr_45"] = (obs["obs_dep_45"] / np.maximum(obs["obs_arr_45"], 1.0)).astype("float32")
    return obs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/tabular_causal.toml")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--folds", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    paths = load_paths()
    protocol = Protocol.from_config(load_config("splits.toml"))
    lgb_params = dict(cfg.get("lightgbm", {}))
    folds = protocol.folds()
    if args.folds:
        folds = folds[: args.folds]

    start = time.perf_counter()
    art = Path(paths["write"]["artifacts"]) / args.run_id
    art.mkdir(parents=True, exist_ok=True)
    frames, fit_state = [], {}
    for name, train_months, val_month in folds:
        t0 = time.perf_counter()
        train_dep, train_arr = D.dep_for_months(train_months, paths), D.arr_for_months(train_months, paths)
        val_dep, val_arr = D.dep_for_months([val_month], paths), D.arr_for_months([val_month], paths)
        y_tr = train_dep["TAXITIME_SEC_mvt"].to_numpy("float64")
        spec = FeatureSpec(track="causal", epoch_seconds=True).fit(train_dep, train_arr, y_tr)
        X_tr = pd.concat([spec.transform(train_dep, train_arr), observed_frame(train_dep, train_arr, train_dep)], axis=1)
        X_va = pd.concat([spec.transform(val_dep, val_arr), observed_frame(val_dep, val_arr, val_dep)], axis=1)
        keep = np.isfinite(y_tr)
        params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
        ds_tr = lgb.Dataset(X_tr.loc[keep], y_tr[keep], categorical_feature=spec.categorical_names(), free_raw_data=False)
        ds_va = lgb.Dataset(X_va, val_dep["TAXITIME_SEC_mvt"].to_numpy("float64"), reference=ds_tr)
        model = lgb.train(params, ds_tr, num_boost_round=int(lgb_params.get("num_boost_round", 4000)),
                          valid_sets=[ds_va],
                          callbacks=[lgb.early_stopping(int(lgb_params.get("early_stopping_round", 150)), verbose=False),
                                     lgb.log_evaluation(0)])
        pred = model.predict(X_va, num_iteration=model.best_iteration)
        y_va = val_dep["TAXITIME_SEC_mvt"].to_numpy("float64")
        fold_dir = art / f"fold-{val_month}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        model.save_model(str(fold_dir / "model.txt"))
        (fold_dir / "spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")
        fit_state[val_month] = {"best_iteration": int(model.best_iteration), "n_features": int(X_tr.shape[1]),
                                "runtime_s": round(time.perf_counter() - t0, 1), **summary(pred, y_va)}
        frames.append(pd.DataFrame({"MVT_ID_mvt": val_dep["MVT_ID_mvt"].to_numpy(), "month": val_month,
                                    "ADEP_mvt": val_dep["ADEP_mvt"].astype("object").to_numpy(),
                                    "pred": np.asarray(pred, dtype="float64"), "target": y_va}))
        print(f"[{args.run_id}] {val_month} : RMSE {summary(pred, y_va)['rmse']:.1f} s", flush=True)

    ev = pd.concat(frames, ignore_index=True)
    rapport = {
        "run_id": args.run_id, "config": args.config, "track": "causal+trafic_observe",
        "discipline": {"fenetres_min": list(FENETRES_MIN), "ancre": "SCHED_TIME_UTC_mvt",
                       "auto_exclusion_depart": True, "plafond_idle_min": PLAFOND_MIN},
        "protocol": {"dev_val_months": list(protocol.dev_val_months), "reserve_months": list(protocol.reserve_months)},
        "global": {**summary(ev.pred.to_numpy(), ev.target.to_numpy()), "n_rows": int(len(ev))},
        "by_month": grouped_report(ev, by=("month",)), "by_airport": grouped_report(ev, by=("ADEP_mvt",)),
        "out_of_domain": out_of_domain(ev.pred.to_numpy()), "folds": fit_state,
        "runtime_s": round(time.perf_counter() - start, 1),
    }
    reports = Path(paths["write"]["reports"])
    (reports / f"{args.run_id}.json").write_text(json.dumps(rapport, indent=1), encoding="utf-8")
    ev.to_parquet(reports / f"{args.run_id}.eval.parquet", index=False)
    save_fingerprint(fingerprint(protocol, paths["_official"]), reports / f"{args.run_id}.fingerprint.json")
    print(json.dumps({"run_id": args.run_id, "global": rapport["global"],
                      "par_mois": [(r["month"], round(r["rmse"], 1)) for r in rapport["by_month"]]}, indent=1))


if __name__ == "__main__":
    main()
