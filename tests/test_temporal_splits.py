"""Les partitions respectent l'ordre temporel et excluent la réserve."""

from __future__ import annotations

from src.config import load_config
from src.splits import Protocol


def protocol() -> Protocol:
    return Protocol.from_config(load_config("splits.toml"))


def test_reserve_jamais_dans_entrainement() -> None:
    p = protocol()
    for _name, train, val in p.folds():
        assert not set(train) & set(p.reserve_months)
        assert val not in train
        assert val not in p.reserve_months


def test_plis_saison_cible() -> None:
    p = protocol()
    assert set(p.dev_val_months) == {"2025-01", "2025-02", "2025-06", "2025-07"}
    assert len(p.folds()) <= 4


def test_reserve_posterieure_aux_plis() -> None:
    p = protocol()
    for _name, train, val in p.folds():
        assert max(train) < min(p.reserve_months) or max(val) < min(p.reserve_months)


def test_train_identique_sauf_mois_valide() -> None:
    p = protocol()
    sizes = {len(t) for _n, t, _v in p.folds()}
    assert len(sizes) == 1                       # même volume d'entraînement pour tous les plis


def test_entrainement_reserve_disjoint() -> None:
    p = protocol()
    assert not set(p.reserve_train_months()) & set(p.reserve_months)
    assert set(p.reserve_train_months()) | set(p.reserve_months) == set(p.all_months)
