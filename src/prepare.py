"""Lecture des données officielles en lecture seule, avec cache local des projections.

Aucune donnée officielle n'est modifiée, renommée ou déplacée : le cache écrit
uniquement dans tmp/ des projections réduites utilisées par le pipeline.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

DEP_COLS = [
    "MVT_ID_mvt", "ADEP_mvt", "ADES_mvt", "PHASE_mvt", "MVT_TIME_UTC_mvt", "BLOCK_TIME_UTC_mvt",
    "SCHED_TIME_UTC_mvt", "AIRCRAFT_TYPE_mvt", "RUNWAY_mvt", "STAND_mvt", "TAXITIME_SEC_mvt",
    "FLIGHT_RULE_mvt", "LOBT_flt", "IOBT_flt", "ADES_FILED_flt", "MARKET_SEGMENT_flt",
    "EOBT_1_flt", "FLIGHT_RULE_flt", "FLIGHT_TYPE_flt", "AIRCRAFT_TYPE_flt", "WK_TBL_CAT_flt",
    "AIRCRAFT_OPERATOR_flt", "AOBT_3_flt",
]
ARR_COLS = [
    "ADES_mvt", "MVT_TIME_UTC_mvt", "SCHED_TIME_UTC_mvt", "RUNWAY_mvt", "STAND_mvt",
    "TAXITIME_SEC_mvt", "PHASE_mvt",
]
STR_COLS_DEP = ["ADEP_mvt", "ADES_mvt", "AIRCRAFT_TYPE_mvt", "RUNWAY_mvt", "STAND_mvt",
                "FLIGHT_RULE_mvt", "MARKET_SEGMENT_flt", "FLIGHT_RULE_flt", "FLIGHT_TYPE_flt",
                "AIRCRAFT_TYPE_flt", "WK_TBL_CAT_flt", "AIRCRAFT_OPERATOR_flt", "ADES_FILED_flt"]


def _to_str(df: pd.DataFrame, cols) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = df[col].astype("object")
    return df


def _read(path: Path, cols, phase: str | None) -> pd.DataFrame:
    table = pq.read_table(path, columns=cols)
    if phase is not None:
        table = table.filter(pc.equal(table["PHASE_mvt"], phase))
    return table.to_pandas()


def load_dep(path: Path, month: str | None = None, cache: Path | None = None) -> pd.DataFrame:
    df = _read(path, DEP_COLS, "DEP")
    df = _to_str(df, STR_COLS_DEP)
    for col in ("MVT_TIME_UTC_mvt", "BLOCK_TIME_UTC_mvt", "SCHED_TIME_UTC_mvt",
                "LOBT_flt", "IOBT_flt", "EOBT_1_flt", "AOBT_3_flt"):
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601", errors="coerce")
    if month is None:  # fichier mixte (finale) : mois déduit du temps de mouvement
        month_series = pd.to_datetime(df["MVT_TIME_UTC_mvt"], utc=True).dt.strftime("%Y-%m")
        df["month"] = month_series.astype("object")
    else:
        df["month"] = month
    return df.reset_index(drop=True)


def load_arr(path: Path, cache: Path | None = None) -> pd.DataFrame:
    df = _read(path, ARR_COLS, "ARR")
    for col in ("ADES_mvt", "RUNWAY_mvt", "STAND_mvt"):
        df[col] = df[col].astype("object")
    for col in ("MVT_TIME_UTC_mvt", "SCHED_TIME_UTC_mvt"):
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601", errors="coerce")
    return df.reset_index(drop=True)


def slot(epoch_s: np.ndarray, width_s: int = 900) -> np.ndarray:
    """Indice de créneau (demi-quart d'heure par défaut)."""
    return np.floor(np.asarray(epoch_s, dtype="float64") / width_s).astype("int64")


_EPOCH_REF = pd.Timestamp("1970-01-01", tz="UTC")


def epoch(dt: pd.Series) -> np.ndarray:
    """Secondes depuis l'epoch, independamment de la resolution du dtype (ns/us/ms).

    Correction (D-034) : `astype("int64")/1e9` supposait une resolution nanoseconde. Les colonnes
    parsees ici arrivent en datetime64[us] -> le resultat etait en millisecondes, ce qui reduisait
    `slot()` a quelques buckets par mois et rendait les compteurs de congestion inoffensifs mais
    inutiles. `total_seconds()` est exact quelle que soit la resolution.
    """
    s = pd.to_datetime(dt, utc=True)
    out = np.array((s - _EPOCH_REF).dt.total_seconds(), dtype="float64", copy=True)
    out[np.asarray(pd.isna(s))] = np.nan
    return out


def diff_minutes(a: pd.Series, b: pd.Series) -> np.ndarray:
    """(a - b) en minutes, NaN si l'un des deux horodatages manque."""
    d = (pd.to_datetime(a, utc=True) - pd.to_datetime(b, utc=True)).dt.total_seconds().to_numpy(dtype="float64") / 60.0
    return d


def clip_finite(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out = np.where(np.isfinite(x), x, np.nan)
    return np.clip(out, lo, hi)
