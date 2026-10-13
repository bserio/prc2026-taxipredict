"""Piste « hybrid » : reconstitution du taxi-out, pas une prévision.

Identité officielle (départ) : TAXITIME_SEC_mvt = MVT_TIME_UTC_mvt - BLOCK_TIME_UTC_mvt.
BLOCK_TIME étant masqué dans les entrées de finale, il est estimé par AOBT_3_flt ;
le résidu (cible - proxy) est corrigé du biais moyen par aéroport calé sur le train du
pli, puis la prédiction est écrêtée aux bornes par aéroport calibrées sur ce même train.
Quand le proxy est absent ou aberrant, repli sur une moyenne lissée aéroport×heure du train.

Usage : python -m src.reconstruct --config configs/tabular_hybrid.toml --run-id hybrid-r1
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.prepare import diff_minutes
from src.report import build_report, write_report
from src.splits import Protocol


def proxy_seconds(dep: pd.DataFrame) -> np.ndarray:
    return (diff_minutes(dep["MVT_TIME_UTC_mvt"], dep["AOBT_3_flt"]) * 60.0).astype("float64")


# ---------------------------------------------------------------------- calibration de la base
# Le proxy est une MESURE BRUITÉE du off-block : régresser la cible dessus donne une pente de
# 0,69 en global (D-031), pas 1. Décaler le proxy d'une constante laisse donc une erreur
# systématique qui croît avec l'écart — précisément la queue qu'il reste à reconstituer.


def _droite(x: np.ndarray, y: np.ndarray) -> list[float]:
    X = np.vstack([np.ones_like(x), x]).T
    w = np.linalg.solve(X.T @ X + 1e-6 * np.eye(2), X.T @ y)
    return [float(w[0]), float(w[1])]


def fit_calibration(px: np.ndarray, y: np.ndarray, ap: np.ndarray, mode: str,
                    min_rows: int = 5_000, n_knots: int = 200) -> dict:
    """Apprend `cible ~ proxy` par aéroport, avec repli hiérarchique explicite.

    aéroport (si assez de lignes) → droite globale → constante globale. Le repli est la partie
    importante : sans lui, les petits aéroports apprivoisent leur propre bruit.
    """
    etat: dict = {"mode": mode, "ap": {}, "global": None, "knots": {}}
    if mode == "constante":
        return etat
    etat["global"] = _droite(px, y)

    for a in pd.unique(ap):
        sel = ap == a
        if int(sel.sum()) < min_rows:
            continue
        xa, ya = px[sel], y[sel]
        if mode == "lineaire":
            etat["ap"][str(a)] = _droite(xa, ya)
        elif mode == "isotonique":
            from sklearn.isotonic import IsotonicRegression

            iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(xa, ya)
            grille = np.quantile(xa, np.linspace(0.0, 1.0, int(n_knots)))
            etat["knots"][str(a)] = {"x": [float(v) for v in grille],
                                     "y": [float(v) for v in iso.predict(grille)]}
        else:
            raise ValueError(f"reconstruct.calibration inconnu : {mode!r}")

    if mode == "isotonique":
        # Filet non linéaire pour les aéroports sous le seuil, sinon ils retomberaient sur une droite.
        from sklearn.isotonic import IsotonicRegression as _Iso

        iso_g = _Iso(increasing=True, out_of_bounds="clip").fit(px, y)
        grille_g = np.quantile(px, np.linspace(0.0, 1.0, int(n_knots)))
        etat["knots"]["__global__"] = {"x": [float(v) for v in grille_g],
                                       "y": [float(v) for v in iso_g.predict(grille_g)]}
    return etat


def apply_calibration(px: np.ndarray, ap: np.ndarray, state: dict) -> np.ndarray:
    """Valeur de base `E[cible | proxy, aéroport]`, NaN là où le proxy est absent."""
    calib = state.get("calib") or {"mode": "constante"}
    mode = str(calib.get("mode", "constante"))
    if mode == "constante":
        bias = np.array([state["bias"].get(a, state["glob_bias"]) for a in ap], dtype="float64")
        return px + bias

    base = np.full(len(px), np.nan)
    glob = calib.get("global")
    droite_globale = np.asarray(glob if isinstance(glob, list) else [0.0, 1.0], dtype="float64")
    ap_brut = calib.get("ap")
    droites: dict = ap_brut if isinstance(ap_brut, dict) else {}
    knots_brut = calib.get("knots")
    knots: dict = knots_brut if isinstance(knots_brut, dict) else {}
    knots_globaux = knots.get("__global__")
    for a in pd.unique(ap):
        sel = (ap == a) & np.isfinite(px)
        if not sel.any():
            continue
        x = px[sel]
        cle = str(a)
        if mode == "lineaire":
            w = np.asarray(droites.get(cle, droite_globale), dtype="float64")
            base[sel] = w[0] + w[1] * x
        else:
            kn = knots.get(cle) or knots_globaux
            if kn is None:
                w = np.asarray(droites.get(cle, droite_globale), dtype="float64")
                base[sel] = w[0] + w[1] * x
            else:
                base[sel] = np.interp(x, np.asarray(kn["x"], dtype="float64"),
                                      np.asarray(kn["y"], dtype="float64"))
    return base


def base_predictions(dep: pd.DataFrame, state: dict) -> tuple[np.ndarray, np.ndarray]:
    """Base de la reconstitution et masque « proxy exploitable » (aucun écrêtage appliqué)."""
    px = proxy_seconds(dep)
    ap = dep["ADEP_mvt"].astype("object").to_numpy()
    return apply_calibration(px, ap, state), np.isfinite(px)


def fit_state(train_dep: pd.DataFrame, cfg: dict) -> dict:
    y = train_dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    ap = train_dep["ADEP_mvt"].astype("object").to_numpy()
    px = proxy_seconds(train_dep)
    rc = cfg.get("reconstruct", {})
    lo_ok, hi_ok = float(rc.get("min_sec", 60)), float(rc.get("max_sec", 7200))
    ok = np.isfinite(y) & np.isfinite(px) & (y > 60) & (y < 7200) & (px >= lo_ok) & (px <= hi_ok)

    frame = pd.DataFrame({"ap": ap[ok], "y": y[ok], "px": px[ok]})
    resid = frame.y - frame.px
    bias = resid.groupby(frame.ap).mean()
    glob_bias = float(resid.mean())

    clip_cfg = cfg.get("clip", {})
    ql, qh = float(clip_cfg.get("q_low", 0.005)), float(clip_cfg.get("q_high", 0.995))
    ytr = pd.DataFrame({"ap": ap[np.isfinite(y) & (y > 60) & (y < 7200)], "y": y[np.isfinite(y) & (y > 60) & (y < 7200)]})
    lo = ytr.groupby("ap").y.quantile(ql).to_dict()
    hi = ytr.groupby("ap").y.quantile(qh).to_dict()

    hour = pd.to_datetime(train_dep["SCHED_TIME_UTC_mvt"], utc=True).dt.hour.to_numpy()
    fb_frame = pd.DataFrame({"ap": ap[ok], "hour": hour[ok], "y": y[ok]})
    counts = fb_frame.groupby(["ap", "hour"]).y.agg(["mean", "count"])
    glob_mean = float(y[np.isfinite(y) & (y > 60) & (y < 7200)].mean())
    fallback = {(a, h): (m * n + glob_mean * 100.0) / (n + 100.0) for (a, h), (m, n) in counts.iterrows()}

    return {"bias": bias.to_dict(), "glob_bias": glob_bias, "lo": lo, "hi": hi,
            "fallback": fallback, "glob_mean": glob_mean,
            "clip_enabled": bool(clip_cfg.get("enabled", True)),
            "calib": fit_calibration(px[ok], y[ok], ap[ok], str(rc.get("calibration", "constante")),
                                     min_rows=int(rc.get("calib_min_rows", 5_000)),
                                     n_knots=int(rc.get("calib_knots", 200))),
            "proxy_ok_share": float(ok.mean())}


def state_to_dict(state: dict) -> dict:
    """Version sérialisable de l'état calé sur le train (clés de dictionnaire en chaînes)."""
    return {
        "bias": {str(k): float(v) for k, v in state["bias"].items()},
        "glob_bias": float(state["glob_bias"]),
        "lo": {str(k): float(v) for k, v in state["lo"].items()},
        "hi": {str(k): float(v) for k, v in state["hi"].items()},
        "fallback": {f"{a}|{int(h)}": float(v) for (a, h), v in state["fallback"].items()},
        "glob_mean": float(state["glob_mean"]),
        "clip_enabled": bool(state["clip_enabled"]),
        "calib": state.get("calib") or {"mode": "constante"},
        "proxy_ok_share": float(state["proxy_ok_share"]),
    }


