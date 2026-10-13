"""Rapports de run homogènes entre pistes (mêmes clés pour scripts/eval.py)."""

from __future__ import annotations

import json
import resource
from pathlib import Path

import numpy as np
import pandas as pd

from src.metrics import grouped_report, out_of_domain, summary


def peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576.0


def build_report(run_id: str, config: str, track: str, kind: str, eval_df: pd.DataFrame,
                 protocol, folds_state: dict, runtime_s: float, split: str = "dev",
                 extra: dict | None = None) -> dict:
    overall = summary(eval_df["pred"].to_numpy(), eval_df["target"].to_numpy())
    report = {
        "run_id": run_id,
        "config": config,
        "track": track,
        "kind": kind,
        "split": split,
        "protocol": {"all_months": list(protocol.all_months), "reserve_months": list(protocol.reserve_months),
                     "dev_val_months": list(protocol.dev_val_months)},
        "global": {**overall, "n_rows": int(len(eval_df))},
        "by_month": grouped_report(eval_df, by=("month",)),
        "by_airport": grouped_report(eval_df, by=("ADEP_mvt",)),
        "out_of_domain": out_of_domain(eval_df["pred"].to_numpy()),
        "folds": folds_state,
        "runtime_s": round(runtime_s, 1),
        "peak_rss_mib": round(peak_rss_mib(), 1),
        "peak_rss_mib_note": "pic RSS du processus principal uniquement (enfants non comptés sur macOS)",
        "metric_unit": "secondes",
    }
    if extra:
        report.update(extra)
    return report


def write_report(report: dict, eval_df: pd.DataFrame, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['run_id']}.json"
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    eval_df.to_parquet(reports_dir / f"{report['run_id']}.eval.parquet", index=False)
    return path
