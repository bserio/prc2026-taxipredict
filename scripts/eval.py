#!/usr/bin/env python
"""Sortie de score pour Arbor : une ligne `SCORE: <RMSE en secondes>`.

Lit un rapport de run déjà produit (aucun réentraînement implicite, aucune ouverture
de réserve) : la commande d'évaluation reste déterministe et séparée des décisions.

    python scripts/eval.py --run-id causal-r1            # dév
    python scripts/eval.py --run-id reserved-causal --split reserved
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_paths  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--split", default="dev", choices=["dev", "reserved"])
    args = ap.parse_args()

    reports = Path(load_paths()["write"]["reports"])
    path = reports / f"{args.run_id}.json"
    if not path.exists():
        print(f"ERREUR: rapport introuvable {path}", file=sys.stderr)
        return 2
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("split") != args.split:
        print(f"ERREUR: le run {args.run_id} porte split={report.get('split')} et non {args.split}", file=sys.stderr)
        return 2
    value = report["global"]["rmse"]
    if not isinstance(value, (int, float)):
        print("ERREUR: pas de score exploitable", file=sys.stderr)
        return 3
    print(f"split={report['split']} n={report['global']['n_rows']} mae={report['global']['mae']:.1f} "
          f"bias={report['global']['bias']:.1f}")
    print(f"SCORE: {value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
