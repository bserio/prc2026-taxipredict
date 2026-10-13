#!/usr/bin/env python3
"""Régénère les fichiers de soumission Taxipredict v7, prêts à déposer.

Familles
    A  causal          prédiction pure ; aucune information postérieure au pushback.
    B  reconstitution  résidu sur l'ancre `MVT_TIME − AOBT_3`, avec repli causal pour les vols
                       qui n'ont pas de fiche réseau (1,35 % des lignes).

Gabarits
    4mois → final_submitting.parquet (670 790 lignes) : gabarit officiel de la finale, à remplir
            intégralement — le script de classement refuse toute ligne manquante ou en trop.
    2mois → submitting.parquet (344 841 lignes) : sous-ensemble janvier + juillet 2026, dans son
            propre ordre. C'est la population réellement notée par le classement.

Type de la cible
    Les deux gabarits officiels déclarent `TAXITIME_SEC_mvt` en **int32** (vérifié sur le schéma
    arrow des fichiers). pandas les lit `float64` uniquement parce qu'ils sont vides : ce script
    écrit donc en int32, après avoir vérifié que toutes les valeurs sont finies et dans les bornes.

Exemples
    python app/infere.py --famille A --equipe lighthearted-sandwich
    python app/infere.py --famille B --gabarit 4mois --sortie /tmp/test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

APP = Path(__file__).resolve().parents[1]          # racine du dépôt (src/ et models/ y vivent)
sys.path.insert(0, str(APP))

from src import data as D                          # noqa: E402
from src.config import load_paths                  # noqa: E402
from src.predict import causal_predictions, finalise, load_model  # noqa: E402
from src.reconstruct import state_from_dict        # noqa: E402
from src.residual import baseline                  # noqa: E402

INT32_MAX = 2_147_483_647
FAMILLES = {
    "A": {"nom": "causal", "lettre": "A"},
    "B": {"nom": "reconstitution", "lettre": "B"},
}
GABARITS = {
    "2mois": {"fichier": "submitting.parquet", "suffixe": "v7"},
    "4mois": {"fichier": "final_submitting.parquet", "suffixe": "final"},
}


def predictions(famille: str, dep: pd.DataFrame, arr: pd.DataFrame) -> np.ndarray:
    """Reproduit exactement le post-traitement des fichiers gelés (plancher 0 s, aucun plafond)."""
    if famille == "A":
        return finalise(causal_predictions(APP / "models" / "causal", dep, arr))

    modele = APP / "models" / "residual"
    spec, booster, best = load_model(modele)
    etat = state_from_dict(json.loads((modele / "state.json").read_text(encoding="utf-8")))
    base, utilisable = baseline(dep, etat)
    residu = np.asarray(booster.predict(spec.transform(dep, arr), num_iteration=best or None), dtype="float64")
    # le repli causal est identique au octet près au modèle gelé de la famille A (diff vérifié)
    repli = causal_predictions(APP / "models" / "causal", dep, arr)
    return finalise(np.where(utilisable, base + residu, repli))


def ecrire(couple, gabarit: Path, sortie: Path, cible_float64: bool) -> dict:
    valeurs_pred, ids_dep = couple
    tpl = pd.read_parquet(gabarit)
    ids_tpl = tpl["MVT_ID_mvt"].to_numpy(dtype="float64")

    # On part du gabarit : chaque ligne à remplir reçoit sa prédiction (le gabarit 2 mois est un
    # sous-ensemble strict des départs, l'indexation inverse laisserait des trous).
    serie = pd.Series(np.asarray(valeurs_pred, dtype="float64"), index=np.asarray(ids_dep, dtype="float64"))
    if serie.index.has_duplicates:
        raise SystemExit("identifiants en double côté prédictions")
    valeurs = serie.reindex(ids_tpl).to_numpy(dtype="float64")
    manquantes = int(np.isnan(valeurs).sum())
    if manquantes:
        raise SystemExit(f"{manquantes} lignes du gabarit {gabarit.name} sans prédiction")

    if not np.isfinite(valeurs).all():
        raise SystemExit("valeurs non finies : refus d'écrire")
    if not cible_float64 and (np.nanmin(valeurs) < -INT32_MAX - 1 or np.nanmax(valeurs) > INT32_MAX):
        raise SystemExit(f"valeurs hors bornes int32 : [{np.nanmin(valeurs)}, {np.nanmax(valeurs)}]")

    dtype = "float64" if cible_float64 else "int32"
    entetes = pq.ParquetFile(gabarit).schema_arrow.names
    cadre = pd.DataFrame({entetes[0]: ids_tpl, entetes[1]: valeurs.astype(dtype)})
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # ZSTD sans dictionnaire : les MVT_ID sont quasi uniques, le dictionnaire RLE par défaut de
    # pyarrow (SNAPPY) triple la taille du fichier (~2,2 Mo au lieu de ~1,1 Mo, cf. v1–v6 en Polars).
    cadre.to_parquet(sortie, index=False, compression="zstd", use_dictionary=False)

    return verifier(sortie, gabarit)


def verifier(chemin: Path, gabarit: Path) -> dict:
    """Contrôle sur les types **arrow** du fichier écrit, jamais sur les dtypes pandas."""
    t_schema = pq.ParquetFile(gabarit).schema_arrow
    s_schema = pq.ParquetFile(chemin).schema_arrow
    erreurs: list[str] = []

    if [f.name for f in s_schema] != [f.name for f in t_schema]:
        erreurs.append(f"colonnes {[f.name for f in s_schema]} != gabarit {[f.name for f in t_schema]}")
    for champ, attendu in zip(s_schema, t_schema):
        if str(champ.type) != str(attendu.type):
            erreurs.append(f"{champ.name} en {champ.type} alors que le gabarit déclare {attendu.type}")

    sous = pd.read_parquet(chemin)
    tpl = pd.read_parquet(gabarit)
    ids_s = sous["MVT_ID_mvt"].to_numpy(dtype="float64")
    ids_t = tpl["MVT_ID_mvt"].to_numpy(dtype="float64")
    if len(ids_s) != len(ids_t):
        erreurs.append(f"{len(ids_s)} lignes != {len(ids_t)} du gabarit")
    elif not np.array_equal(ids_s, ids_t):
        erreurs.append("identifiants non alignés (ordre différent du gabarit)")
    v = sous["TAXITIME_SEC_mvt"].to_numpy(dtype="float64")
    if not np.isfinite(v).all():
        erreurs.append("valeurs non finies après relecture")

    rapport = {
        "fichier": str(chemin),
        "lignes": int(len(sous)),
        "type_cible": str([f.type for f in s_schema][1]),
        "min": float(np.nanmin(v)), "mediane": float(np.nanmedian(v)), "max": float(np.nanmax(v)),
        "sha256": hashlib.sha256(chemin.read_bytes()).hexdigest(),
        "erreurs": erreurs,
    }
    return rapport


def main() -> int:
    ap = argparse.ArgumentParser(description="Régénère un fichier de soumission conforme au gabarit officiel.")
    ap.add_argument("--famille", required=True, choices=sorted(FAMILLES), help="A = causal, B = reconstitution")
    ap.add_argument("--gabarit", default="les_deux", choices=["2mois", "4mois", "les_deux"])
    ap.add_argument("--equipe", default="lighthearted-sandwich", help="nom exact du compte, sans suffixe")
    ap.add_argument("--sortie", default="", help="dossier de destination (défaut : <famille>/soumission)")
    ap.add_argument("--data-dir", default="", help="remplace donnees_officielles/ si les fichiers sont ailleurs")
    ap.add_argument("--float64", action="store_true",
                    help="écrit la cible en float64 (comportement historique du projet) au lieu d'int32")
    args = ap.parse_args()

    paths = load_paths()
    if args.data_dir:
        officiel = Path(args.data_dir).expanduser().resolve()
        if not (officiel / paths["data"]["final_inputs"]).exists():
            raise SystemExit(f"données introuvables dans {officiel}")
        paths["_official"] = officiel

    lettre = FAMILLES[args.famille]["lettre"]
    dossier = Path(args.sortie).expanduser() if args.sortie else APP / "submission"

    dep, arr = D.final_frames(paths)
    pred = predictions(args.famille, dep, arr)
    couple = (pred, dep["MVT_ID_mvt"].to_numpy(dtype="float64"))

    choix = ["2mois", "4mois"] if args.gabarit == "les_deux" else [args.gabarit]
    rapports = []
    for cle in choix:
        gabarit = paths["_official"] / GABARITS[cle]["fichier"]
        sortie = dossier / f"{args.equipe}_{GABARITS[cle]['suffixe']}{lettre}.parquet"
        rapports.append(ecrire(couple, gabarit, sortie, args.float64))

    print(json.dumps(rapports, indent=1, ensure_ascii=False))
    fautes = [e for r in rapports for e in r["erreurs"]]
    if fautes:
        print("\n".join(f"ERREUR : {e}" for e in fautes), file=sys.stderr)
        return 2
    print(f"\nOK — famille {lettre}, {len(rapports)} fichier(s) validé(s) contre leur gabarit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
