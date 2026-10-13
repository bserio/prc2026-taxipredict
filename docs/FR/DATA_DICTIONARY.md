# Dictionnaire des données (vérifié sur les fichiers, pas seulement la documentation)

## Fichiers du dossier officiel et rôle réel

| fichier | lignes | rôles vérifiés |
| --- | ---: | --- |
| `training_2025-MM-01_*.parquet` ×12 | 4 167 797 au total | apprentissage + validation ; cible présente, jamais nulle |
| `ranking.parquet` | 689 534 | phase précédente : janvier + juillet 2026 (les deux mois **notés**), cibles départs masquées, **arrivées étiquetées** à 100 % ; identifiants ⊂ `final_ranking` (689 534 sur 689 534) |
| `submitting.parquet` | 344 841 | gabarit de la phase précédente (= départs de `ranking.parquet`) |
| `final_ranking.parquet` | 1 341 197 | **entrées officielles de la finale** : janv 305 590, févr 288 432, juin 363 231, juil 383 944 mouvements ; départs sans étiquette, **670 407 arrivées avec temps de roulage réel** sur les dix plateformes |
| `final_submitting.parquet` | 670 790 | **gabarit de la finale** : exactement les départs de `final_ranking.parquet` |

> Portée du classement (page d'accueil, relue le 2026‑10‑10) : « The applied ranking will use RMSE for
> submitted predictions for the movements in **January and July 2026** ». Le gabarit couvre quatre mois,
> le score en note deux (`RULES.md`).

Dates extrêmes 2025 : `2025-01-01 00:01:04` → `2025-12-31 23:57:36`. Aucun doublon sur
`MVT_ID_mvt` (4 167 797 identifiants uniques pour 4 167 797 lignes).

**Types du gabarit de finale** (vérifiés sur le fichier, correction d'un relevé antérieur erroné) :
`MVT_ID_mvt` **float64** et `TAXITIME_SEC_mvt` **float64** avec des `NaN` en attente de remplissage —
alors que la cible vaut `int32` dans les fichiers d'entraînement. `src.predict.py` ne durcit donc
aucun type : il reprend le dtype de la colonne du gabarit, ce que `src.validate_submission.py`
contrôle (une divergence de dtype est signalée comme avertissement).

## Schéma (30 colonnes) et statut d'admissibilité par piste

Suffixe `_mvt` = aéroport déclarant, `_flt` = liste de vols du Network Manager.

| colonne | type | nullité départs 2026 | usage causal | usage reconstitution |
| --- | --- | ---: | --- | --- |
| `MVT_ID_mvt` | double | 0,000 % | identifiant (max 2,14×10⁸ ≪ 2⁵³ → exact en flottant) | idem |
| `PHASE_mvt` | string | 0,000 % | filtre population | idem |
| `ADEP_mvt` / `ADES_mvt` | string | 0,000 % | aéroport (départ) / destination | idem |
| `SCHED_TIME_UTC_mvt` | timestamp | 0,000 % | **base calendaire et congestion planifiée** | idem |
| `AIRCRAFT_TYPE_mvt` | string | 0,093 % | variable appareil | idem |
| `AIRCRAFT_TYPE_flt`, `WK_TBL_CAT_flt` | string | 1,353 % / 1,357 % | variables appareil (réseau) | idem |
| `MARKET_SEGMENT_flt`, `FLIGHT_RULE_*`, `FLIGHT_TYPE_flt` | string | ≤ 1,357 % | variables d'exploitation | idem |
| `AIRCRAFT_OPERATOR_flt` | string (anonymisé) | 1,353 % | codage cible lissé | idem |
| `STAND_mvt` | string | 0,001 % | position de stationnement (135–380 par aéroport) | idem |
| `RUNWAY_mvt` | string | 0,000 % | **exclue** (piste réellement utilisée) | incluse |
| `EOBT_1_flt`, `IOBT_flt`, `LOBT_flt` | timestamp | 1,353 % | retards planifiés (voir preuve plus bas) | idem |
| `MVT_TIME_UTC_mvt` | timestamp | 0,000 % | **interdite** (décollage) | proxy |
| `AOBT_3_flt` | timestamp | 1,353 % | **interdite** (off‑block réel M3) | estimation de `BLOCK_TIME` |
| `BLOCK_TIME_UTC_mvt` | timestamp | **100 % null** | indisponible | masqué par l'organisateur |
| `TAXITIME_SEC_mvt` | int32 | **100 % null** | cible | cible |
| `ADES_FILED_flt`, `CALLSIGN_flt`, `FLIGHT_ID_mvt`, `FLIGHT_mvt`, `ARVT_1_flt`, `ARVT_3_flt` | — | — | non utilisées (identifiants, temps d'arrivée postérieurs) | idem |

**Les absences `_flt` ne sont pas des colonnes mal remplies.** Chaque colonne réseau est vide à
1,353 % (2026) et 1,338 % (développement 2025) — et ce sont **les mêmes lignes** : sur ces 1,35 % de
départs, les onze colonnes `_flt` manquent à la fois (vol non enregistré par le réseau). C'est une
propriété de la ligne, pas une qualité inégale des champs ; `T0_DISPONIBILITE.md` en tire les
conséquences, et `PYTHONPATH=. .venv/bin/python scripts/null_rates.py` reproduit ces pourcentages.

## Preuves mesurées sur 2025 (départs, 2 085 047 lignes)

- Identité officielle vérifiée : `TAXITIME_SEC_mvt == MVT_TIME_UTC_mvt − BLOCK_TIME_UTC_mvt`
  sur **100,000 %** des départs.
- Qualité reconstructrice si une colonne sert d'off‑block (`RMSE(MVT_TIME − X, cible)`) :

| source | RMSE (s) | nullité |
| --- | ---: | ---: |
| `AOBT_3_flt` | **384,9** | 1,08 % |
| `EOBT_1_flt` | 676,7 | 1,08 % |
| `IOBT_flt` | 739,8 | 1,08 % |
| `LOBT_flt` | 740,1 | 1,08 % |

  → les trois dernières sont des champs de **planification** (elles reconstruisent mal le
  décollage) : leur usage en piste causale est donc défendable ; `AOBT_3_flt` est un champ
  **réalisé**, réservé à la piste de reconstitution.
- Le proxy `MVT_TIME − AOBT_3` a une erreur de 384,9 s (MAE 238,1 s), exactement l'écart entre
  les deux sources d'off‑block (`AOBT_3 − BLOCK_TIME`, même RMSE contre zéro).
- Distribution de la cible par aéroport 2025 :

| aéroport | n départs | moyenne | médiane | p99 | max | % > 1 h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EDDF | 230 141 | 863 | 837 | 1 819 | 6 907 | 0,03 |
| EDDM | 167 334 | 812 | 774 | 1 921 | 6 899 | 0,04 |
| EGLL | 239 546 | 1 364 | 1 319 | 2 701 | 11 452 | 0,30 |
| EHAM | 247 951 | 785 | 742 | 1 774 | 11 032 | 0,03 |
| LEBL | 179 705 | 957 | 906 | 1 962 | 3 604 | 0,00 |
| LEMD | 212 242 | 1 015 | 985 | 1 932 | 3 598 | 0,00 |
| LFPG | 239 552 | 1 020 | 954 | 2 409 | **84 240** | 0,17 |
| **LIRF** | 160 704 | 1 195 | 1 025 | **4 019** | **131 167** | **1,22** |
| LSZH | 134 907 | 741 | 711 | 1 707 | **87 341** | 0,02 |
| LTFM | 272 965 | 1 053 | 963 | 2 587 | 10 309 | 0,29 |

- Valeurs physiquement impossibles présentes dans les étiquettes d'entraînement : cibles
  négatives (jusqu'à 0,22 % à LSZH) et > 2 h (jusqu'à 36 h à Rome). Elles sont conservées à
  l'apprentissage en L2 (la RMSE vise la moyenne conditionnelle) ; leur exclusion est une
  hypothèse testée séparément (`DECISIONS.md` D‑011).
