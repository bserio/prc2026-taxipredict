"""Garde-fous de l'ouverture de la réserve et post-traitement de sortie."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from src.evaluate_reserved import main
from src.predict import finalise


def _argv(*extra: str) -> list[str]:
    return ["evaluate_reserved.py", *extra]


def test_refus_sans_confirmation_explicite(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", _argv("--tracks", "causal", "--model-dir", "x", "--run-id", "t"))
    with pytest.raises(SystemExit) as exc:
        main()
    assert "--confirm-reserve" in str(exc.value)


def test_recette_inconnue_refusee(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", _argv("--tracks", "causal,magique", "--model-dir", "x",
                                           "--run-id", "t", "--confirm-reserve"))
    with pytest.raises(SystemExit) as exc:
        main()
    assert "inconnues" in str(exc.value)


def test_residuel_exige_un_repli(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", _argv("--tracks", "residual", "--residual-dir", "x",
                                           "--run-id", "t", "--confirm-reserve"))
    with pytest.raises(SystemExit) as exc:
        main()
    assert "repli" in str(exc.value)


def test_seconde_ouverture_refusee(monkeypatch, tmp_path: Path) -> None:
    marker = tmp_path / "RESERVE_OPENED.json"
    marker.write_text(json.dumps({"horodatage": "2026-10-10T05:00:00"}), encoding="utf-8")
    monkeypatch.setattr("src.evaluate_reserved.load_paths",
                        lambda: {"write": {"reports": str(tmp_path)}})
    monkeypatch.setattr(sys, "argv", _argv("--tracks", "causal", "--model-dir", "x",
                                           "--run-id", "t", "--confirm-reserve"))
    with pytest.raises(SystemExit) as exc:
        main()
    assert "déjà ouverte" in str(exc.value)


def test_le_plancher_conserve_les_grandes_valeurs() -> None:
    """D-019 : plancher a 0, aucun plafond."""
    p = finalise(np.array([-500.0, 12.4, 90_000.3, np.nan]))
    assert p[0] == 0.0 and p[1] == 12.0
    assert p[2] == 90_000.0                      # rien n'est ecrete en haut
    assert np.isfinite(p).all()
