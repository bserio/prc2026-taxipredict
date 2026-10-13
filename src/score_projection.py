"""Projection du score officiel AVANT de le relever, sans aucune étiquette de 2026.

Principe : la piste de reconstitution utilise `proxy = MVT_TIME - AOBT_3`. Dans les entrées
officielles de la finale, ces deux colonnes sont présentes, donc le proxy est calculable alors
même que la cible est masquée. On peut ainsi mesurer la **distribution de la difficulté** de la
population 2026 (combien de vols au-delà d'une heure, combien sans fiche réseau, quelle part à
Rome) et y rejouer notre profil d'erreur conditionnelle, mesuré lui sur des mois tenus hors.

Ce que ce script ne fait pas : il ne demande aucun score au classement, ne lit aucune cible 2026
(il n'y en a pas), et n'utilise jamais la réserve interne. C'est un estimateur local, pas une
sonde du classement.

Contrôle de validité obligatoire (`retro_validee`) : on rejoue la même procédure sur un mois de
développement en faisant semblant de l'ignorer. Si l'écart au vrai est trop fort, la projection
n'est pas exploitable et le rapport le dit.

Usage : python -m src.score_projection [--track residual] [--bootstrap 200]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.reconstruct import proxy_seconds
from src.splits import Protocol

# Tranches de proxy en secondes. La dernière est la poche qui domine le carré d'erreur.
TRANCHES = [(0, 900), (900, 1800), (1800, 2700), (2700, 3600), (3600, 5400), (5400, 7200), (7200, np.inf)]
SANS_FICHE = "sans fiche réseau"
SEUIL_CELLULE_DEV = 100          # en dessous, la cellule est fusionnée avec toutes les origines
AEROPORT_A_PART = "LIRF"         # aéroport isolé dans le profil : il domine le carré d'erreur


def tranche(proxy: np.ndarray) -> np.ndarray:
    out = np.full(len(proxy), SANS_FICHE, dtype=object)
    fini = np.isfinite(proxy)
    for lo, hi in TRANCHES:
        sel = fini & (proxy >= lo) & (proxy < hi)
        out[sel] = f"{lo:.0f}-{hi:.0f}" if np.isfinite(hi) else f">{lo:.0f}"
    return out


def cellule(ap: np.ndarray, tr: np.ndarray) -> np.ndarray:
    groupe = np.where(ap == AEROPORT_A_PART, AEROPORT_A_PART, "autre")
    return np.array([f"{t}|{g}" for t, g in zip(tr, groupe)], dtype=object)


def profil(eval_df: pd.DataFrame, exclure: str | None = None) -> tuple[dict[str, tuple[float, int]], dict]:
    """RMSE et effectif par cellule, calculés sur les mois tenus hors demandés."""
    d = eval_df if exclure is None else eval_df[eval_df["month"] != exclure]
    g = d.groupby("cellule")
    table: dict[str, tuple[float, int]] = {}
    for c, sub in g:
        table[str(c)] = (float(np.sqrt(np.mean(sub["sq"].to_numpy()))), int(len(sub)))
    global_rmse = float(np.sqrt(np.mean(d["sq"].to_numpy())))
    par_tranche: dict[str, tuple[float, int]] = {}
    for t, sub in d.groupby("tranche"):
        par_tranche[str(t)] = (float(np.sqrt(np.mean(sub["sq"].to_numpy()))), int(len(sub)))
    return table, {"global": global_rmse, "par_tranche": par_tranche}


def projeter(cellules_2026: np.ndarray, table: dict, fallback: dict) -> tuple[float, list[str]]:
    """MSE moyenne pondérée par la répartition 2026, avec replis explicites."""
    ser = pd.Series(cellules_2026)
    parts = ser.value_counts(normalize=True)
    mse, avertissements = 0.0, []
    for c, w in parts.items():
        if c in table and table[c][1] >= SEUIL_CELLULE_DEV:
            mse += w * table[c][0] ** 2
            continue
        tranche_c = c.split("|")[0]
        if tranche_c in fallback["par_tranche"] and fallback["par_tranche"][tranche_c][1] >= SEUIL_CELLULE_DEV:
            mse += w * fallback["par_tranche"][tranche_c][0] ** 2
            avertissements.append(f"cellule {c} (poids {w:.3f}) remplacée par sa tranche")
        else:
            mse += w * fallback["global"] ** 2
            avertissements.append(f"cellule {c} (poids {w:.3f}) remplacée par l'erreur globale")
    return float(np.sqrt(mse)), sorted(set(avertissements))


def bootstrap(eval_df: pd.DataFrame, cellules_2026: np.ndarray, n: int, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    ser = pd.Series(cellules_2026)
    parts = ser.value_counts(normalize=True)
    groupes = {c: sub["sq"].to_numpy() for c, sub in eval_df.groupby("cellule")}
    tranche_sq = {t: sub["sq"].to_numpy() for t, sub in eval_df.groupby("tranche")}
    global_sq = eval_df["sq"].to_numpy()
    tirages = []
    for _ in range(n):
        mse = 0.0
        for c, w in parts.items():
            src = groupes.get(c)
            if src is None or len(src) < SEUIL_CELLULE_DEV:
                src = tranche_sq.get(c.split("|")[0], global_sq)
            if len(src) < SEUIL_CELLULE_DEV:
                src = global_sq
            echantillon = rng.choice(src, size=len(src), replace=True)
            mse += w * float(np.mean(echantillon))
        tirages.append(np.sqrt(mse))
    return float(np.percentile(tirages, 2.5)), float(np.percentile(tirages, 97.5))


def charger_eval(run: str, reports: Path, prot: Protocol) -> pd.DataFrame:
    ev = pd.read_parquet(reports / f"{run}.eval.parquet")
    morceaux = []
    for m in prot.dev_val_months:
        dep = D.dep_for_months([m], None)
        morceaux.append(pd.DataFrame({"MVT_ID_mvt": dep["MVT_ID_mvt"].to_numpy(),
                                      "proxy": proxy_seconds(dep),
                                      "ap": dep["ADEP_mvt"].astype("object").to_numpy()}))
    joint = ev.merge(pd.concat(morceaux, ignore_index=True), on="MVT_ID_mvt", how="left")
    joint["tranche"] = tranche(joint["proxy"].to_numpy(dtype="float64"))
    joint["cellule"] = cellule(joint["ap"].astype("object").to_numpy(), joint["tranche"].to_numpy())
    y = joint["target"].to_numpy(dtype="float64")
    joint["sq"] = (joint["pred"].to_numpy(dtype="float64") - y) ** 2
    return joint


def charger_2026(paths: dict) -> pd.DataFrame:
    dep, _ = D.final_frames(paths)
    px = proxy_seconds(dep)
    # La colonne officielle `month` fait foi : 27 vols sont planifiés dans un mois voisin du leur.
    out = pd.DataFrame({"month": dep["month"].astype(str).to_numpy(),
                        "ap": dep["ADEP_mvt"].astype("object").to_numpy(), "proxy": px})
    out["tranche"] = tranche(px)
    out["cellule"] = cellule(out["ap"].to_numpy(), out["tranche"].to_numpy())
    return out


def derive(avec_cible: pd.DataFrame, sans_cible: pd.DataFrame) -> list[dict]:
    def resume(d: pd.DataFrame, libelle: str, mois: str = "") -> dict:
        px = d["proxy"].to_numpy(dtype="float64")
        return {"population": libelle, "mois": mois, "n": int(len(d)),
                "sans_fiche_reseau_pct": round(100 * float(np.mean(~np.isfinite(px))), 3),
                "proxy_gt_1h_pct": round(100 * float(np.nanmean(px > 3600)), 3),
                "proxy_gt_2h_pct": round(100 * float(np.nanmean(px > 7200)), 4),
                "LIRF_pct": round(100 * float(np.mean(d["ap"].to_numpy() == AEROPORT_A_PART)), 2),
                "proxy_mediane": round(float(np.nanmedian(px)), 1),
                "proxy_p99": round(float(np.nanquantile(px, 0.99)), 1)}
    lignes = [resume(avec_cible, "2025 (mois cibles, étiquettes connues)")]
    for m, g in sans_cible.groupby("month"):
        lignes.append(resume(g, "2026 (entrée officielle)", m))
    return lignes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="residual", choices=["residual", "causal"])
    ap.add_argument("--run", default="", help="run dont on rejoue le profil (défaut : meilleur de la piste)")
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--cible", type=float, default=385.0, help="barre visée en secondes (janvier + juillet)")
    args = ap.parse_args()

    run = args.run or {"residual": "residual-r1", "causal": "causal-r2"}[args.track]
    paths = load_paths()
    prot = Protocol.from_config(load_config("splits.toml"))
    reports = Path(paths["write"]["reports"])
    debut = time.perf_counter()

    ev = charger_eval(run, reports, prot)
    cible2026 = charger_2026(paths)

    # 1) Rétro-validation d'abord : elle fixe le droit d'interpréter les chiffres qui suivent.
    retro = []
    for m in prot.dev_val_months:
        t_m, r_m = profil(ev, exclure=m)
        sel = ev[ev["month"] == m]
        estime, _ = projeter(sel["cellule"].to_numpy(), t_m, r_m)
        vrai = float(np.sqrt(np.mean(sel["sq"].to_numpy())))
        retro.append({"mois": str(m), "projete": round(estime, 1), "reel": round(vrai, 1),
                      "ecart_pct": round(100 * (estime / vrai - 1.0), 2)})
    ecart_max = max(abs(r["ecart_pct"]) for r in retro)
    sigma = float(np.std([np.log(1.0 + r["ecart_pct"] / 100.0) for r in retro], ddof=1))
    largeur = math.exp(1.96 * sigma)          # incertitude de NIVEAU due à l'effet mois
    niveau_fiable = bool(ecart_max <= 5.0)

    # 2) Projection sur les entrées officielles (aucune étiquette utilisée).
    table, repli = profil(ev)
    projection: dict[str, dict] = {}
    for m in sorted(cible2026["month"].unique()) + ["poolé"]:
        sel = cible2026 if m == "poolé" else cible2026[cible2026["month"] == m]
        rmse, avert = projeter(sel["cellule"].to_numpy(), table, repli)
        ic = bootstrap(ev, sel["cellule"].to_numpy(), args.bootstrap) if args.bootstrap else (float("nan"),) * 2
        projection[m] = {"rmse_projete": round(rmse, 1),
                         "ic95_estimation": [round(ic[0], 1), round(ic[1], 1)],
                         "intervalle_elargi": [round(rmse / largeur, 1), round(rmse * largeur, 1)],
                         "n_lignes": int(len(sel)), "avertissements": avert}
    jj = cible2026[cible2026["month"].isin([m for m in cible2026["month"].unique() if m.endswith(("-01", "-07"))])]
    rmse_jj, _ = projeter(jj["cellule"].to_numpy(), table, repli)

    resultat = {"run_profil": run, "piste": args.track, "genere_le": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "duree_s": round(time.perf_counter() - debut, 1),
                "retro_validation": retro, "ecart_max_pct": round(ecart_max, 2),
                "effet_mois_sigma_log": round(sigma, 3), "largeur_intervalle": round(largeur, 3),
                "niveau_projectable": niveau_fiable,
                "usage_autorise": (["niveau absolu", "comparaison relative", "dérive"] if niveau_fiable
                                   else ["comparaison relative entre mois", "dérive de population"]),
                "projections": projection,
                "janvier_plus_juillet_2026": {
                    "rmse_projete": round(rmse_jj, 1),
                    "intervalle_elargi": [round(rmse_jj / largeur, 1), round(rmse_jj * largeur, 1)],
                    "n_lignes": int(len(jj)),
                    "cible": args.cible,
                    "gain_central_necessaire_pct": round(100 * (1.0 - args.cible / rmse_jj), 1),
                    "gain_borne_optimiste_pct": round(100 * (1.0 - args.cible / (rmse_jj / largeur)), 1)},
                "dérive": derive(ev, cible2026),
                "profil_cellules": {c: {"rmse": round(v[0], 1), "n": v[1]} for c, v in sorted(table.items())}}

    (reports / "SCORE_PROJECTION.json").write_text(json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8")
    lignes = [f"# Projection du score officiel — piste {args.track} (`{run}`)", "",
              f"Généré le {resultat['genere_le']}. **Aucune étiquette 2026 n'existe ni n'est utilisée** : le proxy "
              "est calculé sur les entrées officielles, le profil d'erreur vient de mois tenus hors. Aucun score "
              "n'a été demandé au classement.", "",
              "## 1. Contrôle de validité (rejouer la procédure sur un mois tenu hors)", "",
              "| mois | projeté | réel | écart |", "| --- | ---: | ---: | ---: |"]
    lignes += [f"| {r['mois']} | {r['projete']} | {r['reel']} | {r['ecart_pct']:+.2f} % |" for r in retro]
    lignes += ["", f"Écart maximal **{ecart_max:.1f} %**, dispersion résiduelle σ = {sigma:.3f} en log, soit un "
               f"**facteur d'incertitude de ×{largeur:.2f}** sur le niveau.", "",
               ("La procédure est donc **bonne pour comparer des mois entre eux et mesurer une dérive de population**, "
                "mais **pas pour annoncer un niveau absolu** : à distribution de difficulté égale, deux mois réels "
                "diffèrent ici de ±20 %. Affiner les tranches n'y change rien (23,8 % → 22,7 % avec une queue en "
                "onze tranches) — ce qui varie d'un mois à l'autre n'est pas la fréquence des vols extrêmes mais "
                "**leur ampleur**, et elle n'est inscrite dans aucune colonne.") if not niveau_fiable else
               "La procédure prédit le niveau au mieux près : les projections ci-dessous sont exploitables.", "",
               "## 2. Projection sur les entrées officielles", "",
               "Intervalle = incertitude d'estimation (bootstrap) **et** effet mois (×" + f"{largeur:.2f}).", "",
               "| population | RMSE projetée | IC estimation | intervalle complet | lignes |",
               "| --- | ---: | ---: | ---: | ---: |"]
    for m, p in projection.items():
        lignes.append(f"| {m} | {p['rmse_projete']} | [{p['ic95_estimation'][0]} ; {p['ic95_estimation'][1]}] | "
                      f"[{p['intervalle_elargi'][0]} ; {p['intervalle_elargi'][1]}] | {p['n_lignes']:,} |")
    jjr = resultat["janvier_plus_juillet_2026"]
    lignes += [f"| **janvier + juillet 2026** | **{jjr['rmse_projete']}** | — | "
               f"[{jjr['intervalle_elargi'][0]} ; {jjr['intervalle_elargi'][1]}] | {jjr['n_lignes']:,} |", "",
               f"Pour atteindre **{args.cible:.0f} s** sur janvier + juillet, il faudrait un gain de "
               f"**{jjr['gain_central_necessaire_pct']:.0f} %** par rapport à la projection centrale, ou "
               f"**{jjr['gain_borne_optimiste_pct']:.0f} %** si la population 2026 tombe dans le bas de "
               "l'intervalle. Un seul point du classement officiel — le score du fichier de référence, dont notre "
               "RMSE locale est connue — suffirait à lever l'essentiel de cette incertitude (D‑022).", "",
               "## 3. Dérive 2025 → 2026 (population plus dure ou plus facile ?)", "",
               "| population | mois | n | sans fiche réseau | proxy > 1 h | proxy > 2 h | Rome | médiane | p99 |",
               "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in resultat["dérive"]:
        lignes.append(f"| {d['population']} | {d['mois'] or '—'} | {d['n']:,} | {d['sans_fiche_reseau_pct']} % | "
                      f"{d['proxy_gt_1h_pct']} % | {d['proxy_gt_2h_pct']} % | {d['LIRF_pct']} % | "
                      f"{d['proxy_mediane']} | {d['proxy_p99']} |")
    lignes += ["## 4. Profil conditionnel utilisé (RMSE par cellule, mois tenus hors)", "",
               "| cellule | RMSE | n |", "| --- | ---: | ---: |"]
    lignes += [f"| {c} | {v['rmse']} | {v['n']:,} |" for c, v in resultat["profil_cellules"].items()]
    avert = sorted({a for p in projection.values() for a in p["avertissements"]})
    if avert:
        lignes += ["", "### Replis appliqués (cellules trop peu nombreuses dans le profil)", ""]
        lignes += [f"- {a}" for a in avert]
    (reports / "SCORE_PROJECTION.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")

    print(f"retro-validation : écart max {ecart_max:.1f} % | effet mois x{largeur:.2f} -> "
          f"{'niveau exploitable' if niveau_fiable else 'comparaison relative seulement'}")
    print(f"janvier+juillet 2026 projeté : {rmse_jj:.1f} s  intervalle "
          f"[{rmse_jj / largeur:.1f} ; {rmse_jj * largeur:.1f}]  (cible {args.cible:.0f} s -> "
          f"gain nécessaire {jjr['gain_central_necessaire_pct']:.0f} %)")
    for m, p in projection.items():
        print(f"   {m:10s} {p['rmse_projete']:7.1f} s  [{p['intervalle_elargi'][0]}; {p['intervalle_elargi'][1]}]")
    print(f"ecrit {reports / 'SCORE_PROJECTION.md'}")


if __name__ == "__main__":
    main()
