"""Fixtures synthétiques : jamais un benchmark, jamais un score PRC."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

AP = ["EDDF", "LIRF"]


def _dt(base: pd.Timestamp, seconds) -> pd.Series:
    return pd.Series(base, index=range(len(seconds))) + pd.to_timedelta(np.asarray(seconds), unit="s")


def make_dep(n: int = 400, seed: int = 0, month: str = "2025-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2025-01-05 06:00:00", tz="UTC")
    sched = _dt(base, rng.integers(0, 20 * 3600, n))
    block = sched + pd.to_timedelta(rng.integers(0, 900, n), unit="s")
    takeoff = block + pd.to_timedelta(rng.integers(300, 2400, n), unit="s")
    aobt = block + pd.to_timedelta(rng.integers(-300, 600, n), unit="s")
    return pd.DataFrame({
        "MVT_ID_mvt": np.arange(n, dtype="float64"),
        "ADEP_mvt": rng.choice(AP, n).astype(object),
        "ADES_mvt": (["LFPG"] * n).copy(),
        "PHASE_mvt": (["DEP"] * n).copy(),
        "MVT_TIME_UTC_mvt": takeoff, "BLOCK_TIME_UTC_mvt": block, "SCHED_TIME_UTC_mvt": sched,
        "AIRCRAFT_TYPE_mvt": rng.choice(["A20N", "B738"], n).astype(object),
        "RUNWAY_mvt": rng.choice(["25C", "18"], n).astype(object),
        "STAND_mvt": rng.choice(["A10", "B42", "C7"], n).astype(object),
        "TAXITIME_SEC_mvt": (takeoff - block).dt.total_seconds().astype("int32").to_numpy(),
        "FLIGHT_RULE_mvt": (["I"] * n).copy(),
        "LOBT_flt": sched + pd.Timedelta(minutes=5), "IOBT_flt": sched,
        "ADES_FILED_flt": (["LFPG"] * n).copy(),
        "MARKET_SEGMENT_flt": rng.choice(["Mainline", "Low-Cost"], n).astype(object),
        "EOBT_1_flt": sched + pd.Timedelta(minutes=5),
        "FLIGHT_RULE_flt": (["I"] * n).copy(), "FLIGHT_TYPE_flt": (["S"] * n).copy(),
        "AIRCRAFT_TYPE_flt": rng.choice(["A20N", "B738"], n).astype(object),
        "WK_TBL_CAT_flt": rng.choice(["M", "H"], n).astype(object),
        "AIRCRAFT_OPERATOR_flt": rng.choice(["DLH", "AFR", "RYR"], n).astype(object),
        "AOBT_3_flt": aobt,
        "month": ([month] * n).copy(),
    })


def make_arr(n: int = 300, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2025-01-05 05:00:00", tz="UTC")
    sched = _dt(base, rng.integers(0, 20 * 3600, n))
    land = sched + pd.to_timedelta(rng.integers(-600, 900, n), unit="s")
    return pd.DataFrame({
        "ADES_mvt": rng.choice(AP, n).astype(object),
        "MVT_TIME_UTC_mvt": land, "SCHED_TIME_UTC_mvt": sched,
        "RUNWAY_mvt": rng.choice(["25C", "18"], n).astype(object),
        "STAND_mvt": rng.choice(["A10", "B42", "C7"], n).astype(object),
        "TAXITIME_SEC_mvt": rng.integers(300, 1500, n).astype("int32"),
        "PHASE_mvt": (["ARR"] * n).copy(),
    })


@pytest.fixture
def dep_train() -> pd.DataFrame:
    return make_dep(400, seed=0)


@pytest.fixture
def dep_val() -> pd.DataFrame:
    return make_dep(120, seed=7)


@pytest.fixture
def arr_train() -> pd.DataFrame:
    return make_arr(300, seed=1)
