"""Définitions de métriques : RMSE officielle, MAE, biais, couverture."""

from __future__ import annotations

import numpy as np

from src.metrics import bias, coverage, grouped_report, mae, rmse


def test_rmse_valeur_known() -> None:
    assert rmse(np.array([10.0, 20.0]), np.array([0.0, 0.0])) == np.sqrt((100 + 400) / 2)


def test_rmse_non_ponderee_par_groupe() -> None:
    """La moyenne des RMSE par groupe n'est pas la RMSE globale : on le vérifie."""
    pred = np.array([100.0, 0.0, 0.0, 0.0])
    target = np.array([0.0, 0.0, 1.0, 1.0])
    global_rmse = rmse(pred, target)
    g1 = rmse(pred[:2], target[:2])
    g2 = rmse(pred[2:], target[2:])
    assert abs((g1 + g2) / 2 - global_rmse) > 1.0


def test_mae_et_bias() -> None:
    pred = np.array([10.0, 20.0])
    target = np.array([0.0, 30.0])
    assert mae(pred, target) == 10.0
    assert bias(pred, target) == 0.0      # moyenne(pred - target) = (10 + -10)/2


def test_couverture_et_extras() -> None:
    ids = np.array([1.0, 2.0, 3.0])
    pred = np.array([100.0, np.nan, 300.0])
    cov = coverage(pred, [1.0, 2.0, 3.0], ids)
    assert cov["expected"] == 3 and cov["matched_finite"] == 2
    assert abs(cov["coverage"] - 2 / 3) < 1e-9
    assert cov["missing_ids"] == 1


def test_grouped_report_tri() -> None:
    import pandas as pd

    df = pd.DataFrame({"month": ["a", "a", "b"], "pred": [1.0, 2.0, 10.0], "target": [0.0, 0.0, 0.0]})
    rows = grouped_report(df, by=("month",))
    assert rows[0]["month"] == "b"        # tri par RMSE décroissante
    assert rows[0]["n"] == 1
