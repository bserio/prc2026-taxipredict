"""Applique la regle d'adoption pre-enregistree (D-025 seuil simple, D-029 seuil + bootstrap).

D-029 (defaut) : (1) RMSE inferieure d'au moins SEUIL_pct % sur CHACUN des quatre mois cibles,
sur 100 % des lignes ; (2) bootstrap apparie par ligne dont l'intervalle exclut 1. Les deux a la fois.
D-025 (historique, --seuil 2 --bootstrap 0) : la condition (1) seule a 2 %.

Usage : python scripts/check_adoption.py reports/residual-r5-spec-raw.json reports/residual-r1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEUIL_PCT = 1.0   # D-029 ; les essais de D-025 avaient ete juges a 2 %
MOIS_CIBLES = ("2025-01", "2025-02", "2025-06", "2025-07")


def par_mois(chemin: Path) -> tuple[dict[str, float], float, int]:
    rapport = json.loads(chemin.read_text(encoding="utf-8"))
    mois = {r["month"]: float(r["rmse"]) for r in rapport["by_month"]}
    return mois, float(rapport["global"]["rmse"]), int(rapport["global"]["n_rows"])


def bootstrap_apparie(variante: Path, reference: Path, mois: tuple[str, ...], n: int,
                      seed: int = 7) -> tuple[float, float] | None:
    """Intervalle à 95 % du rapport RMSE(variante)/RMSE(reference), apparié par ligne (D-029).

    On ré-échantillonne les LIGNES (à l'intérieur de chaque mois) et on recalcule les deux RMSE sur le
    même tirage : le bruit commun aux deux recettes s'annule, ce qui reste est bien la question posée.
    """
    import numpy as np
    import pandas as pd

    def parquet_de(chemin: Path) -> Path:
        rapport = Path(chemin)
        return rapport.with_name(rapport.stem + ".eval.parquet") if rapport.suffix == ".json" else rapport

    try:
        v = pd.read_parquet(parquet_de(variante))
        r = pd.read_parquet(parquet_de(reference))
    except Exception as exc:                                   # outillage : on refuse de conclure, pas de planter
        print(f"   (bootstrap non calculable : {exc})")
        return None
    cle = ["MVT_ID_mvt", "month"]
    if not set(cle) <= set(v.columns) or not set(r.columns) >= set(cle) or "pred" not in v.columns or "pred" not in r.columns:
        return None
    if "target" not in v.columns:
        return None
    j = (v[cle + ["pred", "target"]].rename(columns={"pred": "p_v", "target": "y"})
         .merge(r[cle + ["pred"]].rename(columns={"pred": "p_r"}), on=cle, how="inner"))
    j = j[j["month"].isin(mois)]
    if len(j) < 10_000:
        return None

    rng = np.random.default_rng(seed)
    dv = (j["p_v"].to_numpy("float64") - j["y"].to_numpy("float64")) ** 2
    dr = (j["p_r"].to_numpy("float64") - j["y"].to_numpy("float64")) ** 2
    groupes = [np.flatnonzero((j["month"] == m).to_numpy()) for m in mois]
    ratios = np.empty(n, dtype="float64")
    for i in range(n):
        sv = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groupes])
        ratios[i] = float(np.sqrt(dv[sv].mean()) / np.sqrt(dr[sv].mean()))
    return float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variante")
    ap.add_argument("reference")
    ap.add_argument("--seuil", type=float, default=SEUIL_PCT)
    ap.add_argument("--bootstrap", type=int, default=2000, help="0 pour désactiver (D-029)")
    args = ap.parse_args()

    v_mois, v_glob, v_lignes = par_mois(Path(args.variante))
    r_mois, r_glob, r_lignes = par_mois(Path(args.reference))
    if v_lignes != r_lignes:
        print(f"ATTENTION : populations differentees ({v_lignes} vs {r_lignes} lignes) -> comparaison invalide")

    manquants = [m for m in MOIS_CIBLES if m not in v_mois or m not in r_mois]
    if manquants:
        print(f"ATTENTION : mois manquants {manquants} -> la regle exige les quatre mois cibles")

    print(f"{'mois':10s} {'reference':>10s} {'variante':>10s} {'ecart':>9s}  regle (<= -{args.seuil:.0f} %)")
    conformes = []
    for m in MOIS_CIBLES:
        if m in v_mois and m in r_mois:
            ecart = 100.0 * (v_mois[m] / r_mois[m] - 1.0)
            ok = ecart <= -args.seuil
            conformes.append(ok)
            print(f"{m:10s} {r_mois[m]:10.1f} {v_mois[m]:10.1f} {ecart:+8.2f} %  {'OK' if ok else 'REFUS'}")
    for m in sorted(set(v_mois) - set(MOIS_CIBLES)):
        ecart = 100.0 * (v_mois[m] / r_mois[m] - 1.0) if m in r_mois else float("nan")
        print(f"{m:10s} {r_mois.get(m, float('nan')):10.1f} {v_mois[m]:10.1f} {ecart:+8.2f} %  (hors regle)")

    ec_glob = 100.0 * (v_glob / r_glob - 1.0)
    print(f"{'GLOBAL':10s} {r_glob:10.1f} {v_glob:10.1f} {ec_glob:+8.2f} %")

    condition_1 = len(conformes) == len(MOIS_CIBLES) and all(conformes)
    condition_2, ic_texte = True, "bootstrap desactive"
    if args.bootstrap:
        ic = bootstrap_apparie(Path(args.variante), Path(args.reference), MOIS_CIBLES, args.bootstrap)
        if ic is None:
            condition_2 = False
            ic_texte = "bootstrap IMPOSSIBLE (parquets d'evaluation absents ou trop petits) -> gain non etabli"
        else:
            condition_2 = ic[1] < 1.0
            ic_texte = (f"rapport de RMSE IC95 [{ic[0]:.4f} ; {ic[1]:.4f}] -> "
                        f"{'exclut 1 (gain constant)' if condition_2 else 'contient 1 (non etabli)'}")
    print(f"condition 1 (D-029) : -{args.seuil:.0f} % sur les {len(MOIS_CIBLES)} mois cibles -> "
          f"{'OK' if condition_1 else 'REFUS'} ({sum(conformes)}/{len(MOIS_CIBLES)})")
    print(f"condition 2 (D-029) : {ic_texte} -> {'OK' if condition_2 else 'REFUS'}")
    adoptee = condition_1 and condition_2
    print(f"\n{'ADOPTABLE' if adoptee else 'REFUSEE'} au sens de D-029 (les deux conditions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
