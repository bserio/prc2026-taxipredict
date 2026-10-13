"""Métriques officielles et diagnostics.

La métrique de classement est la RMSE calculée sur toutes les lignes attendues du
gabarit ; les agrégats par mois ou aéroport sont des diagnostics, leur moyenne non
pondérée ne remplace pas la RMSE globale.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def rmse(pred: np.ndarray, target: np.ndarray) -> float:
    pred = np.asarray(pred, dtype="float64")
    target = np.asarray(target, dtype="float64")
    ok = np.isfinite(pred) & np.isfinite(target)
    if not ok.any():
        return float("nan")
    return float(math.sqrt(float(np.mean((pred[ok] - target[ok]) ** 2))))


def mae(pred: np.ndarray, target: np.ndarray) -> float:
    pred = np.asarray(pred, dtype="float64")
    target = np.asarray(target, dtype="float64")
    ok = np.isfinite(pred) & np.isfinite(target)
    if not ok.any():
        return float("nan")
    return float(np.mean(np.abs(pred[ok] - target[ok])))


def bias(pred: np.ndarray, target: np.ndarray) -> float:
    """Biais défini comme moyenne(prediction - cible)."""
    pred = np.asarray(pred, dtype="float64")
    target = np.asarray(target, dtype="float64")
    ok = np.isfinite(pred) & np.isfinite(target)
    if not ok.any():
        return float("nan")
    return float(np.mean(pred[ok] - target[ok]))


def coverage(pred: np.ndarray, expected_ids: Iterable[float], id_col: np.ndarray) -> dict:
    """Couverture = prédictions finies correspondant aux lignes attendues / lignes attendues."""
    expected = {float(v) for v in expected_ids}
    got: dict[float, float] = {}
    for ident, value in zip(np.asarray(id_col, dtype="float64"), np.asarray(pred, dtype="float64")):
        if math.isfinite(value):
            got[float(ident)] = value
    matched = sum(1 for ident in expected if ident in got)
    return {
        "expected": len(expected),
        "matched_finite": matched,
        "coverage": matched / len(expected) if expected else float("nan"),
        "extra_ids": len(set(got) - expected),
        "missing_ids": len(expected - set(got)),
    }


def out_of_domain(pred: np.ndarray) -> dict:
    pred = np.asarray(pred, dtype="float64")
    return {
        "n_negative": int(np.nansum(pred < 0)),
        "n_zero": int(np.nansum(pred == 0)),
        "n_over_7200": int(np.nansum(pred > 7200)),
        "n_nonfinite": int(np.sum(~np.isfinite(pred))),
    }


def grouped_report(df, pred_col: str = "pred", target_col: str = "target",
                   by: tuple[str, ...] = ("month",)) -> list[dict]:
    rows = []
    for keys, g in df.groupby(list(by), dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rows.append(
            {
                **{name: (None if v is None else str(v)) for name, v in zip(by, keys)},
                "n": int(len(g)),
                "rmse": rmse(g[pred_col].to_numpy(), g[target_col].to_numpy()),
                "mae": mae(g[pred_col].to_numpy(), g[target_col].to_numpy()),
                "bias": bias(g[pred_col].to_numpy(), g[target_col].to_numpy()),
            }
        )
    return sorted(rows, key=lambda r: -r["rmse"])


def summary(pred: np.ndarray, target: np.ndarray) -> dict:
    return {"rmse": rmse(pred, target), "mae": mae(pred, target), "bias": bias(pred, target)}
