"""Piste « residuel » : LightGBM apprend l'ecart entre le proxy et la cible.

Le proxy MVT_TIME - AOBT_3 porte les memes aberrations que la cible (les 768 lignes
invraisemblables du dev sont aberrantes des deux cotes). En preduisant
    cible = proxy_corrige + modele(features)
le modele n'a plus a extrapoler sur ces lignes : il ne corrige qu'un residu de quelques
centaines de secondes. Aucun ecretage n'est applique (il detruirait justement les valeurs
extremes). Quand le proxy est absent, repli sur le modele causal du meme pli.

Usage : python -m src.residual --config configs/tabular_residual.toml --run-id residual-r1 \
            --causal-run causal-r2
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.features import FeatureSpec
from src.reconstruct import base_predictions, causal_fallback_predictions, fit_state, proxy_seconds
from src.report import build_report, write_report
from src.splits import Protocol


def baseline(val_dep: pd.DataFrame, state: dict) -> tuple[np.ndarray, np.ndarray]:
    """Base = calibration du proxy apprise sur le train du pli (constante par défaut) ; `usable` = proxy fini.

    Aucun écrêtage : la cible officielle contient des valeurs extrêmes, les borner coûte du score (D-019).
    """
    return base_predictions(val_dep, state)


def id_bucket(ids, n_buckets: int = 10) -> np.ndarray:
    """Affecte chaque identifiant a un pli deterministe (forme 1D garantie).

    Pige evite : `pd.util.hash_array` applique a un tableau (N, 1) renvoie (N, 1), et la
    comparaison qui suit se diffuse en une matrice N x N — soit des centaines de gigaoctets.
    """
    values = np.asarray(ids)
    if values.ndim != 1:
        raise ValueError(f"identifiants attendus en 1D, recu {values.shape}")
    if not np.isfinite(values).all():
        raise ValueError("identifiants non finis")
    return np.abs(values.astype("int64")) % n_buckets


def _gate_table(train_dep: pd.DataFrame, train_arr, base_tr: np.ndarray, usable_tr: np.ndarray,
                y_tr: np.ndarray, state: dict, cfg: dict) -> dict[str, bool]:
    """Par aéroport : vaut-il mieux `proxy + biais` seul ou le modèle corrigé ?

    Décidé sur un dixième des lignes d'entraînement (clé = identifiant du mouvement), jamais sur
    le mois évalué. À Rome le proxy brut bat le modèle, ce que l'ajustement global masque.
    """
    import lightgbm as lgb

    bucket = id_bucket(train_dep["MVT_ID_mvt"].to_numpy(dtype="float64"))
    fit_mask = (bucket != 0) & usable_tr & np.isfinite(y_tr)
    val_mask = (bucket == 0) & usable_tr & np.isfinite(y_tr)
    if fit_mask.shape != (len(train_dep),) or val_mask.shape != (len(train_dep),):
        raise AssertionError(f"masque de porte de forme inattendue : {fit_mask.shape}")
    if val_mask.sum() < 5_000:
        return {}

    track = cfg.get("track", "hybrid")
    spec = FeatureSpec(track=track, use_runway_actual=bool(cfg.get("features", {}).get("runway_actual", True)),
                       use_dest_pressure=bool(cfg.get("features", {}).get("dest_pressure", False)))
    res_tr = y_tr - base_tr
    spec.fit(train_dep.loc[fit_mask], train_arr, res_tr[fit_mask])
    X_fit = spec.transform(train_dep.loc[fit_mask], train_arr)
    params = {k: v for k, v in cfg.get("lightgbm", {}).items()
              if k not in {"num_boost_round", "early_stopping_round"}}
    params.update({"learning_rate": 0.08, "num_leaves": 63})
    ds = lgb.Dataset(X_fit, res_tr[fit_mask], categorical_feature=spec.categorical_names(), free_raw_data=False)
    booster = lgb.train(params, ds, num_boost_round=int(cfg.get("gate_num_boost_round", 1200)))

    X_val = spec.transform(train_dep.loc[val_mask], train_arr)
    pred_model = base_tr[val_mask] + np.asarray(booster.predict(X_val), dtype="float64")
    frame = pd.DataFrame({"ap": train_dep["ADEP_mvt"].astype("object").to_numpy()[val_mask],
                          "e_base": (base_tr[val_mask] - y_tr[val_mask]) ** 2,
                          "e_model": (pred_model - y_tr[val_mask]) ** 2})
    agg = frame.groupby("ap")[["e_base", "e_model"]].mean()
    return {str(a): bool(row.e_model < row.e_base) for a, row in agg.iterrows()}


def _specialist(train_dep: pd.DataFrame, train_arr, y_tr: np.ndarray, usable_tr: np.ndarray,
                cfg: dict) -> tuple:
    """Modele entraine UNIQUEMENT sur les vols sans fiche reseau (D-025).

    Ces lignes n'ont aucune colonne `_flt` : y appliquer le modele general revient a leur imposer
    des encodages tombes au prior. Le specialiste n'utilise que le cote mouvement, et sa cible est
    transformee en log1p pour que les feuilles puissent atteindre les valeurs extremes (un arbre
    ne peut pas extrapoler au-dela de sa feuille).
    """
    import lightgbm as lgb

    sp_cfg = cfg.get("specialist", {}) or {}
    mask = (~usable_tr) & np.isfinite(y_tr)
    if int(mask.sum()) < int(sp_cfg.get("min_rows", 5_000)):
        raise RuntimeError(f"pas assez de lignes sans reseau pour un specialiste : {int(mask.sum())}")

    spec = FeatureSpec(track="causal", use_runway_actual=False, use_dest_pressure=False)
    y = np.clip(y_tr[mask], 0.0, None)
    cible_kind = str(sp_cfg.get("target", "log1p"))
    if cible_kind == "log1p":
        cible = np.log1p(y)
    elif cible_kind in {"raw", "tweedie"}:
        cible = y
    else:
        raise ValueError(f"specialist.target inconnu : {cible_kind!r} (attendu log1p | raw | tweedie)")
    spec.fit(train_dep.loc[mask], train_arr, cible)
    X = spec.transform(train_dep.loc[mask], train_arr)

    lgb_params = {k: v for k, v in cfg.get("lightgbm", {}).items()}
    if cible_kind == "tweedie":
        # Tweedie predit en secondes : pas de biais de retransformation (log1p + L2 sous-estime).
        lgb_params["objective"] = "tweedie"
        lgb_params.setdefault("tweedie_variance_power", 1.3)
    num_round = int(lgb_params.pop("num_boost_round", 2000))
    stop = int(lgb_params.pop("early_stopping_round", 100))
    params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
    ds = lgb.Dataset(X, cible, categorical_feature=spec.categorical_names(), free_raw_data=False)
    n_val = max(int(len(cible) * 0.1), 500)
    rng = np.random.default_rng(int(lgb_params.get("seed", 7)))
    idx = rng.permutation(len(cible))
    ds_va = lgb.Dataset(X.iloc[idx[:n_val]], cible[idx[:n_val]], reference=ds,
                        categorical_feature=spec.categorical_names())
    booster = lgb.train(params, ds, num_boost_round=num_round, valid_sets=[ds_va],
                        callbacks=[lgb.early_stopping(stop, verbose=False), lgb.log_evaluation(0)])
    return booster, spec, cible_kind


def desaccord_minutes(dep: pd.DataFrame) -> np.ndarray:
    """|off-block réalisé du réseau − off-block planifié| en minutes. Calculable en exploitation (D-033)."""
    from src.prepare import diff_minutes

    e = diff_minutes(dep["AOBT_3_flt"], dep["LOBT_flt"])
    return np.abs(np.where(np.isfinite(e), e, np.nan))


def _tail_model(train_dep: pd.DataFrame, train_arr, y_tr: np.ndarray, base_tr: np.ndarray,
                usable_tr: np.ndarray, cfg: dict) -> tuple:
    """Second modele entraine sur les seules lignes en desaccord planifie/realise (D-033).

    Cible identique au modele principal (l'ecart a la base), donc le remplacement est branche sans
    couture. La region est choisie parce que son plafond mesure depasse le critere D-029 ; les autres
    candidatures sont ecartees par l'arithmetique, pas par un echec.
    """
    import lightgbm as lgb

    tcfg = cfg.get("tail", {}) or {}
    seuil = float(tcfg.get("seuil_desaccord_min", 30))
    masque = usable_tr & (desaccord_minutes(train_dep) >= seuil) & np.isfinite(y_tr)
    if int(masque.sum()) < int(tcfg.get("min_rows", 20_000)):
        raise RuntimeError(f"pas assez de lignes en desaccord pour un specialise : {int(masque.sum())}")

    spec = FeatureSpec(track=cfg.get("track", "hybrid"),
                       use_runway_actual=bool(cfg.get("features", {}).get("runway_actual", True)))
    cible = (y_tr - base_tr)[masque]
    spec.fit(train_dep.loc[masque], train_arr, cible)
    X = spec.transform(train_dep.loc[masque], train_arr)

    lgb_params = {k: v for k, v in cfg.get("lightgbm", {}).items()}
    num_round = int(tcfg.get("num_boost_round", 1200))
    stop = int(tcfg.get("early_stopping_round", 100))
    params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
    for cle in ("min_data_in_leaf", "num_leaves", "learning_rate"):
        if cle in tcfg:
            params[cle] = tcfg[cle]
    ds = lgb.Dataset(X, cible, categorical_feature=spec.categorical_names(), free_raw_data=False)
    n_val = max(int(len(cible) * 0.1), 500)
    rng = np.random.default_rng(int(lgb_params.get("seed", 7)))
    idx = rng.permutation(len(cible))
    ds_va = lgb.Dataset(X.iloc[idx[:n_val]], cible[idx[:n_val]], reference=ds,
                        categorical_feature=spec.categorical_names())
    booster = lgb.train(params, ds, num_boost_round=num_round, valid_sets=[ds_va],
                        callbacks=[lgb.early_stopping(stop, verbose=False), lgb.log_evaluation(0)])
    return booster, spec, seuil


def run_fold(train_dep: pd.DataFrame, val_dep: pd.DataFrame, train_arr: pd.DataFrame | None,
             val_arr: pd.DataFrame | None, state: dict, cfg: dict, causal_run: str,
             val_month: str, paths: dict, gate: dict[str, bool] | None = None,
             specialist: bool = False, tail: bool = False) -> tuple[pd.DataFrame, dict]:
    import lightgbm as lgb

    track = cfg.get("track", "hybrid")
    spec = FeatureSpec(track=track, use_runway_actual=bool(cfg.get("features", {}).get("runway_actual", True)),
                       use_dest_pressure=bool(cfg.get("features", {}).get("dest_pressure", False)))

    y_tr = train_dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    base_tr, usable_tr = baseline(train_dep, state)
    keep = np.isfinite(y_tr) & usable_tr
    spec.fit(train_dep.loc[keep], train_arr, (y_tr - base_tr)[keep])

    lgb_params = {k: v for k, v in cfg.get("lightgbm", {}).items()}
    num_round = int(lgb_params.pop("num_boost_round", 4000))
    stop = int(lgb_params.pop("early_stopping_round", 150))

    X_tr = spec.transform(train_dep.loc[keep], train_arr)
    res_tr = (y_tr - base_tr)[keep]
    params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
    ds_tr = lgb.Dataset(X_tr, res_tr, categorical_feature=spec.categorical_names(), free_raw_data=False)

    n_val = max(int(len(res_tr) * 0.1), 1_000)
    rng = np.random.default_rng(int(lgb_params.get("seed", 7)))
    idx = rng.permutation(len(res_tr))
    ds_va = lgb.Dataset(X_tr.iloc[idx[:n_val]], res_tr[idx[:n_val]], reference=ds_tr,
                        categorical_feature=spec.categorical_names())

    booster = lgb.train(params, ds_tr, num_boost_round=num_round, valid_sets=[ds_va],
                        callbacks=[lgb.early_stopping(stop, verbose=False), lgb.log_evaluation(0)])

    X_va = spec.transform(val_dep, val_arr)
    res_hat = np.asarray(booster.predict(X_va, num_iteration=booster.best_iteration), dtype="float64")

    base_va, usable_va = baseline(val_dep, state)
    fb = causal_fallback_predictions(causal_run, val_month, val_dep, val_arr, paths) if causal_run else None
    if fb is None:
        fb = np.array([state["fallback"].get((a, int(h)), state["glob_mean"]) for a, h in zip(
            val_dep["ADEP_mvt"].astype("object").to_numpy(),
            pd.to_datetime(val_dep["SCHED_TIME_UTC_mvt"], utc=True).dt.hour.to_numpy())], dtype="float64")
        kind = "airport_hour_mean"
    else:
        kind = "causal_model"

    sp_info = {"actif": False, "iterations": 0, "cible": "none", "part_lignes": 0.0}
    if specialist:
        booster_sp, spec_sp, cible_kind = _specialist(train_dep, train_arr, y_tr, usable_tr, cfg)
        masque_sp = ~usable_va
        if masque_sp.any():
            p = np.asarray(booster_sp.predict(spec_sp.transform(val_dep.loc[masque_sp], val_arr),
                                             num_iteration=booster_sp.best_iteration), dtype="float64")
            fb_alt = np.array(fb, dtype="float64", copy=True)
            fb_alt[masque_sp] = np.clip(np.expm1(p) if cible_kind == "log1p" else p, 0.0, None)
            fb = fb_alt
        sp_info = {"actif": True, "iterations": int(booster_sp.best_iteration), "cible": cible_kind,
                   "part_lignes": float(masque_sp.mean())}

    tail_info = {"actif": False, "iterations": 0, "seuil_min": 0.0, "part_lignes": 0.0}
    if tail:
        booster_t, spec_t, seuil_t = _tail_model(train_dep, train_arr, y_tr, base_tr, usable_tr, cfg)
        masque_t = usable_va & (desaccord_minutes(val_dep) >= seuil_t)
        if masque_t.any():
            p = np.asarray(booster_t.predict(spec_t.transform(val_dep.loc[masque_t], val_arr),
                                             num_iteration=booster_t.best_iteration), dtype="float64")
            alt = np.array(res_hat, dtype="float64", copy=True)   # le specialise ne rend que ses propres lignes
            alt[masque_t] = p
            res_hat = alt
        tail_info = {"actif": True, "iterations": int(booster_t.best_iteration), "seuil_min": seuil_t,
                     "part_lignes": float(masque_t.mean())}

    correction = np.ones(len(val_dep), dtype=bool)
    if gate:
        ap_val = val_dep["ADEP_mvt"].astype("object").to_numpy()
        correction = np.array([gate.get(str(a), True) for a in ap_val], dtype=bool)

    pred = np.where(usable_va & correction, base_va + res_hat, np.where(usable_va, base_va, fb))
    pred = np.where(np.isfinite(pred), pred, state["glob_mean"])

    out = pd.DataFrame({"MVT_ID_mvt": val_dep["MVT_ID_mvt"].to_numpy(), "month": val_month,
                        "ADEP_mvt": val_dep["ADEP_mvt"].astype("object").to_numpy(),
                        "pred": pred, "target": val_dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")})
    diag = {"proxy_used_share": float(usable_va.mean()), "fallback_kind": kind,
            "best_iteration": int(booster.best_iteration), "n_train_rows": int(keep.sum()),
            "specialist": sp_info, "tail": tail_info,
            "gate_modelee": {k: bool(v) for k, v in (gate or {}).items()}}
    return out, diag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/tabular_residual.toml")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--folds", type=int, default=0)
    ap.add_argument("--split", default="dev", choices=["dev", "reserved", "witness"])
    ap.add_argument("--causal-run", default="", help="run causal utilise comme repli")
    ap.add_argument("--gate", action="store_true",
                    help="par aéroport, choisit entre proxy+biais seul et proxy+correction (décidé sur l'entraînement)")
    ap.add_argument("--specialist", action="store_true",
                    help="remplace le repli générique par un modèle entraîné sur les seuls vols sans fiche réseau (D-025)")
    ap.add_argument("--tail", action="store_true",
                    help="spécialise la correction sur les vols en désaccord planifié/réalisé d'au moins [tail].seuil_desaccord_min (D-033)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    paths = load_paths()
    protocol = Protocol.from_config(load_config("splits.toml"))
    if args.split == "dev":
        folds = protocol.folds()
    elif args.split == "witness":
        folds = protocol.witness_folds()
    else:
        folds = [("reserve", protocol.reserve_train_months(), m) for m in protocol.reserve_months]
    if args.folds:
        folds = folds[: args.folds]

    start = time.perf_counter()
    frames, diags = [], {}
    for _name, train_months, val_month in folds:
        print(f"[{args.run_id}] pli {val_month} : {len(train_months)} mois d'entrainement", flush=True)
        train_dep = D.dep_for_months(train_months, paths)
        train_arr = D.arr_for_months(train_months, paths)
        val_dep = D.dep_for_months([val_month], paths)
        val_arr = D.arr_for_months([val_month], paths)
        state = fit_state(train_dep, cfg)
        gate = None
        if args.gate:
            base_tr, usable_tr = baseline(train_dep, state)
            gate = _gate_table(train_dep, train_arr, base_tr, usable_tr,
                               train_dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64"), state, cfg)
            print(f"[{args.run_id}] porte : modeles {sorted(a for a, use in gate.items() if use)} | "
                  f"proxy seul {sorted(a for a, use in gate.items() if not use)}", flush=True)
        frame, diag = run_fold(train_dep, val_dep, train_arr, val_arr, state, cfg, args.causal_run,
                               val_month, paths, gate=gate, specialist=args.specialist, tail=args.tail)
        frames.append(frame)
        diags[val_month] = diag

    eval_df = pd.concat(frames, ignore_index=True)
    report = build_report(args.run_id, args.config, cfg.get("track", "hybrid"), "residual", eval_df, protocol,
                          diags, time.perf_counter() - start, split=args.split,
                          extra={"avertissement": "piste de reconstitution : le proxy MVT_TIME - AOBT_3 sert de "
                                                  "base, l'information est posterieure a l'off-block"})
    out = write_report(report, eval_df, Path(paths["write"]["reports"]))
    print(f"ecrit {out}")
    print({"global": report["global"], "by_month": [(r["month"], round(r["rmse"], 1)) for r in report["by_month"]]})


if __name__ == "__main__":
    main()
