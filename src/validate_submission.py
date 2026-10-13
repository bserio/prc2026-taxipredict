"""Contrôles de conformité d'un fichier de soumission avant tout dépôt.

    python -m src.validate_submission --file submission/sub-causal-v1.parquet

Échec (code 2) si : identifiants différents du gabarit, lignes manquantes ou en trop,
doublons, types incompatibles, valeurs non finies. Erreurs listées explicitement ;
le script relit le fichier écrit depuis le disque et n'utilise jamais l'objet mémoire.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_paths


def check(path: Path, template: pd.DataFrame) -> dict:
    sub = pd.read_parquet(path)
    report: dict = {"fichier": str(path), "erreurs": [], "avertissements": []}
    if list(sub.columns) != list(template.columns):
        report["erreurs"].append(f"colonnes {list(sub.columns)} != gabarit {list(template.columns)}")
    if len(sub) != len(template):
        report["erreurs"].append(f"{len(sub)} lignes != {len(template)} lignes du gabarit")

    ids_sub = sub.get("MVT_ID_mvt", pd.Series(dtype="float64")).to_numpy(dtype="float64")
    ids_tpl = template["MVT_ID_mvt"].to_numpy(dtype="float64")
    if len(ids_sub) and not np.array_equal(ids_sub, ids_tpl):
        missing = set(ids_tpl.tolist()) - set(ids_sub.tolist())
        extra = set(ids_sub.tolist()) - set(ids_tpl.tolist())
        report["erreurs"].append(f"identifiants non alignés : manquants={len(missing)} en_plus={len(extra)} "
                                 f"(ordre différent)" if not (missing or extra) else
                                 f"identifiants absents du gabarit : manquants={len(missing)} en_plus={len(extra)}")
    dup = int(pd.Series(ids_sub).duplicated().sum())
    if dup:
        report["erreurs"].append(f"{dup} identifiants en double")

    if sub["MVT_ID_mvt"].dtype != template["MVT_ID_mvt"].dtype:
        report["avertissements"].append(f"dtype MVT_ID {sub['MVT_ID_mvt'].dtype} != gabarit {template['MVT_ID_mvt'].dtype}")
    if sub["TAXITIME_SEC_mvt"].dtype != template["TAXITIME_SEC_mvt"].dtype:
        report["avertissements"].append(f"dtype TAXITIME {sub['TAXITIME_SEC_mvt'].dtype} != gabarit "
                                        f"{template['TAXITIME_SEC_mvt'].dtype}")

    values = sub["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    n_nonfinite = int(np.sum(~np.isfinite(values)))
    if n_nonfinite:
        report["erreurs"].append(f"{n_nonfinite} valeurs non finies")
    n_neg = int(np.nansum(values < 0))
    if n_neg:
        report["avertissements"].append(f"{n_neg} valeurs négatives (physiquement impossible)")
    report["statistiques"] = {"n": int(len(values)), "min": float(np.nanmin(values)) if len(values) else None,
                              "median": float(np.nanmedian(values)) if len(values) else None,
                              "max": float(np.nanmax(values)) if len(values) else None,
                              "n_over_7200": int(np.nansum(values > 7200))}
    report["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    args = ap.parse_args()
    paths = load_paths()
    template = pd.read_parquet(paths["_official"] / paths["data"]["final_template"])
    report = check(Path(args.file), template)
    print(json.dumps(report, indent=1))
    if report["erreurs"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