def state_from_dict(data: dict) -> dict:
    return {
        "bias": {str(k): float(v) for k, v in data["bias"].items()},
        "glob_bias": float(data["glob_bias"]),
        "lo": {str(k): float(v) for k, v in data["lo"].items()},
        "hi": {str(k): float(v) for k, v in data["hi"].items()},
        "fallback": {(k.split("|")[0], int(k.split("|")[1])): float(v) for k, v in data["fallback"].items()},
        "glob_mean": float(data["glob_mean"]),
        "clip_enabled": bool(data["clip_enabled"]),
        "calib": data.get("calib") or {"mode": "constante"},   # états antérieurs : base à constante
        "proxy_ok_share": float(data.get("proxy_ok_share", float("nan"))),
    }


def causal_fallback_predictions(run_id: str, val_month: str, val_dep: pd.DataFrame,
                                val_arr: pd.DataFrame | None, paths: dict) -> np.ndarray | None:
    """Prédictions du modèle causal entraîné sur les mêmes mois de train (repli propre)."""
    fold_dir = Path(paths["write"]["artifacts"]) / run_id / f"fold-{val_month}"
    model_path, spec_path = fold_dir / "model.txt", fold_dir / "spec.json"
    if not (model_path.exists() and spec_path.exists()):
        return None
    import json

    import lightgbm as lgb

    from src.features import FeatureSpec

    spec = FeatureSpec.from_dict(json.loads(spec_path.read_text(encoding="utf-8")))
    model = lgb.Booster(model_file=str(model_path))
    best = 0
    if (fold_dir / "meta.json").exists():
        best = int(json.loads((fold_dir / "meta.json").read_text(encoding="utf-8")).get("best_iteration", 0))
    X = spec.transform(val_dep, val_arr)
    return np.asarray(model.predict(X, num_iteration=best if best > 0 else None), dtype="float64")


