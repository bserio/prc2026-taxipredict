# Qu'est-ce qu'une prédiction a le droit de savoir ? (audit des champs à l'instant t0)

Document d'audit, écrit le 2026‑10‑10 après la relecture des pages officielles. Il répond à une
question que les règles ne tranchent pas : **à quel moment se place-t-on pour prédire, et que sait-on
à ce moment-là ?** Les règles officielles ne fixent aucun instant de prédiction et n'interdisent
aucune colonne (`RULES.md`, section « Ce que les règles ne disent pas »). Nous prenons donc une
position explicite, nous la chiffrons, et nous écrivons ce qu'elle coûte.

## 1. L'instant choisi, et pourquoi il n'est pas observable dans ces fichiers

Nous appelons **t0** le moment où l'on imaginerait un aiguilleur-demandeur cherchant à prédire le
roulage : juste avant la poussée (pushback). Ce qui rend l'exercice honnête ici, c'est que **le vrai
t0 n'est pas dans les fichiers de la finale** :

| information | présent dans les entrées 2026 ? | ce que ça interdit d'affirmer |
| --- | --- | --- |
| `BLOCK_TIME_UTC_mvt` (pushback réel, donc le vrai t0) | masqué à 100 % | on ne peut pas vérifier qu'une variable était bien déjà connue *à cet instant* |
| `MVT_TIME_UTC_mvt` (décollage réel) | **présent à 100 %** | son usage n'est pas une prédiction mais une reconstitution (piste séparée, D‑004) |
| `TAXITIME_SEC_mvt` (la cible) | masqué à 100 % | — |

Notre ancre de calcul est donc **l'horaire programmé** `SCHED_TIME_UTC_mvt`, pas le pushback réel.
Conséquence écrite : tout ce que nous appelons « connu à l'avance » signifie « inscrit dans la
planification dont l'instantané nous a été livré », et non « garanti disponible à la seconde du
pushback ». Cette nuance est la seule chose que nous ne puissions pas prouver, et c'est pour cela
qu'elle figure en tête de document plutôt qu'en note de bas de page.

## 2. Table de disponibilité, variable par variable

Statut : **certaine** = inscrite dans la planification avant le vol ; **ambiguë** = peut changer entre
l'instantané et le pushback ; **absente du jeu** = n'existe dans aucun fichier fourni. Les taux
d'absence sont mesurés sur les quatre mois de développement 2025 **et** sur les entrées officielles
2026 (`python` + `pandas`, même calcul des deux côtés).

| variable du modèle | provenance | statut à t0 | absence 2025 | absence 2026 |
| --- | --- | --- | ---: | ---: |
| heure, jour, semaine, saison | `SCHED_TIME_UTC_mvt` | certaine (horaire publié) | 0,000 % | 0,000 % |
| aéroport de départ | `ADEP_mvt` | certaine | 0,000 % | 0,000 % |
| type d'appareil (mouvement) | `AIRCRAFT_TYPE_mvt` | certaine | 0,097 % | 0,093 % |
| règles de vol (mouvement) | `FLIGHT_RULE_mvt` | certaine | 0,019 % | 0,007 % |
| **poste de parking** | `STAND_mvt` | **ambiguë** — un poste peut être réaffecté après l'instantané | 0,002 % | 0,001 % |
| type d'appareil (déclaré réseau) | `AIRCRAFT_TYPE_flt` | certaine, mais 1,34 % de vols sans fiche réseau | 1,338 % | 1,353 % |
| catégorie de turbulence de sillage | `WK_TBL_CAT_flt` | idem | 1,340 % | 1,357 % |
| segment de marché | `MARKET_SEGMENT_flt` | idem | 1,338 % | 1,353 % |
| type de vol (régulier/affrété) | `FLIGHT_TYPE_flt` | idem | 1,338 % | 1,353 % |
| règles de vol (réseau) | `FLIGHT_RULE_flt` | idem | 1,340 % | 1,357 % |
| opérateur (anonymisé) | `AIRCRAFT_OPERATOR_flt` | idem | 1,338 % | 1,353 % |
| écart à l'horaire estimé M1 | `EOBT_1_flt` | certaine à la planification, **révisée jusqu'au pushback** | 1,338 % | 1,353 % |
| écart à l'horaire initial | `IOBT_flt` | idem | 1,338 % | 1,353 % |
| écart au dernier pushback connu | `LOBT_flt` | **la plus tardive des trois** — la plus exposée à cette hypothèse | 1,338 % | 1,353 % |
| congestion « créneaux d'avant / maintenant / après » | comptages calculés sur les `SCHED_TIME` de tous les vols | certaine en tant que *plan* ; ignore les retards réalisés | — | — |
| offsets poste→piste, distance attendue à la piste | appris du taxi‑in des **arrivées** des mois d'entraînement | certaine (géométrie d'aéroport) | — | — |
| météo (vent, visibilité, neige) | **absente du jeu de données** | — | — | — |

Deux lectures importantes de ce tableau :

