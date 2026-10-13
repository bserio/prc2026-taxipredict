"""Analyse des variantes d'audit D-035 : cout reel de retirer le poste, puis LOBT.

Trois lectures complementaires, contre la recette gelee `causal-r2` :
  1. par mois tenu hors (le critere D-029 porte sur les quatre mois cibles) ;
  2. janvier + juillet combines — ce sont les deux mois que note le classement officiel ;
  3. par tranche de duree reelle, pour separer le ventre de la distribution des anomalies.

Le bootstrap apparie est calcule dans le sens variante/reference : un rapport > 1 signifie une PERTE
(ici on mesure un cout, pas un gain).

Usage : PYTHONPATH=. .venv/bin/python scripts/d035_sensitivity.py [n_bootstrap]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REFERENCE = "reports/causal-r2.json"
VARIANTES = {"sans poste": "reports/causal-r10-nostand.json", "sans LOBT": "reports/causal-r11-nolobt.json"}
NOTES = ("2025-01", "2025-07")
TRANCHES = ((0, 1200, "0-20 min"), (1200, 2400, "20-40 min"), (2400, 3600, "40-60 min"),
            (3600, np.inf, "> 60 min"))


def charger(chemin: str) -> pd.DataFrame:
    p = Path(chemin).with_name(Path(chemin).stem + ".eval.parquet")
    return pd.read_parquet(p)


def rmse(d: pd.DataFrame) -> float:
    return float(np.sqrt(np.mean((d["pred"] - d["target"]) ** 2)))


def bootstrap(j: pd.DataFrame, n: int, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    dv = (j.p_v - j.y) ** 2
    dr = (j.p_r - j.y) ** 2
    groupes = [np.flatnonzero((j["month"] == m).to_numpy()) for m in sorted(j["month"].unique())]
    r = np.empty(n)
    for i in range(n):
        s = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groupes])
        r[i] = float(np.sqrt(dv[s].mean()) / np.sqrt(dr[s].mean()))
    return float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    ref = charger(REFERENCE)
    print(f"reference : {REFERENCE}  ({len(ref):,} lignes, RMSE {rmse(ref):.1f} s)\n")
    for nom, chemin in VARIANTES.items():
        var = charger(chemin)
        v_mois = {r["month"]: float(r["rmse"]) for r in json.loads(Path(chemin).read_text())["by_month"]}
        r_mois = {r["month"]: float(r["rmse"]) for r in json.loads(Path(REFERENCE).read_text())["by_month"]}
        print(f"=== {nom} ({chemin})")
        for m in sorted(r_mois):
            print(f"   {m} : {r_mois[m]:7.1f} -> {v_mois[m]:7.1f} s  ({100 * (v_mois[m] / r_mois[m] - 1):+5.2f} %)")
        j = (var[["MVT_ID_mvt", "month", "pred", "target"]].rename(columns={"pred": "p_v", "target": "y"})
             .merge(ref[["MVT_ID_mvt", "month", "pred"]].rename(columns={"pred": "p_r"}),
                    on=["MVT_ID_mvt", "month"], how="inner"))
        notes = j[j.month.isin(NOTES)]
        a = float(np.sqrt(np.mean((notes.p_v - notes.y) ** 2)))
        b = float(np.sqrt(np.mean((notes.p_r - notes.y) ** 2)))
        ic = bootstrap(j, n)
        print(f"   janv.+juil. combines : {b:.1f} -> {a:.1f} s  ({100 * (a / b - 1):+5.2f} %)")
        print(f"   global 4 mois        : {rmse(ref):.1f} -> {rmse(var):.1f} s  "
              f"({100 * (rmse(var) / rmse(ref) - 1):+5.2f} %)")
        print(f"   bootstrap apparie (variante/reference, {n} tirages) : IC95 [{ic[0]:.4f} ; {ic[1]:.4f}] "
              f"-> {'perte etablie' if ic[0] > 1 else ('gain etabli' if ic[1] < 1 else 'non departageable')}")
        print("   par tranche de duree reelle (sur les lignes appariees) :")
        for lo, hi, lib in TRANCHES:
            t = j[j.y.ge(lo) & j.y.lt(hi)]
            if not len(t):
                continue
            r = float(np.sqrt(np.mean((t.p_r - t.y) ** 2)))
            v = float(np.sqrt(np.mean((t.p_v - t.y) ** 2)))
            print(f"      {lib:9s} {100 * len(t) / len(j):5.2f} % des lignes   {r:7.1f} -> {v:7.1f} s  "
                  f"({100 * (v / r - 1):+6.2f} %)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
