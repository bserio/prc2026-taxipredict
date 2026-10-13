"""Le modèle causal ne doit dépendre d'aucune information postérieure à l'off-block."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features import FeatureSpec
from tests.conftest import make_arr, make_dep

FORBIDDEN = {"MVT_TIME_UTC_mvt", "AOBT_3_flt", "BLOCK_TIME_UTC_mvt", "TAXITIME_SEC_mvt"}


def y_of(df: pd.DataFrame) -> np.ndarray:
    return df["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")


def test_causal_aucune_colonne_interdite() -> None:
    spec = FeatureSpec(track="causal").fit(make_dep(), make_arr(), y_of(make_dep()))
    X = spec.transform(make_dep(seed=3), make_arr(seed=4))
    assert not (FORBIDDEN & set(X.columns))
    assert not any("proxy" in c or "aobt" in c.lower() or "mvt_time" in c for c in X.columns)


def test_causal_invariant_aux_colones_post_hoc() -> None:
    """Si une colonne postérieure influence la prédiction, ce test échoue."""
    train = make_dep(400, seed=0)
    val = make_dep(120, seed=7)
    spec = FeatureSpec(track="causal").fit(train, make_arr(), y_of(train))
    base = spec.transform(val, make_arr(seed=5)).to_numpy(dtype="float64")

    tampered = val.copy()
    tampered["MVT_TIME_UTC_mvt"] = tampered["MVT_TIME_UTC_mvt"] + pd.Timedelta(hours=9)
    tampered["AOBT_3_flt"] = tampered["BLOCK_TIME_UTC_mvt"] - pd.Timedelta(minutes=37)
    tampered["BLOCK_TIME_UTC_mvt"] = tampered["SCHED_TIME_UTC_mvt"] + pd.Timedelta(hours=4)
    after = spec.transform(tampered, make_arr(seed=5)).to_numpy(dtype="float64")
    np.testing.assert_allclose(base, after, equal_nan=True)


def test_hybrid_bien_sensible_au_proxy() -> None:
    """Contre-épreuve : la piste hybrid doit bouger si on modifie MVT_TIME."""
    train = make_dep(400, seed=0)
    val = make_dep(120, seed=7)
    spec = FeatureSpec(track="hybrid").fit(train, make_arr(), y_of(train))
    base = spec.transform(val, make_arr(seed=5))["proxy_sec"].to_numpy(dtype="float64")
    tampered = val.copy()
    tampered["MVT_TIME_UTC_mvt"] = tampered["MVT_TIME_UTC_mvt"] + pd.Timedelta(minutes=20)
    after = spec.transform(tampered, make_arr(seed=5))["proxy_sec"].to_numpy(dtype="float64")
    assert np.nanmax(np.abs(after - base)) > 1000


def test_encodages_ajustes_sur_le_train_seulement() -> None:
    train = make_dep(400, seed=0)
    val_a = make_dep(120, seed=7)
    spec_a = FeatureSpec(track="causal").fit(train, make_arr(), y_of(train))
    table_a = dict(spec_a.enc["te_ap_stand"][0])

    val_b = make_dep(120, seed=7)
    val_b["TAXITIME_SEC_mvt"] = (val_b["TAXITIME_SEC_mvt"].astype("int64") + 5000).astype("int32")
    spec_b = FeatureSpec(track="causal").fit(train, make_arr(), y_of(train))
    assert dict(spec_b.enc["te_ap_stand"][0]) == table_a


def test_piste_reelle_absente_du_causal() -> None:
    train, val = make_dep(), make_dep(120, seed=9)
    spec = FeatureSpec(track="causal", use_runway_actual=False).fit(train, make_arr(), y_of(train))
    cols = set(spec.transform(val, make_arr(seed=2)).columns)
    assert "c_RUNWAY_mvt" not in cols and "geo_act_total_sec" not in cols


def test_indicateur_de_regime_desactive_par_defaut() -> None:
    """Les recettes gelées ne doivent pas voir apparaître la colonne (D-025 refusée, D-028)."""
    train = make_dep(400, seed=0)
    for spec in (FeatureSpec(track="causal"), FeatureSpec(track="hybrid")):
        X = spec.fit(train, make_arr(), y_of(train)).transform(make_dep(120, seed=7), make_arr(seed=2))
        assert "regime_sans_reseau" not in X.columns


def test_indicateur_de_regime_signale_et_sans_fuite() -> None:
    """Activé, le drapeau marque les vols sans fiche réseau et ne dépend d'aucune donnée réalisée."""
    train = make_dep(400, seed=0)
    val = make_dep(120, seed=7)
    masque = np.zeros(len(val), dtype=bool)
    masque[::3] = True
    val.loc[masque, "EOBT_1_flt"] = pd.NaT

    spec = FeatureSpec(track="causal", use_regime_flag=True).fit(train, make_arr(), y_of(train))
    X = spec.transform(val, make_arr(seed=2))
    np.testing.assert_array_equal(X["regime_sans_reseau"].to_numpy(), masque.astype("int8"))

    tampered = val.copy()
    tampered["MVT_TIME_UTC_mvt"] = tampered["MVT_TIME_UTC_mvt"] + pd.Timedelta(hours=9)
    tampered["AOBT_3_flt"] = tampered["BLOCK_TIME_UTC_mvt"] - pd.Timedelta(minutes=37)
    apres = spec.transform(tampered, make_arr(seed=2))["regime_sans_reseau"].to_numpy()
    np.testing.assert_array_equal(apres, masque.astype("int8"))

    restaure = FeatureSpec.from_dict(spec.to_dict())
    assert restaure.use_regime_flag is True
