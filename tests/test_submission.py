"""Contrôle de conformité d'une soumission (fixtures synthétiques)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.validate_submission import check


@pytest.fixture
def template() -> pd.DataFrame:
    return pd.DataFrame({"MVT_ID_mvt": np.array([1.0, 2.0, 3.0]),
                         "TAXITIME_SEC_mvt": np.array([0, 0, 0], dtype="int32")})


def _write(tmp_path, df):
    path = tmp_path / "sub.parquet"
    df.to_parquet(path, index=False)
    return path


def test_conforme(tmp_path, template) -> None:
    sub = pd.DataFrame({"MVT_ID_mvt": template["MVT_ID_mvt"],
                        "TAXITIME_SEC_mvt": np.array([600, 700, 800], dtype="int32")})
    report = check(_write(tmp_path, sub), template)
    assert report["erreurs"] == []
    assert report["statistiques"]["n"] == 3


def test_ligne_manquante_identifiant(tmp_path, template) -> None:
    sub = pd.DataFrame({"MVT_ID_mvt": np.array([1.0, 2.0, 99.0]),
                        "TAXITIME_SEC_mvt": np.array([600, 700, 800], dtype="int32")})
    report = check(_write(tmp_path, sub), template)
    assert any("manquants=1" in e and "en_plus=1" in e for e in report["erreurs"])


def test_valeur_non_finie(tmp_path, template) -> None:
    sub = pd.DataFrame({"MVT_ID_mvt": template["MVT_ID_mvt"],
                        "TAXITIME_SEC_mvt": np.array([600.0, np.nan, 800.0])})
    report = check(_write(tmp_path, sub), template)
    assert any("non finies" in e for e in report["erreurs"])


def test_negatif_signale(tmp_path, template) -> None:
    sub = pd.DataFrame({"MVT_ID_mvt": template["MVT_ID_mvt"],
                        "TAXITIME_SEC_mvt": np.array([-5, 700, 800], dtype="int32")})
    report = check(_write(tmp_path, sub), template)
    assert any("négatives" in a for a in report["avertissements"])


def test_doublons_signales(tmp_path, template) -> None:
    sub = pd.DataFrame({"MVT_ID_mvt": np.array([1.0, 1.0, 3.0]),
                        "TAXITIME_SEC_mvt": np.array([600, 700, 800], dtype="int32")})
    report = check(_write(tmp_path, sub), template)
    assert any("double" in e for e in report["erreurs"])
