"""Chargement des configurations TOML et des chemins locaux."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(name: str) -> dict[str, Any]:
    path = Path(name)
    if not path.is_absolute():
        for candidate in (ROOT / name, CONFIGS / name, CONFIGS / f"{name}.toml"):
            if candidate.exists():
                path = candidate
                break
    if not path.exists():
        raise FileNotFoundError(f"config introuvable : {path}")
    return _read(path)


def load_paths() -> dict[str, Any]:
    """paths.local.toml (ignoré par Git) sinon paths.example.toml."""
    local = CONFIGS / "paths.local.toml"
    cfg = _read(local if local.exists() else CONFIGS / "paths.example.toml")
    official = Path(cfg["data"]["official_dir"]).expanduser()
    if not official.is_dir():
        raise FileNotFoundError(
            "official_dir introuvable : renseigner configs/paths.local.toml avec le chemin exact des données"
        )
    cfg["_official"] = official
    for key, sub in (("artifacts", "artifacts"), ("runs", "experiments/runs"),
                     ("reports", "reports"), ("submission", "submission"), ("tmp", "tmp")):
        cfg.setdefault("write", {})[key] = str(ROOT / sub)
    return cfg


def training_file(official_dir: Path, month: str, pattern: str = "training_*.parquet") -> Path:
    """month = 'YYYY-MM'. Le fichier mensuel officiel est l'unité de partition."""
    year, mm = month.split("-")
    matches = sorted(official_dir.glob(f"training_{year}-{mm}-01_*.parquet"))
    if len(matches) != 1:
        raise FileNotFoundError(f"{len(matches)} fichier(s) pour le mois {month} dans {official_dir}")
    return matches[0]


def fingerprint_file(root: Path, run_id: str) -> Path:
    return root / "reports" / f"{run_id}.fingerprint.json"
