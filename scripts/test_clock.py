#!/usr/bin/env python3
"""Test d'horloge etendu (garde C du protocole V8) sur le modele gele V7A.

Principe : une variable est autorisee si et seulement si son instant de realisation
est anterieur ou egal a T0 (= poussage). Ici T0-P : avant le pushback, aucune donnee
realisee du vol considere ni du trafic de la periode ne peut bouger la prediction.

Trois epreuves, chacune exigeant maxdiff = 0 (pas « quasi nul ») :

  A. Absence structurelle : les colonnes realisees interdites ne doivent meme pas
     exister dans le cadre alimentant le pipeline (ARVT_1_flt n'est jamais charge).
  B. Masquage : boucher MVT_TIME, AOBT_3, RUNWAY (liste historique de
     controle_causal.py) PUIS BLOCK_TIME et ADES_mvt (ajouts V8 : poussage realise,
     destination realisee apres detournement).
  C. Permutation : perturber ces colonnes au hasard en preservant la distribution
     marginale (epreuve V8 stricte), sur les depart ET sur les arrivees de la periode
     (MVT_TIME/TAXITIME realises des ARRIVEES) — prouve que capacite et geometrie
     viennent de la spec gelee, pas d'un recalcul sur la periode evaluee.

Sortie : code 0 si CONFORME, 2 sinon ; rapport JSON dans reports/.

    python3 scripts/test_clock.py [--modele <dir>] [--echantillon 50000]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

RACINE = pathlib.Path(__file__).resolve().parents[1]   # racine du dépôt (src/ et models/)
sys.path.insert(0, str(RACINE))

import lightgbm as lgb                                # noqa: E402

from src.config import load_paths                     # noqa: E402
from src.features import FeatureSpec                  # noqa: E402
from src.predict import load_model                    # noqa: E402
from src.prepare import load_arr, load_dep            # noqa: E402


def _load_boosters(dossier):
    """Un dossier = model.txt (modele gele) ou model_*.txt (enssemble) -> liste (booster, best)."""
    dossier = pathlib.Path(dossier)
    if (dossier / "model.txt").exists():
        _, booster, best = load_model(dossier)
        return [(booster, best)]
    fichiers = sorted(dossier.glob("model_*.txt"))
    if not fichiers:
        raise SystemExit(f"aucun modele dans {dossier}")
    return [(lgb.Booster(model_file=str(f)), 0) for f in fichiers]

# realisees apres T0 cote depart (T0 = poussage) : poussees a ne jamais bouger la prediction
INTERDITES_DEP = ["MVT_TIME_UTC_mvt", "AOBT_3_flt", "RUNWAY_mvt",
                  "BLOCK_TIME_UTC_mvt", "ADES_mvt"]
# realisees cote arrivees de la periode evaluee : le bras causal ne doit pas les lire
INTERDITES_ARR = ["MVT_TIME_UTC_mvt", "TAXITIME_SEC_mvt"]
# jamais chargees du tout par src.prepare (epreuve A)
ABSENTES = ["ARVT_1_flt", "delay_arvt_eobt", "delay_aobt_eobt", "delay_offblock_eobt"]


def _pred(spec, boosters, dep, arr):
    X = spec.transform(dep, arr)
    p = np.mean([b.predict(X, num_iteration=best or None) for b, best in boosters], axis=0)
    return X, np.asarray(p, dtype="float64")


def _epreuve(nom, spec, boosters, base_dep, base_arr, y0, rng):
    dep, arr = base_dep.copy(), base_arr.copy()
    for col in INTERDITES_DEP:
        if col not in dep.columns:
            continue
        if nom == "masquage":
            dep[col] = pd.NaT if str(dep[col].dtype).startswith("datetime") else None
        else:  # permutation : distribution marginale preservee, lignes melees
            dep[col] = dep[col].to_numpy()[rng.permutation(len(dep))]
    for col in INTERDITES_ARR:
        if col not in arr.columns:
            continue
        if nom == "masquage":
            arr[col] = pd.NaT if str(arr[col].dtype).startswith("datetime") else None
        else:
            arr[col] = arr[col].to_numpy()[rng.permutation(len(arr))]
    X1, y1 = _pred(spec, boosters, dep, arr)
    return {
        "epreuve": nom,
        "colonnes_depart_perturbees": [c for c in INTERDITES_DEP if c in base_dep.columns],
        "ecart_maximal_s": round(float(np.max(np.abs(y1 - y0))), 6),
        "lignes_modifiees": int(np.sum(np.abs(y1 - y0) > 1e-9)),
    }


def principal() -> int:
    ap = argparse.ArgumentParser(description="Garde C : preuve par perturbation que V7A ignore tout ce qui est realise apres T0.")
    ap.add_argument("--modele", default=str(RACINE / "models" / "causal"))
    ap.add_argument("--entrees", default="", help="fichier d'entrées (défaut : final_inputs de configs/paths.local.toml)")
    ap.add_argument("--echantillon", type=int, default=50000)
    ap.add_argument("--graine", type=int, default=7)
    ap.add_argument("--rapport", default="test_clock_v7A", help="nom du JSON de sortie dans reports/")
    args = ap.parse_args()

    spec = FeatureSpec.from_dict(json.loads((pathlib.Path(args.modele) / "spec.json").read_text(encoding="utf-8")))
    boosters = _load_boosters(args.modele)
    if args.entrees:
        entrees = pathlib.Path(args.entrees).expanduser().resolve()
    else:
        paths = load_paths()
        entrees = paths["_official"] / paths["data"]["final_inputs"]

    dep = load_dep(entrees, None)
    arr = load_arr(entrees)
    echant = dep.sample(n=min(args.echantillon, len(dep)), random_state=args.graine).reset_index(drop=True)

    structurelle = {c: (c not in dep.columns) for c in ABSENTES}
    X0, y0 = _pred(spec, boosters, echant, arr)

    rng = np.random.default_rng(args.graine)
    epreuves = [_epreuve("masquage", spec, boosters, echant, arr, y0, rng),
                _epreuve("permutation", spec, boosters, echant, arr, y0, rng)]

    conforme = all(e["ecart_maximal_s"] == 0.0 and e["lignes_modifiees"] == 0 for e in epreuves) \
        and all(structurelle.values())
    rapport = {
        "modele": str(pathlib.Path(args.modele)),
        "entrees": str(entrees),
        "t0": "poussage (T0-P)",
        "lignes_testees": int(len(echant)),
        "variables_modele": int(X0.shape[1]),
        "absence_structurelle": structurelle,
        "epreuves": epreuves,
        "conclusion": ("CONFORME : aucune perturbation posterieure a T0 ne change aucune prediction"
                       if conforme else
                       "NON CONFORME : au moins une colonne posterieure a T0 influence la prediction"),
    }
    out = RACINE / "reports" / f"{args.rapport}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rapport, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rapport, indent=1, ensure_ascii=False))
    return 0 if conforme else 2


if __name__ == "__main__":
    raise SystemExit(principal())