def predict(val_dep: pd.DataFrame, state: dict, fallback_pred: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    px = proxy_seconds(val_dep)
    ap = val_dep["ADEP_mvt"].astype("object").to_numpy()
    hour = pd.to_datetime(val_dep["SCHED_TIME_UTC_mvt"], utc=True).dt.hour.to_numpy()
    bias = np.array([state["bias"].get(a, state["glob_bias"]) for a in ap], dtype="float64")
    if fallback_pred is None:
        fb = np.array([state["fallback"].get((a, int(h)), state["glob_mean"]) for a, h in zip(ap, hour)],
                      dtype="float64")
        fallback_kind = "airport_hour_mean"
    else:
        fb = np.asarray(fallback_pred, dtype="float64")
        fallback_kind = "causal_model"

    lo_ok, hi_ok = 60.0, 7200.0
    usable = np.isfinite(px) & (px >= lo_ok) & (px <= hi_ok)
    pred = np.where(usable, px + bias, fb)
    pred = np.where(np.isfinite(pred), pred, state["glob_mean"])  # aucune prédiction non finie

    if state["clip_enabled"]:
        lo = np.array([state["lo"].get(a, 60.0) for a in ap], dtype="float64")
        hi = np.array([state["hi"].get(a, 7200.0) for a in ap], dtype="float64")
        pred = np.clip(pred, lo, hi)
    return pred, {"proxy_used_share": float(usable.mean()), "fallback_share": float(1 - usable.mean()),
                  "fallback_kind": fallback_kind}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/tabular_hybrid.toml")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--folds", type=int, default=0)
    ap.add_argument("--split", default="dev", choices=["dev", "reserved"])
    ap.add_argument("--fallback-run", default="", help="run causal dont on charge les modèles pour le repli")
    args = ap.parse_args()

    cfg = load_config(args.config)
    paths = load_paths()
    protocol = Protocol.from_config(load_config("splits.toml"))
    folds = protocol.folds() if args.split == "dev" else [("reserve", protocol.reserve_train_months(), m)
                                                          for m in protocol.reserve_months]
    if args.folds:
        folds = folds[: args.folds]

    start = time.perf_counter()
    frames, states = [], {}
    for name, train_months, val_month in folds:
        train_dep = D.dep_for_months(train_months, paths)
        val_dep = D.dep_for_months([val_month], paths)
        val_arr = D.arr_for_months([val_month], paths)
        state = fit_state(train_dep, cfg)
        fb_pred = None
        if args.fallback_run:
            fb_pred = causal_fallback_predictions(args.fallback_run, val_month, val_dep, val_arr, paths)
            if fb_pred is None:
                print(f"[{args.run_id}] repli causal indisponible pour {val_month}, repli moyenne aéroport-heure")
        pred, diag = predict(val_dep, state, fb_pred)
        y = val_dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
        frames.append(pd.DataFrame({"MVT_ID_mvt": val_dep["MVT_ID_mvt"].to_numpy(), "month": val_month,
                                    "ADEP_mvt": val_dep["ADEP_mvt"].astype("object").to_numpy(),
                                    "pred": pred, "target": y}))
        states[val_month] = {**diag, "proxy_ok_share_train": state["proxy_ok_share"],
                             "clip_enabled": state["clip_enabled"]}

    eval_df = pd.concat(frames, ignore_index=True)
    report = build_report(args.run_id, args.config, cfg.get("track", "hybrid"), cfg.get("kind", "reconstruct"),
                          eval_df, protocol, states, time.perf_counter() - start, split=args.split,
                          extra={"avertissement": "piste de reconstitution : utilise MVT_TIME et AOBT_3, "
                                                  "informations postérieures à l'off-block"})
    out = write_report(report, eval_df, Path(paths["write"]["reports"]))
    print(f"ecrit {out}")
    print({"global": report["global"], "by_month": [(r["month"], round(r["rmse"], 1)) for r in report["by_month"]]})


if __name__ == "__main__":
    main()
