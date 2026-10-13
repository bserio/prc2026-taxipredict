"""Invariants de l'audit des sources : classification exhaustive et identite algebrique."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.audit import CONCORDANT, FORT, MODERE, SANS_INFO, categories, ecart_offblock

CATEGORIES = {CONCORDANT, MODERE, FORT, SANS_INFO}


def _vol(minuties):
    """Construit un depart à partir des trois horloges (None = champ absent)."""
    base = pd.Timestamp("2025-01-05 06:00:00", tz="UTC")
    def col(v):
        return pd.Series([None if x is None else base + pd.Timedelta(minutes=x) for x in v], dtype="datetime64[ns, UTC]")
    sched, block, aobt = zip(*minuties)
    return pd.DataFrame({"SCHED_TIME_UTC_mvt": col(sched), "BLOCK_TIME_UTC_mvt": col(block),
                         "AOBT_3_flt": col(aobt)})


def test_identite_cible_moins_proxy_egale_ecart() -> None:
    """`cible - proxy` doit etre exactement `AOBT_3 - BLOCK_TIME`, quel que soit MVT_TIME."""
    dep = _vol([(0, 10, 12), (0, 30, 95), (0, None, 40), (0, 20, None)])
    base = pd.Timestamp("2025-01-05 06:00:00", tz="UTC")
    mvt = pd.Series([base + pd.Timedelta(minutes=m) for m in (30, 90, 60, 50)], dtype="datetime64[ns, UTC]")
    cible = ((mvt - dep.BLOCK_TIME_UTC_mvt).dt.total_seconds()).to_numpy(dtype="float64")
    proxy = ((mvt - dep.AOBT_3_flt).dt.total_seconds()).to_numpy(dtype="float64")
    ecart = ecart_offblock(dep)
    attendu = cible - proxy
    fini = np.isfinite(attendu) & np.isfinite(ecart)
    assert fini.sum() == 2                                   # deux vols ont les deux sources
    assert np.allclose(attendu[fini], ecart[fini])


def test_classification_exhaustive_et_mutuellement_exclusive() -> None:
    dep = _vol([(0, 10, 12), (0, 30, 95), (0, None, 40), (0, 20, None), (0, 60, 200)])
    cat = categories(ecart_offblock(dep))
    assert set(cat.unique()) <= CATEGORIES
    assert len(cat) == len(dep)
    compte = cat.value_counts()
    assert compte[SANS_INFO] == 2                            # un par source manquante
    assert compte[CONCORDANT] >= 1


def test_l_absence_de_seconde_source_ne_depend_d_aucun_seuil() -> None:
    dep = _vol([(0, 10, 12), (0, None, 40)])
    e = ecart_offblock(dep)
    for seuils in ((600, 1200), (900, 1800), (1800, 3600)):
        assert categories(e, seuils).iloc[1] == SANS_INFO


def test_elargir_les_seuils_ne_deplace_jamais_vers_plus_de_desaccord() -> None:
    rng = np.random.default_rng(0)
    e = rng.normal(0, 1500, 5000)
    parts = []
    for seuils in ((600, 1200), (900, 1800), (1800, 3600)):
        c = categories(e, seuils)
        parts.append(float((c == FORT).mean()) + float((c == MODERE).mean()))
    assert parts == sorted(parts, reverse=True)              # seuils plus larges -> moins de discordants
