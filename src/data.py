"""Chargement mutualisé des données officielles (lecture seule) avec cache de projection."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.config import load_paths, training_file
from src.prepare import load_arr, load_dep


def _cache_key(path: Path, tag: str) -> str:
    st = path.stat()
    raw = f"{path}|{st.st_size}|{int(st.st_mtime)}|{tag}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _cached(path: Path, tag: str, loader, tmp_dir: Path) -> pd.DataFrame:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / f"{tag}-{_cache_key(path, tag)}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    df = loader(path)
    df.to_parquet(out, index=False)
    return df


_MEMORY: dict[tuple[str, str], pd.DataFrame] = {}


def _dep_month(month: str, tmp_dir: Path) -> pd.DataFrame:
    key = (month, "dep")
    if key not in _MEMORY:                            # evite de relire 11 mois a chaque pli
        path = training_file(load_paths()["_official"], month)
        _MEMORY[key] = _cached(path, f"dep-{month}", lambda p: load_dep(p, month), tmp_dir)
    return _MEMORY[key]


def _arr_month(month: str, tmp_dir: Path) -> pd.DataFrame:
    key = (month, "arr")
    if key not in _MEMORY:
        path = training_file(load_paths()["_official"], month)
        _MEMORY[key] = _cached(path, "arr", load_arr, tmp_dir).assign(month=month)
    return _MEMORY[key]


def dep_for_months(months, paths: dict | None = None, tmp_dir: Path | None = None) -> pd.DataFrame:
    paths = paths or load_paths()
    tmp_dir = tmp_dir or Path(paths["write"]["tmp"])
    return pd.concat([_dep_month(m, tmp_dir) for m in months], ignore_index=True)


def arr_for_months(months, paths: dict | None = None, tmp_dir: Path | None = None) -> pd.DataFrame:
    paths = paths or load_paths()
    tmp_dir = tmp_dir or Path(paths["write"]["tmp"])
    return pd.concat([_arr_month(m, tmp_dir) for m in months], ignore_index=True)


def final_frames(paths: dict | None = None, tmp_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Entrées officielles de la finale 2026 : (départs, arrivées)."""
    paths = paths or load_paths()
    tmp_dir = tmp_dir or Path(paths["write"]["tmp"])
    path = paths["_official"] / paths["data"]["final_inputs"]
    dep = _cached(path, "final-dep", lambda p: load_dep(p, None), tmp_dir)
    arr = _cached(path, "final-arr", lambda p: load_arr(p), tmp_dir)
    return dep, arr


def template(paths: dict | None = None) -> pd.DataFrame:
    paths = paths or load_paths()
    return pd.read_parquet(paths["_official"] / paths["data"]["final_template"])
