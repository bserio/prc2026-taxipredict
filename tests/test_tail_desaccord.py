"""Garde-fous de la spécialisation « désaccord planifié / réalisé » (D-033).

Le mécanisme est derrière un drapeau désactivé par défaut : ces tests vérifient la définition du
sélecteur (seule chose qui distingue les deux modèles) et le refus explicite quand la région est trop
petite pour qu'un spécialiste ait un sens.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.residual import _tail_model, baseline, desaccord_minutes, fit_state
from tests.conftest import make_arr, make_dep


def test_desaccord_valeur_absolue_et_nan() -> None:
    dep = make_dep(60, seed=3)
    dep["AOBT_3_flt"] = dep["LOBT_flt"] + pd.Timedelta(minutes=-25)
    d = desaccord_minutes(dep)
    assert np.allclose(d, 25.0)

    inverse = dep.copy()
    inverse["AOBT_3_flt"] = inverse["LOBT_flt"] + pd.Timedelta(minutes=25)
    assert np.allclose(desaccord_minutes(inverse), d)          # valeur absolue : le sens n'importe pas

    casse = dep.copy()
    casse.loc[0, "LOBT_flt"] = pd.NaT
    assert np.isnan(desaccord_minutes(casse)[0])


def test_le_seuil_selectionne_bon_regime() -> None:
    dep = make_dep(400, seed=5)
    ecart = np.full(len(dep), 5.0)
    ecart[:100] = 90.0
    dep["AOBT_3_flt"] = dep["LOBT_flt"] + pd.to_timedelta(ecart, unit="m")
    d = desaccord_minutes(dep)
    assert int((d >= 30).sum()) == 100


def test_refus_si_region_trop_petite() -> None:
    """Un spécialiste entraîné sur quelques centaines de lignes est du bruit : on refuse de le produire."""
    train = make_dep(600, seed=0)
    cfg = {"track": "hybrid", "features": {}, "lightgbm": {"seed": 7}, "tail": {"seuil_desaccord_min": 30,
                                                                                "min_rows": 20_000}}
    etat = fit_state(train, cfg)
    y = train["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    base, usable = baseline(train, etat)
    with pytest.raises(RuntimeError, match="pas assez de lignes"):
        _tail_model(train, make_arr(), y, base, usable, cfg)
