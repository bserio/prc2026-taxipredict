"""Entraînement et évaluation sur les plis de développement.

Usage :
    python -m src.train --config configs/tabular_causal.toml --run-id causal-r1
    python -m src.train --config configs/baseline.toml --run-id baseline-r1 [--folds 1]

Écrit artifacts/<run-id>/ (modèles, specs de features) et reports/<run-id>.json.
La réserve interne 2025 n'est jamais lue ici (voir src.evaluate_reserved).
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.features import FeatureSpec
from src.metrics import grouped_report, out_of_domain, summary
from src.splits import Protocol, fingerprint, save_fingerprint


def peak_rss_mib() -> float:
    """Pic RSS du processus principal (les enfants ne sont pas comptés sur macOS)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576.0


def target_of(dep: pd.DataFrame) -> np.ndarray:
    return dep["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")


def fit_baseline(train_y: np.ndarray, train_ap: np.ndarray, val_ap: np.ndarray, mode: str) -> np.ndarray:
    """Baseline apprise sur le train du pli uniquement ; repli sur la moyenne globale."""
    keep = np.isfinite(train_y) & (train_y > 60) & (train_y < 7200)
    y_tr, ap_tr = train_y[keep], train_ap[keep]
    glob = float(y_tr.mean())
    if mode == "global_mean":
        return np.full(len(val_ap), glob, dtype="float64")
    if mode == "airport_mean":
        table = pd.Series(y_tr).groupby(ap_tr).mean().to_dict()
        counts = pd.Series(y_tr).groupby(ap_tr).size().to_dict()
        shrunk = {k: (v * counts[k] + glob * 50.0) / (counts[k] + 50.0) for k, v in table.items()}
        return np.array([shrunk.get(a, glob) for a in val_ap], dtype="float64")
    raise ValueError(f"baseline inconnue : {mode}")


