#!/usr/bin/env python3
"""Contrôle de conformité de la piste causale : prouver plutôt qu'affirmer.

On fabrique les variables et les prédictions deux fois sur un échantillon de départs :

    1. entrées telles que fournies par l'organisateur ;
    2. mêmes entrées, en **bouchant** les trois informations qui ne seraient connues qu'après le
       poussage : heure de décollage réalisée (`MVT_TIME_UTC_mvt`), heure de poussage réalisée
       (`AOBT_3_flt`) et piste réellement utilisée (`RUNWAY_mvt`).

Si la matrice de variables et les prédictions ressortent strictement identiques, le modèle ne peut
pas dépendre de ces colonnes : l'affirmation de l'argumentaire devient vérifiable par n'importe qui.

    python app/controle_causal.py [--echantillon 5000]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

APP = pathlib.Path(__file__).resolve().parents[1]          # racine du dépôt
sys.path.insert(0, str(APP))

from src.config import load_paths                      # noqa: E402
from src.features import FeatureSpec                  # noqa: E402
from src.predict import load_model                    # noqa: E402
from src.prepare import load_arr, load_dep            # noqa: E402

INTERDITES = ["MVT_TIME_UTC_mvt", "AOBT_3_flt", "RUNWAY_mvt"]


def principal() -> int:
    ap = argparse.ArgumentParser(description="Prouve que le modèle causal n'utilise aucune donnée post-poussage.")
    ap.add_argument("--modele", default=str(APP / "models" / "causal"))
    ap.add_argument("--entrees", default="", help="fichier d'entrées officielles (défaut : final_inputs de configs/paths.local.toml)")
    ap.add_argument("--echantillon", type=int, default=5000)
    ap.add_argument("--graine", type=int, default=7)
    args = ap.parse_args()

    spec = FeatureSpec.from_dict(json.loads((pathlib.Path(args.modele) / "spec.json").read_text(encoding="utf-8")))
    _, booster, best = load_model(pathlib.Path(args.modele))
    if args.entrees:
        entrees = pathlib.Path(args.entrees).expanduser().resolve()
    else:
        paths = load_paths()
        entrees = paths["_official"] / paths["data"]["final_inputs"]

    dep = load_dep(entrees, None)
    arr = load_arr(entrees)
    echant = dep.sample(n=min(args.echantillon, len(dep)), random_state=args.graine).reset_index(drop=True)

    boucher = [c for c in INTERDITES if c in echant.columns]
    sans = echant.copy()

    X_avant = spec.transform(echant, arr)
    y_avant = np.asarray(booster.predict(X_avant, num_iteration=best or None), dtype="float64")

    for col in boucher:
        sans[col] = pd.NaT if str(sans[col].dtype).startswith("datetime") else None
    X_apres = spec.transform(sans, arr)
    y_apres = np.asarray(booster.predict(X_apres, num_iteration=best or None), dtype="float64")

    matrice_identique = X_avant.equals(X_apres)
    ecart_pred = float(np.max(np.abs(y_avant - y_apres))) if len(y_avant) else 0.0
    lignes_differentes = int(np.sum(np.abs(y_avant - y_apres) > 1e-9))

    rapport = {
        "modele": str(pathlib.Path(args.modele).relative_to(APP)),
        "colonnes_bouchees": boucher,
        "lignes_testees": int(len(echant)),
        "variables": int(X_avant.shape[1]),
        "matrice_de_variables_identique": bool(matrice_identique),
        "ecart_maximal_entre_predictions_s": round(ecart_pred, 6),
        "lignes_dont_la_prediction_change": lignes_differentes,
        "conclusion": ("CONFORME : retirer ces informations ne change aucune prédiction"
                       if matrice_identique and lignes_differentes == 0
                       else "NON CONFORME : le modèle dépend de colonnes prétendument inutilisées"),
    }
    print(json.dumps(rapport, indent=1, ensure_ascii=False))
    return 0 if rapport["conclusion"].startswith("CONFORME") else 2


if __name__ == "__main__":
    raise SystemExit(principal())