- **les absences ne sont pas des colonnes mal remplies.** Chaque colonne `*_flt` est vide à 1,34 %
  (2025) et 1,35 % (2026) — et ce sont **les mêmes lignes** : sur ces vols, les onze colonnes réseau
  manquent *à la fois*. C'est une propriété de la ligne (vol non enregistré par le réseau), pas une
  qualité inégale des champs. Sur cette poche, 12 variables de modèle sur 34 se retrouvent sans
  valeur ; elles pèsent **12,2 %** des décisions du modèle (mesure `lightgbm`, gain cumulé).
- **les colonnes `*_mvt` sont pleines.** Poste 0,001 %, aéroport et horaires 0,000 % sur les entrées
  officielles : la piste de prédiction ne dépend pas du réseau pour son information principale.

## 3. Ce que coûte le doute, chiffré avant toute décision

Plutôt que d'argumenter sur l'ambiguïté du poste ou de `LOBT`, nous l'avons mesurée de deux façons.

**(a) Effacement à l'inférence** (modèle gelé rejoué, aucune réentraînement) : ramener le poste à sa
valeur « poste inconnu » coûte **+8,5 %** de RMSE au total — et la perte est **plus forte sur les durées
ordinaires** que sur les anomalies :

| durée réelle | part des lignes | gelé | sans poste | perte |
| --- | ---: | ---: | ---: | ---: |
| 0–20 min | 76,4 % | 238,1 s | 270,2 s | **+13,5 %** |
| 20–40 min | 22,3 % | 421,5 s | 487,2 s | **+15,6 %** |
| 40–60 min | 1,0 % | 1 387,0 s | 1 526,1 s | +10,0 % |
| > 60 min | 0,3 % | 7 111,4 s | 7 479,0 s | +5,2 % |

Autrement dit : le poste est une information du **ventre de la distribution** (il dit « tel poste à Rome
roule en général 12 minutes, tel autre 35 »), pas une information de queue. Neutraliser `LOBT` ne coûte
que **+1,0 %** : ce champ-là est secondaire. *Réserve méthodologique : effacer une variable à l'inférence
mesure une dépendance, pas exactement un réentraînement ; les chiffres (a) sont donc indicatifs.*

**(b) Réentraînements complets** (variantes `causal-r10-nostand`, `causal-r11-nolobt`, quatre plis tenus
hors, tout le reste identique — mesure définitive, D‑035) :

| variante | janvier | février | juin | juillet | janv.+juil. | global | bootstrap apparié |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| référence `causal-r2` | 540,0 | 555,4 | 459,0 | 650,2 | 603,5 | **557,1** | — |
| sans poste (ni `STAND`, ni géométrie) | +2,64 % | +1,58 % | +2,20 % | +1,48 % | **+1,90 %** | 567,6 | IC95 [1,0129 ; 1,0265] → perte établie |
| sans `LOBT_flt` | +0,10 % | −0,14 % | +0,20 % | +0,01 % | **+0,04 %** | 557,3 | IC95 [0,9992 ; 1,0016] → non départageable |

Et la localisation de la perte du poste, sur les lignes appariées : **0–20 min (76,4 % des lignes)
+7,96 %** ; 20–40 min +2,27 % ; 40–60 min +0,84 % ; > 60 min **+0,45 %**. Le poste est donc une information
du **ventre de la distribution**, pas de la queue — l'inverse de l'intuition testée. `LOBT`, à l'inverse, ne
coûte rien à retirer : si son statut était jugé trop tardif, la version épurée se défend sans perte mesurable.

## 4. Ce que nous écrivons noir sur blanc dans la réponse

1. La piste **prédiction** n'utilise aucune information postérieure au pushback *telle qu'elle est
   définie dans le dictionnaire officiel* (`MVT_TIME`, `BLOCK_TIME`, `AOBT_3` exclus, contrôlés par
   tests automatisés : les passer à `NaN` ne change rien à ses variables).
2. Elle traite `STAND_mvt` comme une **affectation de planification**, et les trois écarts d'horaire
   comme la **dernière version connue** à la date de l'instantané. Ces deux hypothèses sont
   invérifiables depuis un instantané unique, et le document le dit au lieu de les cacher.
3. Si ces hypothèses étaient jugées trop fortes, la variante sans poste existe et son coût est mesuré :
   il se chiffre en pourcentage de score, pas en adjectif.
4. La piste **reconstitution** (proxy `décollage − AOBT_3`) n'est **pas** une prédiction au sens de ce
   document : elle lit le décollage réel. Elle est nommée, chiffrée et laissée au choix de l'équipe
   (D‑004), jamais mélangée à la précédente.

## 5. Reproduction des chiffres de ce document

```bash
# taux d'absence par colonne, 2025 (mois de dev) et 2026 (entrées officielles) :
PYTHONPATH=. .venv/bin/python scripts/null_rates.py
python -m src.audit                          # audit complet des deux sources d'off-block (reports/AUDIT_SOURCES.md)
python -m src.train --config configs/tabular_causal_nostand.toml --run-id causal-r10-nostand
python -m src.train --config configs/tabular_causal_nolobt.toml  --run-id causal-r11-nolobt
python scripts/check_adoption.py reports/causal-r10-nostand.json reports/causal-r2.json
```
