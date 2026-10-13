"""Contrat des données officielles (exécuté seulement si les données sont accessibles)."""

from __future__ import annotations

import pytest

pa = pytest.importorskip("pyarrow")
pc = pytest.importorskip("pyarrow.compute")
pq = pytest.importorskip("pyarrow.parquet")

from src.config import load_paths, training_file  # noqa: E402


@pytest.fixture(scope="module")
def paths():
    try:
        return load_paths()
    except FileNotFoundError:
        pytest.skip("données officielles non configurées (configs/paths.local.toml)")


def test_gabarit_final_aligne_sur_les_departements(paths) -> None:
    official = paths["_official"]
    tpl = pq.read_table(official / paths["data"]["final_template"]).to_pandas()
    ranking = pq.read_table(official / paths["data"]["final_inputs"], columns=["MVT_ID_mvt", "PHASE_mvt"])
    dep = set(ranking.filter(pc.equal(ranking["PHASE_mvt"], "DEP"))["MVT_ID_mvt"].to_pylist())
    assert list(tpl.columns) == ["MVT_ID_mvt", "TAXITIME_SEC_mvt"]
    assert len(tpl) == len(dep) == len(set(tpl["MVT_ID_mvt"]))
    assert set(tpl["MVT_ID_mvt"]) == dep


def test_cible_entrainement_presente(paths) -> None:
    table = pq.read_table(training_file(paths["_official"], "2025-03"), columns=["TAXITIME_SEC_mvt", "PHASE_mvt"])
    dep = table.filter(pc.equal(table["PHASE_mvt"], "DEP"))["TAXITIME_SEC_mvt"]
    assert dep.null_count == 0


def test_cible_masquee_dans_les_entrees_de_finale(paths) -> None:
    table = pq.read_table(paths["_official"] / paths["data"]["final_inputs"],
                          columns=["PHASE_mvt", "TAXITIME_SEC_mvt", "BLOCK_TIME_UTC_mvt"])
    dep = table.filter(pc.equal(table["PHASE_mvt"], "DEP"))
    assert dep["TAXITIME_SEC_mvt"].null_count == dep.num_rows
    assert dep["BLOCK_TIME_UTC_mvt"].null_count == dep.num_rows


def test_identifiants_uniques_2025(paths) -> None:
    seen = set()
    for month in ("2025-04", "2025-05"):
        table = pq.read_table(training_file(paths["_official"], month), columns=["MVT_ID_mvt"])
        ids = set(table["MVT_ID_mvt"].to_pylist())
        assert not (seen & ids)
        seen |= ids
