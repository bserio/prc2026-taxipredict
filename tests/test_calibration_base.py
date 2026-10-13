"""Invariants de la base de reconstitution calibrée (D-031).

Deux choses sont protégées ici : les recettes gelées (mode `constante`) doivent reproduire exactement
la base d'origine, et une base calibrée ne doit dépendre d'aucune étiquette au moment d'inférer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.reconstruct import (apply_calibration, base_predictions, fit_state, proxy_seconds,
                             state_from_dict, state_to_dict)
from tests.conftest import make_dep


def etat(mode: str) -> tuple[dict, pd.DataFrame]:
    train = make_dep(1200, seed=0)
    cfg = {"reconstruct": {"calibration": mode, "calib_min_rows": 200, "calib_knots": 40}}
    return fit_state(train, cfg), make_dep(300, seed=11)


def test_mode_defaut_reproduit_la_base_d_origine() -> None:
    train = make_dep(1200, seed=0)
    state = fit_state(train, {})                       # aucune cle `calibration` : recettes gelées
    assert state["calib"]["mode"] == "constante"
    val = make_dep(300, seed=11)
    px = proxy_seconds(val)
    ap = val["ADEP_mvt"].astype("object").to_numpy()
    attendu = px + np.array([state["bias"].get(a, state["glob_bias"]) for a in ap], dtype="float64")
    base, usable = base_predictions(val, state)
    np.testing.assert_allclose(base, attendu, equal_nan=True)
    assert (usable == np.isfinite(px)).all()


def test_base_calibree_ne_depend_d_aucune_etiquette() -> None:
    """Deux frames identiques en variables d'entrée doivent donner la même base, quelle que soit la cible."""
    for mode in ("lineaire", "isotonique"):
        state, val = etat(mode)
        a = apply_calibration(proxy_seconds(val), val["ADEP_mvt"].astype("object").to_numpy(), state)
        remanie = val.copy()
        remanie["TAXITIME_SEC_mvt"] = (remanie["TAXITIME_SEC_mvt"].astype("int64") + 4000).astype("int32")
        b = apply_calibration(proxy_seconds(remanie), remanie["ADEP_mvt"].astype("object").to_numpy(), state)
        np.testing.assert_allclose(a, b, equal_nan=True)


def test_calibrations_non_lineaires_restent_monotones_et_finies() -> None:
    state, val = etat("isotonique")
    px = proxy_seconds(val)
    base = apply_calibration(px, val["ADEP_mvt"].astype("object").to_numpy(), state)
    assert np.isfinite(base[np.isfinite(px)]).all()
    tri = np.argsort(px)
    # Monotone par aéroport : sur un seul aéroport, base croissante avec le proxy.
    ap = val["ADEP_mvt"].astype("object").to_numpy()
    pour_un = (ap == ap[0]) & np.isfinite(px)
    y_triee = base[pour_un][np.argsort(px[pour_un])]
    assert (np.diff(y_triee) >= -1e-6).all()


def test_persistance_de_la_calibration() -> None:
    for mode in ("lineaire", "isotonique"):
        state, val = etat(mode)
        ap = val["ADEP_mvt"].astype("object").to_numpy()
        px = proxy_seconds(val)
        avant = apply_calibration(px, ap, state)
        apres = apply_calibration(px, ap, state_from_dict(state_to_dict(state)))
        np.testing.assert_allclose(avant, apres, equal_nan=True)


def test_repli_sur_aeroport_sous_le_seuil() -> None:
    """Un aéroport sous le seuil n'apprend rien pour lui-même : c'est le filet global qui parle."""
    etat_iso, _ = etat("isotonique")
    assert etat_iso["calib"]["knots"].get("__global__") is not None

    val = make_dep(300, seed=11)
    orphelin = {"bias": {}, "glob_bias": 0.0, "glob_mean": 600.0,
                "calib": {"mode": "isotonique", "global": [0.0, 1.0], "ap": {}, "knots": {}}}
    base = apply_calibration(proxy_seconds(val), val["ADEP_mvt"].astype("object").to_numpy(), orphelin)
    assert np.isfinite(base).all()                     # aucun aéroport connu : filet global quand même