def run_fold(cfg: dict, protocol: Protocol, val_month: str, train_months, paths: dict,
             lgb_params: dict, fit_state: dict, artifacts_dir: Path | None = None) -> pd.DataFrame:
    track = cfg.get("track", "causal")
    use_rwy = bool(cfg.get("features", {}).get("runway_actual", False))
    kind = cfg.get("kind", "lightgbm")
    train_dep = D.dep_for_months(train_months, paths)
    train_arr = D.arr_for_months(train_months, paths)
    val_dep = D.dep_for_months([val_month], paths)
    val_arr = D.arr_for_months([val_month], paths)

    y_tr, y_va = target_of(train_dep), target_of(val_dep)
    start = time.perf_counter()

    if kind == "baseline":
        mode = cfg.get("baseline_mode", "global_mean")
        pred = fit_baseline(y_tr, train_dep["ADEP_mvt"].astype("object").to_numpy(),
                            val_dep["ADEP_mvt"].astype("object").to_numpy(), mode)
        n_features, best_iteration, model, spec = 0, 0, None, None
    else:
        spec = FeatureSpec(track=track, use_runway_actual=use_rwy,
                           use_dest_pressure=bool(cfg.get("features", {}).get("dest_pressure", False)),
                           use_regime_flag=bool(cfg.get("features", {}).get("regime_flag", False)),
                           use_stand=bool(cfg.get("features", {}).get("stand_enc", True)),
                           use_lobt=bool(cfg.get("features", {}).get("plan_lobt", True)),
                           epoch_seconds=bool(cfg.get("features", {}).get("epoch_seconds", False))
                           ).fit(train_dep, train_arr, y_tr)
        X_tr = spec.transform(train_dep, train_arr)
        X_va = spec.transform(val_dep, val_arr)
        if cfg.get("train_filter", True):
            keep = np.isfinite(y_tr) & (y_tr > 60) & (y_tr < 7200)
        else:
            keep = np.isfinite(y_tr)
        X_tr, y_fit = X_tr.loc[keep], y_tr[keep]
        fit_state.setdefault("filter", {})["train_rows_kept"] = int(keep.sum())
        booster_params = {k: v for k, v in lgb_params.items() if k not in {"num_boost_round", "early_stopping_round"}}
        ds_tr = lgb.Dataset(X_tr, y_fit, categorical_feature=spec.categorical_names(), free_raw_data=False)
        ds_va = lgb.Dataset(X_va, y_va, reference=ds_tr)
        callbacks = [lgb.early_stopping(lgb_params.get("early_stopping_round", 150), verbose=False), lgb.log_evaluation(0)]
        model = lgb.train(booster_params, ds_tr, num_boost_round=lgb_params.get("num_boost_round", 4000),
                          valid_sets=[ds_va], callbacks=callbacks)
        pred = model.predict(X_va, num_iteration=model.best_iteration)
        n_features, best_iteration = int(X_tr.shape[1]), int(model.best_iteration)
        if artifacts_dir is not None:
            fold_dir = Path(artifacts_dir) / f"fold-{val_month}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            model.save_model(str(fold_dir / "model.txt"))
            (fold_dir / "spec.json").write_text(json.dumps(spec.to_dict()), encoding="utf-8")
            (fold_dir / "meta.json").write_text(
                json.dumps({"best_iteration": int(model.best_iteration), "val_month": val_month,
                            "train_months": list(train_months)}), encoding="utf-8")

    runtime = time.perf_counter() - start
    out = pd.DataFrame({"MVT_ID_mvt": val_dep["MVT_ID_mvt"].to_numpy(), "month": val_month,
                        "ADEP_mvt": val_dep["ADEP_mvt"].astype("object").to_numpy(),
                        "pred": np.asarray(pred, dtype="float64"), "target": y_va})
    stats = summary(out.pred.to_numpy(), out.target.to_numpy())
    fit_state.setdefault("folds", {})[val_month] = {
        "best_iteration": best_iteration, "train_rows": int(len(train_dep)), "val_rows": int(len(val_dep)),
        "n_features": n_features, "runtime_s": round(runtime, 1), **stats,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--folds", type=int, default=0, help="limite le nombre de plis (0 = tous)")
    ap.add_argument("--months", default="", help="sous-ensemble de mois de validation, séparés par des virgules")
    ap.add_argument("--witness", action="store_true",
                    help="plis témoins élargis (mois hors rotation normale) ; ne départagent jamais deux recettes")
    ap.add_argument("--baseline-mode", default="", choices=["", "global_mean", "airport_mean"])
    ap.add_argument("--no-fingerprint", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.baseline_mode:
        cfg["baseline_mode"] = args.baseline_mode
    paths = load_paths()
    protocol = Protocol.from_config(load_config("splits.toml"))
    metrics_cfg = load_config("metrics.toml")
    lgb_params = dict(cfg.get("lightgbm", {}))
    split_name = "witness" if args.witness else "dev"
    folds = protocol.witness_folds() if args.witness else protocol.folds()
    if args.months:
        wanted = set(args.months.split(","))
        folds = [f for f in folds if f[2] in wanted]
    if args.folds:
        folds = folds[: args.folds]

    start = time.perf_counter()
    artifacts_dir = Path(paths["write"]["artifacts"]) / args.run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    fit_state: dict = {}
    frames = []
    for name, train_months, val_month in folds:
        print(f"[{args.run_id}] pli {name} : train={len(train_months)} mois, val={val_month}", flush=True)
        frames.append(run_fold(cfg, protocol, val_month, train_months, paths, lgb_params, fit_state, artifacts_dir))

    eval_df = pd.concat(frames, ignore_index=True)
    overall = summary(eval_df.pred.to_numpy(), eval_df.target.to_numpy())
    report = {
        "run_id": args.run_id,
        "config": args.config,
        "track": cfg.get("track", "causal"),
        "kind": cfg.get("kind", "lightgbm"),
        "protocol": {"all_months": list(protocol.all_months), "reserve_months": list(protocol.reserve_months),
                     "dev_val_months": list(protocol.dev_val_months), "folds": [f[0] for f in folds]},
        "split": split_name,
        "global": {**overall, "n_rows": int(len(eval_df))},
        "by_month": grouped_report(eval_df, by=("month",)),
        "by_airport": grouped_report(eval_df, by=("ADEP_mvt",)),
        "out_of_domain": out_of_domain(eval_df.pred.to_numpy()),
        "folds": fit_state.get("folds", {}),
        "runtime_s": round(time.perf_counter() - start, 1),
        "peak_rss_mib_note": "pic RSS du processus principal uniquement (enfants non comptés sur macOS)",
        "peak_rss_mib": round(peak_rss_mib(), 1),
        "metric_unit": metrics_cfg["metric"]["unit"],
    }
    reports = Path(paths["write"]["reports"])
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{args.run_id}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    eval_df.to_parquet(reports / f"{args.run_id}.eval.parquet", index=False)

    if not args.no_fingerprint:
        save_fingerprint(fingerprint(protocol, paths["_official"]), reports / f"{args.run_id}.fingerprint.json")

    print(json.dumps({"run_id": args.run_id, "global": report["global"],
                      "by_month": [(r["month"], round(r["rmse"], 1)) for r in report["by_month"]]}, indent=1))


if __name__ == "__main__":
    main()
