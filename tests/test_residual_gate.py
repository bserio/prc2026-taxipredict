"""Non-régression de la porte résiduelle : les masques doivent rester unidimensionnels."""

from __future__ import annotations

import numpy as np
import pytest

from src.residual import id_bucket


def test_forme_du_pli_deterministe() -> None:
    ids = np.array([10.0, 11.0, 12.0, 13.0])
    bucket = id_bucket(ids)
    assert bucket.shape == (4,)
    assert list(bucket) == [0, 1, 2, 3]
    assert np.array_equal(bucket, id_bucket(ids))          # même affectation à chaque exécution


def test_le_masque_ne_se_diffuse_pas_en_matrice() -> None:
    """Le bogue d'origine : un hash en (N, 1) diffusait le masque en N x N (des centaines de Go)."""
    n = 5_000
    ids = np.arange(n, dtype="float64")
    usable = np.ones(n, dtype=bool)
    finite = np.ones(n, dtype=bool)
    mask = (id_bucket(ids) != 0) & usable & finite
    assert mask.ndim == 1 and mask.shape == (n,)


def test_identifiants_invalides_rejetes() -> None:
    with pytest.raises(ValueError):
        id_bucket(np.array([np.nan]))
    with pytest.raises(ValueError):
        id_bucket(np.zeros((3, 1)))
