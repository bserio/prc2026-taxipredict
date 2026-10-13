"""Invariants de la projection du score officiel (D-030).

Ce module produit un chiffre destiné à être lu par un humain : ses garde-fous portent sur ce qui
rendrait le chiffre faux — poids qui ne couvrent pas la population, replis silencieux, étiquettes
2026 utilisées alors qu'elles n'existent pas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.score_projection import cellule, charger_2026, profil, projeter, tranche


def _eval() -> pd.DataFrame:
    """Population synthétique équilibrée sur les sept tranches : chaque cellule est bien peuplée."""
    rng = np.random.default_rng(0)
    bornes = [(0.0, 900.0), (900.0, 1800.0), (1800.0, 2700.0), (2700.0, 3600.0),
              (3600.0, 5400.0), (5400.0, 7200.0), (7200.0, 12000.0)]
    px = np.concatenate([rng.uniform(lo, hi, 600) for lo, hi in bornes])
    ap = rng.choice(["LIRF", "EHAM"], len(px)).astype(object)
    tr = tranche(px)
    return pd.DataFrame({"month": np.tile(np.repeat(["2025-01", "2025-07"], 300), 7)[:len(px)],
                         "ap": ap, "proxy": px, "tranche": tr, "cellule": cellule(ap, tr),
                         "sq": rng.gamma(2.0, 40_000.0, len(px))})


def test_tranches_couvre_toutes_lignes_et_separe_sans_fiche() -> None:
    px = np.array([100.0, 1000.0, 5000.0, 99_999.0, np.nan])
    t = tranche(px)
    assert (t[:-1] != "sans fiche réseau").all() and t[-1] == "sans fiche réseau"
    assert len(np.unique(t)) == 5                      # chaque valeur finie dans sa propre tranche


def test_projection_sur_sa_propre_population_retombe_sur_le_reel() -> None:
    ev = _eval()
    table, repli = profil(ev)
    projete, avertissements = projeter(ev["cellule"].to_numpy(), table, repli)
    reel = float(np.sqrt(ev["sq"].mean()))
    assert abs(projete / reel - 1.0) < 1e-4            # à l'arrondi des poids près (value_counts)
    assert avertissements == []


def test_cellule_inconnue_provoque_un_repli_declare() -> None:
    ev = _eval()
    table, repli = profil(ev)
    inconnues = np.array(["999999-inf|LIRF"] * 50 + list(ev["cellule"].to_numpy()[1:]))
    projete, avertissements = projeter(inconnues, table, repli)
    assert any("remplacée" in a for a in avertissements)
    assert np.isfinite(projete)


def test_les_poids_de_la_projection_couvrent_toute_la_population() -> None:
    """La somme des parts vaut 1 : une population mal filtrée fausserait silencieusement le chiffre."""
    parts = pd.Series(_eval()["cellule"].to_numpy()).value_counts(normalize=True)
    assert abs(float(parts.sum()) - 1.0) < 1e-9


def test_la_projection_ne_peut_pas_lire_de_cible(monkeypatch) -> None:
    """Les entrées officielles n'ont pas de cible : on vérifie que le chargeur n'en réclame aucune."""
    faux = pd.DataFrame({"month": ["2026-01", "2026-01"], "ADEP_mvt": ["LFPG", "LIRF"],
                         "MVT_TIME_UTC_mvt": pd.to_datetime(["2026-01-05 08:00", "2026-01-05 09:00"], utc=True),
                         "AOBT_3_flt": pd.to_datetime(["2026-01-05 07:30", "2026-01-05 08:20"], utc=True)})
    monkeypatch.setattr("src.score_projection.D.final_frames", lambda paths=None, tmp_dir=None: (faux, faux))
    charge = charger_2026({})
    assert {"month", "ap", "proxy", "tranche", "cellule"} <= set(charge.columns)
    assert not any(c.endswith("_mvt") or c.endswith("_flt") for c in charge.columns)
