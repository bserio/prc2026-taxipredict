"""Ouverture UNIQUE de la réserve interne 2025 (novembre + décembre).

La réserve ne sert qu'une fois : toutes les recettes intéressées doivent donc être évaluées
**dans la même commande**. Un marqueur journalise l'ouverture (horodatage, recettes, scores)
et refuse toute ouverture ultérieure, sauf `--force` avec justification consignée.

Garde-fous :
  * exigence explicite `--confirm-reserve` ;
  * chaque modèle doit avoir été ajusté sans la réserve (contrôlé dans son meta.json) ;
  * le même post-traitement que la soumission est appliqué (`src.predict.finalise`) ;
  * aucune donnée de la réserve n'écrit ailleurs que dans `reports/`.

    python -m src.evaluate_reserved --tracks causal,residual,reference \\
        --model-dir artifacts/causal-final/final \\
        --residual-dir artifacts/residual-final/final \\
        --run-id reserve-2025-11-12 --confirm-reserve
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.predict import causal_predictions, finalise, load_model
from src.reconstruct import fit_state, predict as hybrid_predict, state_from_dict
from src.report import build_report, write_report
from src.residual import baseline
from src.splits import Protocol

CHOIX = ("causal", "residual", "reference")


def _controleGel(model_dir: Path, protocol: Protocol, nom: str) -> dict:
    meta_path = model_dir / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"refusé : {nom} sans meta.json, impossible de prouver l'absence de la réserve")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if set(meta.get("train_months", [])) & set(protocol.reserve_months):
        raise SystemExit(f"refusé : {nom} a été ajusté sur des mois de la réserve")
    return meta


def predictions(track: str, mois: str, dep: pd.DataFrame, arr: pd.DataFrame, args, paths, cache: dict) -> np.ndarray:
    if track == "causal":
        return causal_predictions(Path(args.model_dir), dep, arr)

    if track == "reference":
        if "etat_ref" not in cache:
            cfg = load_config(args.reference_config)
            cache["etat_ref"] = fit_state(D.dep_for_months(Protocol.from_config(
                load_config("splits.toml")).reserve_train_months(), paths), cfg)
        pred, _ = hybrid_predict(dep, cache["etat_ref"], None)
        return pred

    # residual : base = proxy corrige du biais, le modèle ne prédit que la correction
    if "res" not in cache:
        spec, model, best = load_model(Path(args.residual_dir))
        etat = state_from_dict(json.loads((Path(args.residual_dir) / "state.json").read_text(encoding="utf-8")))
        cache["res"] = (spec, model, best, etat)
    spec, model, best, etat = cache["res"]
    base, usable = baseline(dep, etat)
    res_hat = np.asarray(model.predict(spec.transform(dep, arr), num_iteration=best if best > 0 else None),
                         dtype="float64")
    if "fb" not in cache:
        repli = Path(args.fallback_model_dir or args.model_dir)
        cache["fb"] = causal_predictions(repli, dep, arr)
    return np.where(usable, base + res_hat, cache["fb"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", default="causal,residual,reference",
                    help=f"liste séparée par des virgules parmi {CHOIX}")
    ap.add_argument("--model-dir", default="", help="modèle causal gelé")
    ap.add_argument("--residual-dir", default="", help="modèle résiduel gelé (+ state.json)")
    ap.add_argument("--fallback-model-dir", default="", help="repli causal du résiduel (défaut : --model-dir)")
    ap.add_argument("--reference-config", default="configs/tabular_hybrid_noclip.toml")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--confirm-reserve", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.confirm_reserve:
        raise SystemExit("refusé : ajouter --confirm-reserve (ouverture unique, après gel des recettes)")

    tracks = [t.strip() for t in args.tracks.split(",") if t.strip()]
    inconnues = [t for t in tracks if t not in CHOIX]
    if inconnues:
        raise SystemExit(f"recettes inconnues : {inconnues} (choix possibles : {CHOIX})")
    if "causal" in tracks and not args.model_dir:
        raise SystemExit("refusé : --model-dir requis pour évaluer la piste causale")
    if "residual" in tracks and not (args.residual_dir and (args.fallback_model_dir or args.model_dir)):
        raise SystemExit("refusé : la piste résiduelle exige --residual-dir et un repli causal "
                         "(--fallback-model-dir ou --model-dir)")

    paths = load_paths()
    reports_dir = Path(paths["write"]["reports"])
    marker = reports_dir / "RESERVE_OPENED.json"
    if marker.exists() and not args.force:
        raise SystemExit(f"réserve déjà ouverte le "
                         f"{json.loads(marker.read_text(encoding='utf-8'))['horodatage']} — "
                         "une seconde ouverture exige --force et une justification consignée dans DECISIONS.md")

    protocol = Protocol.from_config(load_config("splits.toml"))
    modeles = {}
    if "causal" in tracks:
        modeles["causal"] = _controleGel(Path(args.model_dir), protocol, "modèle causal")
    if "residual" in tracks:
        modeles["residual"] = _controleGel(Path(args.residual_dir), protocol, "modèle résiduel")

    # Les prédictions sont calculées mois par mois, puis poolées : la RMSE de la réserve est
    # une seule RMSE sur novembre + décembre, pas une moyenne de deux scores.
    par_recette: dict[str, pd.DataFrame] = {t: [] for t in tracks}
    start = time.perf_counter()
    for mois in protocol.reserve_months:
        dep = D.dep_for_months([mois], paths)
        arr = D.arr_for_months([mois], paths)
        cache: dict = {}
        for t in tracks:
            brut = predictions(t, mois, dep, arr, args, paths, cache)
            par_recette[t].append(pd.DataFrame({
                "MVT_ID_mvt": dep["MVT_ID_mvt"].to_numpy(), "month": mois,
                "ADEP_mvt": dep["ADEP_mvt"].astype("object").to_numpy(),
                "pred": finalise(brut),
                "target": pd.to_numeric(dep["TAXITIME_SEC_mvt"], errors="coerce").to_numpy(dtype="float64")}))

    journal = {"horodatage": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "run_id": args.run_id,
               "reserve": list(protocol.reserve_months), "recettes": {}}
    resume = {}
    for t in tracks:
        eval_df = pd.concat(par_recette[t], ignore_index=True)
        eval_df = eval_df[np.isfinite(eval_df.target.to_numpy())]
        rapport = build_report(f"{args.run_id}-{t}", args.model_dir or args.residual_dir or args.reference_config,
                              t, "reserved", eval_df, protocol, {"n_rows": int(len(eval_df))},
                              time.perf_counter() - start, split="reserved")
        write_report(rapport, eval_df, reports_dir)
        aberrantes = (eval_df.target > 7200) | (eval_df.target <= 60)
        resume[t] = round(float(rapport["global"]["rmse"]), 1)
        journal["recettes"][t] = {
            "rmse": resume[t],
            "mae": round(float(rapport["global"]["mae"]), 1),
            "biais": round(float(rapport["global"]["bias"]), 1),
            "lignes": int(len(eval_df)),
            "rmse_hors_lignes_aberrantes": round(float(np.sqrt(np.mean(
                (eval_df.pred.to_numpy()[~aberrantes] - eval_df.target.to_numpy()[~aberrantes]) ** 2))), 1),
            "par_mois": [(r["month"], round(r["rmse"], 1)) for r in rapport["by_month"]],
        }

    marker.write_text(json.dumps(journal, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resume, indent=1))


if __name__ == "__main__":
    main()
