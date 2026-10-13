"""Taux d'absence par colonne, sur les mois de developpement 2025 et sur les entrees officielles 2026.

Reproduit la table de `docs/T0_DISPONIBILITE.md` (section 2). Lecture seule ; aucun ecrit ailleurs
que la sortie standard.

Usage : PYTHONPATH=. .venv/bin/python scripts/null_rates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src import data as D  # noqa: E402
from src.config import load_config  # noqa: E402
from src.splits import Protocol  # noqa: E402

CHAMPS = [
    "LOBT_flt", "IOBT_flt", "EOBT_1_flt", "ADES_FILED_flt", "MARKET_SEGMENT_flt", "FLIGHT_RULE_flt",
    "FLIGHT_TYPE_flt", "AIRCRAFT_TYPE_flt", "WK_TBL_CAT_flt", "AIRCRAFT_OPERATOR_flt", "AOBT_3_flt",
    "ADEP_mvt", "STAND_mvt", "AIRCRAFT_TYPE_mvt", "FLIGHT_RULE_mvt", "SCHED_TIME_UTC_mvt", "RUNWAY_mvt",
]


def main() -> int:
    prot = Protocol.from_config(load_config("splits.toml"))
    dev = D.dep_for_months(list(prot.dev_val_months), None)
    off, _ = D.final_frames()
    sans_flt = [c for c in CHAMPS if c.endswith("_flt")]

    print(f"{'colonne':24s} {'dev 2025':>10s} {'officiel 2026':>14s}")
    for c in CHAMPS:
        a = dev[c].isna().mean() * 100 if c in dev.columns else float("nan")
        b = off[c].isna().mean() * 100 if c in off.columns else float("nan")
        print(f"{c:24s} {a:9.3f}% {b:13.3f}%")

    present = [c for c in sans_flt if c in dev.columns]
    p_dev = dev[present].isna().all(axis=1).mean() * 100
    p_off = off[[c for c in present if c in off.columns]].isna().all(axis=1).mean() * 100
    print(f"\nlignes ou TOUTES les colonnes _flt manquent a la fois : dev {p_dev:.2f} % | officiel {p_off:.2f} %")
    print("(ce sont les memes lignes pour chaque colonne : l'absence est une propriete de la ligne, "
          "pas une qualite inegale des champs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
