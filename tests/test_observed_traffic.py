"""Garde-fous de la piste « reference + attente » : fenetres strictement anterieures, auto-exclusion.

Ces tests sont la garantie verifiable de la discipline annoncee dans `src/refattente.py` : le trafic
observe ne doit jamais regarder l'avenir, et un vol ne doit jamais compter son propre decollage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.refattente import observed_frame

T0 = pd.Timestamp("2025-06-15 12:00:00", tz="UTC")


def _ts(minutes: float) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=minutes)


def _dep(lignes: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({"MVT_ID_mvt": [f"d{i}" for i in range(len(lignes))],
                         "ADEP_mvt": [a for a, _ in lignes],
                         "SCHED_TIME_UTC_mvt": [_ts(m) for _, m in lignes],
                         "MVT_TIME_UTC_mvt": [_ts(m) for _, m in lignes]})


def _arr(lignes: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({"ADES_mvt": [a for a, _ in lignes],
                         "MVT_TIME_UTC_mvt": [_ts(m) for _, m in lignes]})


def test_fenetres_antérieures_et_exclusion_du_futur():
    dep = _dep([("LFPG", 0.0)])
    arr = _arr([("LFPG", -10.0), ("LFPG", -30.0), ("LFPG", -60.0), ("LFPG", +5.0)])
    obs = observed_frame(dep, arr, dep)
    assert obs["obs_arr_15"][0] == 1          # seul le vol de -10 min
    assert obs["obs_arr_45"][0] == 2          # -10 et -30
    assert obs["obs_arr_90"][0] == 3          # -10, -30, -60 ; JAMAIS celui de +5 min


def test_un_vol_ne_compte_jamais_son_propre_decollage():
    dep = _dep([("LFPG", 0.0), ("LFPG", -3.0)])
    obs = observed_frame(dep, _arr([]), dep)
    assert obs["obs_dep_15"][0] == 1          # uniquement l'autre depart (a -3 min)
    assert obs["obs_dep_15"][1] == 0          # lui-meme est deja exclu de sa propre fenetre


def test_ancre_strictement_exclue():
    dep = _dep([("LFPG", 0.0)])
    arr = _arr([("LFPG", 0.0), ("LFPG", -0.5)])       # une arrivee pile a l'ancre
    obs = observed_frame(dep, arr, dep)
    assert obs["obs_arr_15"][0] == 1                  # seule celle de -0,5 min compte


def test_delai_depuis_dernier_evenement():
    dep = _dep([("LFPG", 0.0)])
    arr = _arr([("LFPG", -20.0), ("LFPG", -90.0)])
    obs = observed_frame(dep, arr, dep)
    assert abs(obs["obs_arr_idle_min"][0] - 20.0) < 1e-6


def test_epoch_est_en_secondes_quelle_que_soit_la_resolution():
    """Garde-fou du defaut corrige en D-034 : `epoch()` ne doit pas dependre de la resolution du dtype."""
    from src.prepare import epoch

    attendu = (T0 - pd.Timestamp("1970-01-01", tz="UTC")).total_seconds()
    assert abs(epoch(pd.Series([T0]))[0] - attendu) < 1e-6
    for unite in ("ns", "us", "ms"):
        naif = pd.Series([T0.tz_localize(None)]).astype(f"datetime64[{unite}]")
        assert abs(epoch(naif.dt.tz_localize("UTC"))[0] - attendu) < 1e-6


def test_aeroports_isoles():
    dep = _dep([("LFPG", 0.0)])
    arr = _arr([("EHAM", -5.0), ("EHAM", -40.0)])      # trafic observe ailleurs qu'a LFPG
    obs = observed_frame(dep, arr, dep)
    assert obs["obs_arr_90"][0] == 0
    assert np.isnan(obs["obs_arr_idle_min"][0])
