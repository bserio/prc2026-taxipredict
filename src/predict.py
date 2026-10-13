"""Production du fichier de soumission depuis les entrées officielles 2026.

    python -m src.predict --track causal --model-dir artifacts/causal-final/final --run-id sub-causal-v1
    python -m src.predict --track hybrid --fallback-model-dir artifacts/causal-final/final --run-id sub-hybrid-v1

Le gabarit officiel dicte l'ordre, les identifiants et les types : la sortie reprend
exactement MVT_ID_mvt (double) du gabarit et TAXITIME_SEC_mvt dans le **dtype du gabarit**
(float64), arrondi à la seconde la plus proche. Aucun envoi : l'écriture est locale,
le dépôt MinIO demande une approbation séparée.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.features import FeatureSpec
from src.reconstruct import fit_state, predict as hybrid_predict


def finalise(pred) -> np.ndarray:
    """Post-traitement de sortie, unique pour la soumission et pour l'estimation sur réserve.

    Plancher à 0 s : mesuré gratuit en RMSE (D-019) et il supprime l'impossible.
    Aucun ecretage haut : il coute jusqu'a +2,5 % de RMSE.
    """
    p = np.asarray(pred, dtype="float64")
    return np.rint(np.maximum(np.where(np.isfinite(p), p, float(np.nanmedian(p))), 0.0))


def load_model(model_dir: Path):
    spec = FeatureSpec.from_dict(json.loads((model_dir / "spec.json").read_text(encoding="utf-8")))
    model = lgb.Booster(model_file=str(model_dir / "model.txt"))
    meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8")) if (model_dir / "meta.json").exists() else {}
    best = int(meta.get("num_boost_round") or 0)
    return spec, model, best


def causal_predictions(model_dir: Path, dep: pd.DataFrame, arr: pd.DataFrame) -> np.ndarray:
    spec, model, best = load_model(model_dir)
    X = spec.transform(dep, arr)
    return np.asarray(model.predict(X, num_iteration=best if best > 0 else None), dtype="float64")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=["causal", "hybrid", "residual"])
    ap.add_argument("--model-dir", default="", help="répertoire du modèle gelé (piste causal)")
    ap.add_argument("--fallback-model-dir", default="", help="modèle causal utilisé comme repli (pistes hybrid/residual)")
    ap.add_argument("--config", default="")
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    paths = load_paths()
    dep, arr = D.final_frames(paths)
    template = D.template(paths)
    print(f"entrées finales : {len(dep):,} départs | gabarit : {len(template):,} lignes")

    if args.track == "causal":
        if not args.model_dir:
            raise SystemExit("--model-dir requis pour la piste causal")
        pred = causal_predictions(Path(args.model_dir), dep, arr)
    elif args.track == "residual":
        from src.reconstruct import state_from_dict
        from src.residual import baseline

        model_dir = Path(args.model_dir)
        spec, model, best = load_model(model_dir)
        state = state_from_dict(json.loads((model_dir / "state.json").read_text(encoding="utf-8")))
        base, usable = baseline(dep, state)
        res_hat = np.asarray(model.predict(spec.transform(dep, arr), num_iteration=best if best > 0 else None),
                             dtype="float64")
        fb = causal_predictions(Path(args.fallback_model_dir), dep, arr) if args.fallback_model_dir else None
        if fb is None:
            ap_hour = pd.to_datetime(dep["SCHED_TIME_UTC_mvt"], utc=True).dt.hour.to_numpy()
            fb = np.array([state["fallback"].get((a, int(h)), state["glob_mean"]) for a, h in
                           zip(dep["ADEP_mvt"].astype("object").to_numpy(), ap_hour)], dtype="float64")
            print("repli : moyenne aéroport-heure (aucun modèle causal fourni)")
        else:
            print(f"repli : modèle causal {args.fallback_model_dir} sur {float((~usable).mean()):.2%} des lignes")
        pred = np.where(usable, base + res_hat, fb)
    else:
        cfg = load_config(args.config or "configs/tabular_hybrid.toml")
        from src import data as _D
        from src.splits import Protocol
        months = Protocol.from_config(load_config("splits.toml")).reserve_train_months()
        state = fit_state(_D.dep_for_months(months, paths), cfg)
        fb = causal_predictions(Path(args.fallback_model_dir), dep, arr) if args.fallback_model_dir else None
        pred, diag = hybrid_predict(dep, state, fb)
        print("diagnostic repli :", diag)

    template_ids = template["MVT_ID_mvt"].to_numpy(dtype="float64")
    key = dep["MVT_ID_mvt"].to_numpy(dtype="float64")
    order = pd.Index(template_ids).get_indexer(pd.Index(key))
    if (order < 0).any():
        raise SystemExit(f"{int((order < 0).sum())} identifiants du modèle absents du gabarit")
    if len(set(key.tolist())) != len(key.tolist()):
        raise SystemExit("identifiants en double côté entrées")
    # Plancher a 0 et arrondi : meme fonction que l'estimation sur reserve (D-019).
    values = finalise(pred)
    dtype_cible = template["TAXITIME_SEC_mvt"].dtype        # le gabarit fait float64, pas int32
    full = np.zeros(len(template_ids), dtype=dtype_cible)
    full[order] = values.astype(dtype_cible)
    out = pd.DataFrame({"MVT_ID_mvt": template_ids.astype("float64"), "TAXITIME_SEC_mvt": full})

    sub_dir = Path(paths["write"]["submission"])
    sub_dir.mkdir(parents=True, exist_ok=True)
    path = sub_dir / f"{args.run_id}.parquet"
    out.to_parquet(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps({"fichier": str(path), "lignes": int(len(out)), "sha256": digest,
                      "min": int(full.min()), "max": int(full.max())}, indent=1))


if __name__ == "__main__":
    main()
