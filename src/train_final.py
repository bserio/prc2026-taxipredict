"""Entraînement final (gel) sur tous les mois 2025 hors réserve, puis inférence 2026.

    python -m src.train_final --config configs/tabular_causal.toml --run-id causal-final
    python -m src.predict --track causal --model-dir artifacts/causal-final/final --run-id sub-causal-v1
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
from src.splits import Protocol


def median_rounds(report_path: str) -> int:
    """Nombre d'itérations du gel = médiane des plis de développement (pas un réglage sur la réserve)."""
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    iters = [int(d["best_iteration"]) for d in data.get("folds", {}).values() if "best_iteration" in d]
    if not iters:
        raise SystemExit(f"aucun best_iteration dans {report_path}")
    return int(np.median(iters))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from-report", default="", help="rapport de dev dont on prend la médiane des itérations")
    args = ap.parse_args()

    cfg = load_config(args.config)
    paths = load_paths()
    protocol = Protocol.from_config(load_config("splits.toml"))
    months = protocol.reserve_train_months()      # la réserve reste exclue du gel
    print(f"[{args.run_id}] gel : entraînement sur {len(months)} mois hors réserve {list(protocol.reserve_months)}")

    dep = D.dep_for_months(months, paths)
    arr = D.arr_for_months(months, paths)
    y = dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    lgb_params = dict(cfg.get("lightgbm", {}))
    use_rwy = bool(cfg.get("features", {}).get("runway_actual", False))
    track = cfg.get("track", "causal")
    residual = cfg.get("kind") == "lightgbm-residual"

    state_dict = None
    if residual:
        from src.reconstruct import fit_state, state_to_dict
        from src.residual import baseline

        state = fit_state(dep, cfg)
        base, usable = baseline(dep, state)
        target = y - base
        keep = np.isfinite(y) & usable
        state_dict = state_to_dict(state)
    else:
        target = y
        keep = np.isfinite(y) & (y > 60) & (y < 7200) if cfg.get("train_filter", True) else np.isfinite(y)

    spec = FeatureSpec(track=track, use_runway_actual=use_rwy,
                       use_dest_pressure=bool(cfg.get("features", {}).get("dest_pressure", False)),
                       use_regime_flag=bool(cfg.get("features", {}).get("regime_flag", False))
                       ).fit(dep.loc[keep], arr, target[keep])
    X = spec.transform(dep.loc[keep], arr)

    params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
    ds = lgb.Dataset(X, target[keep], categorical_feature=spec.categorical_names(), free_raw_data=False)
    start = time.perf_counter()
    # Sans jeu de validation : le nombre d'itérations est fixé à la médiane des plis de
    # développement (DECISIONS.md), consigné dans meta.json pour la reproductibilité.
    n_rounds = median_rounds(args.from_report) if args.from_report else int(cfg.get("final_num_boost_round", 400))
    model = lgb.train(params, ds, num_boost_round=n_rounds)
    out_dir = Path(paths["write"]["artifacts"]) / args.run_id / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(out_dir / "model.txt"))
    (out_dir / "spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    if state_dict is not None:
        (out_dir / "state.json").write_text(json.dumps(state_dict), encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps({
        "train_months": list(months), "num_boost_round": n_rounds, "rows": int(keep.sum()),
        "target": "residu_du_proxy" if residual else "valeur_absolue",
        "n_features": int(X.shape[1]), "runtime_s": round(time.perf_counter() - start, 1),
        "iterations_source": args.from_report or "config.final_num_boost_round",
        "config": args.config}, indent=1), encoding="utf-8")
    print(f"ecrit {out_dir}")


if __name__ == "__main__":
    main()
