"""Audit des sources : deux mesures independantes du meme off-block.

La cible officielle vient des mouvements :  cible  = MVT_TIME - BLOCK_TIME_UTC_mvt.
Le reseau en fournit une autre :            proxy  = MVT_TIME - AOBT_3_flt.

Les soustraire elimine MVT_TIME et laisse un desaccord pur sur l'off-block :

    cible - proxy = AOBT_3_flt - BLOCK_TIME_UTC_mvt

Cet outil **ne preche pas** entre les deux sources : il classe les vols selon leur accord,
puis croise cette classification avec (a) les roulages longs et (b) l'erreur des modeles deja
evalues. Aucune decision d'entrainement n'est prise ici ; l'evaluation reste sur 100 % des lignes.

    python -m src.audit                       # mois cibles du developpement
    python -m src.audit --months 2025-01      # un seul mois
    python -m src.audit --seuils 600,1800     # seuils de desaccord (secondes)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src import data as D
from src.config import load_config, load_paths
from src.prepare import diff_minutes
from src.splits import Protocol

SANS_INFO = "sans_info_NM"
CONCORDANT = "concordant"
MODERE = "desaccord_modere"
FORT = "desaccord_fort"


def ecart_offblock(dep: pd.DataFrame) -> np.ndarray:
    """Desaccord entre les deux sources d'off-block, en secondes (signe : reseau - mouvements).

    Egal a `cible - proxy` par construction ; NaN si l'une des deux sources manque.
    """
    e = diff_minutes(dep["AOBT_3_flt"], dep["BLOCK_TIME_UTC_mvt"]) * 60.0
    return np.where(np.isfinite(e), e, np.nan).astype("float64")


def categories(ecart: np.ndarray, seuils=(900, 1800)) -> pd.Series:
    """Classe chaque vol selon l'ampleur du desaccord, sans designer le coupable.

    Sans information reseau = categorie a part entiere : on ne peut pas parler d'accord
    quand il n'y a qu'une source.
    """
    modere, fort = float(seuils[0]), float(seuils[1])
    a = np.abs(np.asarray(ecart, dtype="float64"))
    cat = np.where(~np.isfinite(a), SANS_INFO,
                   np.where(a <= modere, CONCORDANT, np.where(a <= fort, MODERE, FORT)))
    return pd.Series(cat, index=range(len(a)))


def _table(frame: pd.DataFrame, cle: str) -> pd.DataFrame:
    g = frame.groupby(cle).agg(
        n=("cible", "size"),
        cible_mediane=("cible", "median"),
        cible_p99=("cible", lambda s: float(s.quantile(0.99))),
        cible_max=("cible", "max"),
        ecart_median=("ecart", "median"),
    ).reset_index()
    g["part_lignes"] = (g.n / g.n.sum()).round(4)
    return g


def audit_months(mois: list[str], paths: dict, seuils) -> tuple[pd.DataFrame, dict]:
    dep = D.dep_for_months(mois, paths)
    cible = pd.to_numeric(dep["TAXITIME_SEC_mvt"], errors="coerce").to_numpy(dtype="float64")
    ecart = ecart_offblock(dep)
    proxy = cible - ecart                                   # coherent par construction
    f = pd.DataFrame({
        "MVT_ID_mvt": dep["MVT_ID_mvt"].to_numpy(dtype="float64"),
        "month": dep["month"].astype("object").to_numpy(),
        "ADEP_mvt": dep["ADEP_mvt"].astype("object").to_numpy(),
        "cible": cible, "proxy": proxy, "ecart": ecart,
        "categorie": categories(ecart, seuils).to_numpy(),
    })

    resume = {"mois": mois, "seuils_secondes": list(map(int, seuils)),
              "lignes": int(len(f)), "categories": _table(f, "categorie").to_dict("records")}

    # Question utile : les roulages longs sont-ils confirmes par les deux sources ?
    resume["roulages_long"] = {}
    for seuil_cible in (3600, 7200):
        longs = f[f.cible > seuil_cible]
        if not len(longs):
            continue
        v = longs.categorie.value_counts(normalize=True).round(4)
        resume["roulages_long"][f"cible_supérieure_à_{seuil_cible}s"] = {
            "n": int(len(longs)),
            **{k: float(v.get(k, 0.0)) for k in (CONCORDANT, MODERE, FORT, SANS_INFO)},
        }
    resume["roulages_long_confirmes"] = {
        f"cible_au_dela_de_{s}s": diagnostic_mvt(dep, cible, f.categorie, s) for s in (3600, 7200)}
    return f, resume


def croiser_erreur(f: pd.DataFrame, runs: dict[str, Path]) -> pd.DataFrame:
    """Erreur des modeles deja evalues, par categorie de concordance (evaluation intacte)."""
    lignes = []
    for nom, chemin in runs.items():
        if not chemin.exists():
            continue
        e = pd.read_parquet(chemin)[["MVT_ID_mvt", "pred", "target"]]
        m = e.merge(f[["MVT_ID_mvt", "categorie"]], on="MVT_ID_mvt", how="left")
        m["categorie"] = m.categorie.fillna(SANS_INFO)
        for cat, g in m.groupby("categorie"):
            car = (g.pred - g.target) ** 2
            lignes.append({"modele": nom, "categorie": cat, "lignes": int(len(g)),
                           "rmse": round(float(np.sqrt(car.mean())), 1),
                           "biais": round(float((g.pred - g.target).mean()), 1),
                           "part_du_carre_d_erreur": round(float(car.sum() / ((m.pred - m.target) ** 2).sum()), 4)})
    return pd.DataFrame(lignes)


def diagnostic_mvt(dep: pd.DataFrame, cible: np.ndarray, cat: pd.Series, seuil_cible: float) -> dict:
    """Troisieme yardstick : les roulages enormes viennent-ils du decollage ou de l'off-block ?

    Les deux sources d'off-block se soustraient avec le MEME `MVT_TIME` : si c'est le decollage qui
    est faux, elles restent d'accord entre elles. On compare donc aussi le decollage a l'horaire
    planifie (`MVT_TIME - SCHED_TIME`, temps au sol total) et a l'off-block calcule par le reseau
    avant depart (`LOBT_flt`). Un vol vraiment bloque au sol a un temps au sol total enorme ;
    un `MVT_TIME` ou un `BLOCK_TIME` corrompu n'en a pas.
    """
    sel = cible > seuil_cible
    if not sel.any():
        return {}
    sol = np.asarray(diff_minutes(dep["MVT_TIME_UTC_mvt"], dep["SCHED_TIME_UTC_mvt"]), dtype="float64") * 60.0
    lobt = np.asarray(diff_minutes(dep["MVT_TIME_UTC_mvt"], dep["LOBT_flt"]), dtype="float64") * 60.0
    c = cat.to_numpy()[sel]
    out = {"n": int(sel.sum()), "categories": {}}
    for k in (CONCORDANT, MODERE, FORT, SANS_INFO):
        m = c == k
        if not m.any():
            out["categories"][k] = {"n": 0}
            continue
        s, l = sol[sel][m], lobt[sel][m]
        out["categories"][k] = {
            "n": int(m.sum()),
            "sol_total_median_min": round(float(np.nanmedian(s)) / 60.0, 1),
            "sol_total_superieur_a_2h": round(float(np.nanmean(s > 7200)), 3),
            "mvt_minus_lobt_median_min": round(float(np.nanmedian(l)) / 60.0, 1) if np.isfinite(l).any() else None,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default="", help="sinon : les mois cibles du developpement")
    ap.add_argument("--seuils", default="900,1800", help="secondes : seuils modere, fort")
    ap.add_argument("--sortir-csv", default="")
    args = ap.parse_args()

    paths = load_paths()
    prot = Protocol.from_config(load_config("splits.toml"))
    mois = args.months.split(",") if args.months else list(prot.dev_val_months)
    seuils = tuple(float(s) for s in args.seuils.split(","))

    f, resume = audit_months(mois, paths, seuils)
    runs = {n: Path(paths["write"]["reports"]) / f"{n}.eval.parquet"
            for n in ("causal-r2", "residual-r1", "ref-proxy-dev")}
    resume["erreur_par_categorie"] = croiser_erreur(f, runs).to_dict("records")

    # Sensibilite au seuil : la classification ne doit pas etre un artefact de reglage.
    resume["sensibilite_seuil"] = []
    for s in ((600, 1200), (900, 1800), (1200, 2400), (1800, 3600)):
        c = categories(f.ecart.to_numpy(), s).value_counts(normalize=True)
        resume["sensibilite_seuil"].append({"seuils": list(s),
                                            **{k: round(float(c.get(k, 0.0)), 4)
                                               for k in (CONCORDANT, MODERE, FORT, SANS_INFO)}})

    sortie = Path(paths["write"]["reports"]) / "AUDIT_SOURCES.json"
    sortie.write_text(json.dumps(resume, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.sortir_csv:
        f.to_parquet(args.sortir_csv, index=False)

    print(f"lignes auditees : {resume['lignes']:,} | seuils {resume['seuils_secondes']} s\n")
    print("repartition des categories")
    for r in resume["categories"]:
        print(f"   {r['categorie']:16s} n={r['n']:>9,d} ({r['part_lignes']*100:5.2f} %)  "
              f"cible med. {r['cible_mediane']:6.0f} s  p99 {r['cible_p99']:6.0f} s  "
              f"max {r['cible_max']:8.0f} s  ecart median {r['ecart_median']:+7.0f} s")
    print("\nles roulages longs sont-ils confirmes par les deux sources ?")
    for k, v in resume["roulages_long"].items():
        print(f"   {k} : n={v['n']:,}  concordants {v[CONCORDANT]*100:.1f} %  "
              f"desaccord modere {v[MODERE]*100:.1f} %  desaccord fort {v[FORT]*100:.1f} %  "
              f"sans info reseau {v[SANS_INFO]*100:.1f} %")
    print("\ntroisieme yardstick : le temps au sol total (decollage - horaire planifie) confirme-t-il ?")
    for k, v in resume["roulages_long_confirmes"].items():
        print(f"   {k} (n={v.get('n', 0):,})")
        for cat, d in v.get("categories", {}).items():
            if not d.get("n"):
                continue
            print(f"      {cat:16s} n={d['n']:>5,d}  sol total median {d['sol_total_median_min']:8.1f} min  "
                  f">2h dans {d['sol_total_superieur_a_2h']*100:5.1f} % des cas  "
                  f"decollage-LOBT median {d['mvt_minus_lobt_median_min'] if d['mvt_minus_lobt_median_min'] is not None else float('nan'):8.1f} min")
    print("\nerreur des modeles par categorie (evaluation sur 100 % des lignes)")
    for r in resume["erreur_par_categorie"]:
        print(f"   {r['modele']:14s} {r['categorie']:16s} n={r['lignes']:>9,d}  RMSE {r['rmse']:8.1f} s  "
              f"biais {r['biais']:+7.1f} s  part du carre d'erreur {r['part_du_carre_d_erreur']*100:5.1f} %")
    print(f"\necrit {sortie}")


if __name__ == "__main__":
    main()
