# Registre des experiences

Chaque ligne est reproduisible : `python -m src.train --config <config> --run-id <id>` (ou
`src.reconstruct` / `src.residual`). RMSE de developpement = les quatre mois tenus hors
(janv, fevr, juin, juil 2025) concatenes, aucune ligne exclue. La reserve (nov+dec 2025) n'a jamais servi a l'entrainement, au reglage ni au choix d'une recette ;
elle a ete evaluee **une seule fois**, le 2026-10-10 06:17, modeles deja geles (D-023, marqueur
`reports/RESERVE_OPENED.json`), et aucune decision n'en a ete tiree.

| id | config | piste | RMSE dev (s) | vs causal-r2 | statut | observation |
| --- | --- | --- | ---: | ---: | --- | --- |
| `baseline-mean` | `configs/baseline.toml` | reference | 640,8 | +15,0 % | ref. basse | moyenne globale de l'entrainement |
| `causal-r1` | `configs/tabular_causal.toml` | causale | 557,1 | — | gelable | premiere recette LightGBM |
| `causal-r2` | idem (+ persistance modeles) | causale | 557,1 | 0,0 % | **tronc causal** | sert de repli aux autres pistes |
| `causal-r3-nofilter` | `tabular_causal_nofilter.toml` | causale | 557,1 | 0,0 % | invalide | le filtre n'etait applique qu'aux encodages : identique a r1 par construction |
| `causal-r4-filtered` | `tabular_causal.toml` (filtre reel) | causale | 570,1 | **+2,3 %** | refusee | D‑011 : exclure la queue coute plus qu'il ne rapporte |
| `causal-r5-big` | `tabular_causal_big.toml` | causale | 569,7 | **+2,3 %** | refusee | seul `learning_rate` 0,05→0,03 a change (le `num_leaves` etait deja a 96) : ralentir sans regulariser degrade |
| `hybrid-r2` | `tabular_hybrid.toml` | reconstitution | 566,6 | +1,7 % | refusee | ecretage + repli moyenne‑heure |
| `hybrid-model-r1` | `tabular_hybrid_model.toml` | reconstitution | **490,8** | **−11,9 %** | meilleure mesuree | proxy comme variable, pas d'ecretage |
| `hybrid-model-r2-norwy` | `tabular_hybrid_model_norwy.toml` | reconstitution | 498,4 | −10,5 % | mesure D‑003 | retirer la piste réellement utilisée coûte +7,6 s (−1,5 %) |
| `residual-r1` | `tabular_residual.toml` | reconstitution | **479,9** | **−13,9 %** | **meilleure mesurée** | prédit l'écart au proxy, aucun écrêtage (D‑013) |
| `causal-r6-dest` | `tabular_causal.toml` + pression destination | causale | 569,1 | +2,2 % | **invalide** | mesure confondue : la config avait encore `train_filter = true` (rejeté par D‑011) → identique à `causal-r4-filtered` |
| `causal-r7-dest` | idem, filtre corrigé (`train_filter = false`) | causale | 556,7 | −0,1 % | neutre | pression destination sans confusion : gain nul en causal |
| `residual-r2-dest` | `tabular_residual.toml` + pression destination | reconstitution | 494,9 | −11,2 % | refusée | la même variable **coûte** 15 s en résiduel (D‑016) → désactivée par défaut |
| `residual-r3-long` | `tabular_residual_long.toml` (9000 itérations) | reconstitution | 480,6 | −13,7 % | refusée | capacité hors de cause : l'early stopping ne déclenche jamais, et 4000 → 9000 ne change rien |
| `residual-r4-gate` | `tabular_residual.toml --gate` | reconstitution | 479,9 | −13,9 % | neutre (filet) | la porte choisit le modèle pour les 10 aéroports sur les 4 plis : aucun arbitrage à faire |
| `residual-r5-spec` | `tabular_residual_spec.toml --specialist` (log1p) | reconstitution | 473,1 (pli janvier seul) | +5,2 % sur ce pli | **refusée au pli 1** | biais de retransformation : `expm1` d'une moyenne géométrique sous‑estime la queue → variantes corrigées ci‑dessous (D‑028) |
| `residual-r5-spec-raw` | `tabular_residual_spec_raw.toml --specialist` | reconstitution | 497,9 | +3,8 % | refusée (0/4 mois) | spécialiste entraîné sur les seuls vols sans fiche réseau : **la spécialisation nuit** (+1,4 à +5,5 % par mois) |
| `residual-r6-spec-tweedie` | `tabular_residual_spec_tweedie.toml --specialist` | reconstitution | 481,6 | +0,4 % | refusée (0/4 mois) | Tweedie 1,3 sans biais de retransformation : neutre au mieux — la poche a un plancher mesuré, pas un défaut de modèle |
| `causal-r8-regime` | `tabular_causal_regime.toml` | causale | 557,8 | +0,1 % | refusée (0/4 mois) | indicateur « aucune fiche réseau » redondant : les `miss_*` par colonne permettaient déjà la séparation |
| `residual-r7-calib-iso` | `tabular_residual_calib_iso.toml` (base isotonique par aéroport) | reconstitution | 490,4 | +2,2 % | **refusée (D‑031)** | −6,2 % mesurés sur la base seule ne se reportent pas : le modèle apprend déjà la pente via `proxy_sec`. Pire, l'isotonique s'aplatit hors de son domaine et écrête la queue → juillet +5,1 % |
| `residual-r8-calib-lin` | `tabular_residual_calib_lin.toml` (base `a + b·proxy`) | reconstitution | 480,2 | +0,1 % | refusée (D‑031) | exactement neutre : IC95 du rapport [0,9999 ; 1,0016]. La calibration déplace le travail de la base vers le modèle, elle n'ajoute rien |
| `residual-r9-tail-desac` | `tabular_residual_tail.toml --tail` (spécialiste \|AOBT_3−LOBT\| ≥ 30 min) | reconstitution | 480,4 | +0,1 % | **refusée (D‑033)** | a touché ses 34 553 lignes cibles et y a **perdu** (533,0 → 541,7 s) ; strictement identique ailleurs. Erreur de variance, pas de biais : 81 000 lignes d'apprentissage ne valent pas 1 750 000 |
| `causal-r10-nostand` | `tabular_causal_nostand.toml` (aucune variable issue de `STAND_mvt`) | causale | 567,6 | **+1,9 %** | **refusée (D‑035)** | coût établi (IC95 [1,0129 ; 1,0265]) et concentré sur le ventre : +8,0 % sur les 0‑20 min contre +0,45 % au‑delà de 60 min — l'inverse de l'hypothèse testée |
| `causal-r11-nolobt` | `tabular_causal_nolobt.toml` (ni écart à `LOBT` ni indicateur) | causale | 557,3 | +0,0 % | non adoptée (D‑035) | statistiquement gratuite (IC95 [0,9992 ; 1,0016]) : si `LOBT` était jugé trop tardif, son retrait ne coûterait rien de mesurable |
| `causal-r12-epochfix` | `tabular_causal.toml` après correction d'échelle de `epoch()` | causale | 558,7 | +0,3 % | non adoptée (D‑034) | les compteurs de congestion deviennent justes (4 créneaux par mois → ~2 976) sans gain mesurable : la planifiée était redondante avec heure + aéroport |
| `causal-r13-repro` | idem, repli de janvier seul, `epoch_seconds=false` | causale | 540,0 (janvier) | 0,0 % | contrôle | prouve que les recettes gelées et les fichiers fournis restent reproductibles à l'identique après la correction d'échelle |
| `causal-noplan-r1` | `tabular_causal_noplan.toml`, six variables de planification du poussage retirées (EOBT/IOBT via suppression après `transform`, LOBT via `plan_lobt=false`) ; 34 → 28 colonnes | causale | 559,5 | **+0,4 %** | **audit** (ne départage pas deux recettes) | pire cas chiffré de l'hypothèse de conception : si les trois champs réseau étaient jugés trop tardifs, la piste causale ne perdrait que 2,4 s au global (janv. +2,0 ; févr. +3,2 ; juin +3,5 ; juil. +1,4) |
| `refattente-r1` | `src/refattente.py` (causal + trafic réellement observé avant l'ancre) | causale + attente | 555,4 | −0,3 % | **refusée (D‑037)** | −0,32 % au global et sur janvier+juillet, mais janvier +0,87 % et juin +0,10 % → sous D‑029 ; les 9 variables observées pèsent ~11 % des décisions sans rendre 1 % |
| `arrival-transfer` | `src/arrival_transfer.py` (arrivées réelles 2026 comme vérité) | mesure de transfert | 271,1 local → **289,1 notée** | facteur **1,067** | acquis (D‑036) | première mesure du glissement local → période notée sur étiquettes réelles ; référence « moyenne par aéroport » : 1,045 |
| `causal-wit` | `tabular_causal.toml --witness` | causale | 355,0 (mars + octobre) | — | temoin | mois hors rotation normale : ne départagent jamais deux recettes |
| `residual-wit` | `tabular_residual.toml --split witness` | reconstitution | 278,7 (mars + octobre) | — | temoin | même écart relatif en faveur du résiduel que sur les mois cibles |
| `ref-proxy-dev` | `tabular_hybrid_noclip.toml` | référence | 591,7 | +6,2 % | fournie comme ancre | proxy brut + biais par aéroport, sans apprentissage ; sert de point de comparaison avec le classement officiel (D‑022) |
| `causal-final`, `residual-final` | gel sur 10 mois hors réserve | les deux | — | — | gelés | itérations prises de la médiane des plis (D‑017) ; trois soumissions produites localement, **jamais déposées sans accord** |

### Ouverture unique de la réserve interne (novembre + décembre 2025, 328 009 départs)

Exécutée le 2026‑10‑10 06:17 +0200, les trois recettes **dans la même commande** (le marqueur
`reports/RESERVE_OPENED.json` interdit toute seconde ouverture). Aucune ligne exclue.

| recette | RMSE réserve | hors lignes aberrantes | biais |
| --- | ---: | ---: | ---: |
| prédiction constante (moyenne 990,3 s) | 523,4 | 413,1 | — |
| `ref-proxy` (proxy + biais, sans apprentissage) | 470,0 | 344,3 | +3,4 |
| causale gelée (`causal-final`) | 432,8 | 342,5 | +8,3 |
| résiduelle gelée (`residual-final`) | **353,9** | **237,3** | −13,1 |

Lecture : l'écart en faveur du résiduel se retrouve hors données touchées (−18,2 % contre le causal),
mais novembre–décembre est nettement plus facile que les mois cibles — ce chiffre n'est **pas** une
prévision du classement. Aucun réglage n'a été décidé après cette ouverture (D‑023).

### Estimations poolées sur six mois tenus hors (les 4 mois cibles + les 2 témoins)

| recette | toutes les lignes | hors lignes aberrantes |
| --- | ---: | ---: |
| causale (`causal-r2` + `causal-wit`) | 497,2 | 362,2 |
| reconstitution (`residual-r1` + `residual-wit`) | **421,9** | **269,4** |

Les six mois portent 1 021 416 lignes dont 990 à cible invraisemblable. L'écart en faveur de la
reconstitution se retrouve sur chacun des quatre mois cibles (−16,7 %, −17,2 %, −10,2 %, −12,3 %).

## Detail qui compte pour la lecture du tableau

Repartition du carre d'erreur sur le dev (768 lignes cible > 7200 s = 0,04 % des lignes) :

| recette | RMSE hors aberrantes | RMSE sur les 768 lignes aberrantes |
| --- | ---: | ---: |
| `causal-r2` | 382,8 | 11 974 |
| `hybrid-model-r1` | **283,0** | 11 859 |

Autrement dit : le proxy ameliore fortement la population apprenable (−26 %) mais echoue, comme
tout le reste, sur les lignes invraisemblables — d'ou la formulation en residu (`residual-r1`),
qui reporte ces lignes sur le proxy lui‑même plutôt que sur une moyenne de feuille.

Par aéroport avec `hybrid-model-r1` (RMSE s) : LIRF 1 484 · LFPG 454 · LTFM 346 · EGLL 273 ·
LSZH 227 · LEBL 215 · EDDM 195 · EHAM 194 · EDDF 193 · LEMD 187. Rome concentre l'erreur restante.

## Audit d'hypothèse de conception (2026‑10‑12, lecture seule)

Question posée par l'équipe : les champs de planification du poussage (`EOBT_1`, `IOBT`, `LOBT`)
sont-ils écrits avant le roulage ? Deux mesures complémentaires, consignées ici :

1. **Signature d'écriture posthume** : sur les 2 085 047 départs de 2025, `LOBT` n'est égal
   exactement à `BLOCK_TIME` (poussage réel) que sur **0,44 %** des lignes comparables, avec un écart
   médian de **−251 s** en amont du poussage réel ; `AOBT_3`, la valeur réalisée, sert de témoin
   contrasté (écart médian −51 s, |moyenne| 17 s contre 366 s pour `LOBT`). Le profil de `LOBT` est
   celui d'un champ de planification, pas d'une trace d'exécution. Nuance consignée : environ un
   quart des lignes ont un `LOBT` postérieur au poussage réel (file +6 s au p75), compatible avec
   des révisions tardives du réseau, non avec une recopie systématique.
2. **Pire cas borné** : `causal-noplan-r1` retire les six variables concernées et ne perd que
   **+0,4 %** de RMSE (détail dans le tableau ci-dessus). Quelle que soit l'issue du débat sur ces
   champs, la piste causale ne s'appuie pas sur eux pour son écart à la reconstitution.

## Empreintes et environnement

- Empreinte SHA‑256 des fichiers officiels enregistree dans chaque `reports/<id>.json`
  (desactivee par `--no-fingerprint` pendant les explorations).
- CPython 3.13.14, lightgbm 4.7.0, pandas/numpy/pyarrow verrouilles (`requirements.lock.txt`).
- Artifacts par pli : `artifacts/<id>/fold-<mois>/{model.txt,spec.json,meta.json}`.
