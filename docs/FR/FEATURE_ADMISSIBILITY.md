# Admissibilité des variables — deux pistes explicitement séparées

Contexte : les règles officielles **n'imposent aucun instant de prédiction** et **n'interdisent
aucune colonne** (voir `RULES.md`). L'absence d'interdiction ne vaut pas autorisation. Le projet
maintient donc deux recettes nommées, jamais mélangées silencieusement, avec une décision de
dépôt tracée dans `DECISIONS.md`.

## Colonne décisive : `MVT_TIME_UTC_mvt`

Dans les entrées de finale, pour les départs : `TAXITIME_SEC_mvt` et `BLOCK_TIME_UTC_mvt` sont
masqués (100 % null) par l'organisateur, mais `MVT_TIME_UTC_mvt` (décollage) est présent à 0 % de
null et `AOBT_3_flt` (off‑block réalisé M3) à 1,4 %. Comme la cible est exactement
`MVT_TIME − BLOCK_TIME`, l'organisateur fournit donc une quasi‑identité.

- Proxy mesuré sur 2025 : `RMSE(MVT_TIME − AOBT_3, cible) = 384,9 s` (MAE 238,1 s), contre
  546–640 s pour une constante et 557 s pour notre meilleur modèle causal.
- Cette information n'existerait pas à l'instant du pushback : elle caractérise une
  **reconstitution**, pas une prévision.

## Piste A — `causal` (prédiction)

Utilise ce qui est connu au moment de la planification/déroulé avant le décollage :
calendrier, aéroport, type d'appareil, opérateur, STAND, règle de vol, segment de marché,
retards planifiés (`EOBT_1`, `IOBT`, `LOBT`), congestion **planifiée** du réseau (débits
d'arrivées et de départs calculés sur `SCHED_TIME`), plus encodages appris sur l'entraînement.

Exclue : `MVT_TIME_UTC_mvt`, `AOBT_3_flt`, `BLOCK_TIME_UTC_mvt`, `RUNWAY_mvt` (piste réellement
utilisée), tout temps d'arrivée, et toute agrégation calculée en incluant le mois validé.

Justification de garder `EOBT_1/IOBT/LOBT` : ce sont des champs de **planification** — ils
reconstruisent mal le décollage (RMSE 677–740 s contre 384,9 s pour `AOBT_3`), ce qui est la
preuve empirique qu'ils ne fuient pas la cible.

## Piste B — `hybrid` (reconstitution assumée)

Même base + `proxy_sec = MVT_TIME − AOBT_3`, débits **réalisés** (congestion observée),
`RUNWAY_mvt`. Deux implémentations :

1. analytique (`src/reconstruct.py`) : cible = proxy corrigé d'un biais par aéroport, écrêtage
   optionnel sur les quantiles d'entraînement, repli vers le modèle causal quand le proxy est
   inutilisable (proxy nul ou hors [60 s ; 7200 s] : 1,5 % des lignes, RMSE locale ~3 500 s) ;
2. modèle (`configs/tabular_hybrid_model.toml`) : le proxy entre comme variable dans LightGBM,
   qui apprend lui‑même quand s'en méfier.

## Ce que montre la mesure (développement, 4 mois tenus hors)

| recette | RMSE globale | RMSE hors cibles aberrantes (> 7200 s) |
| --- | ---: | ---: |
| moyenne globale (référence basse) | 640,8 | — |
| A — causale | 557,1 | 382,8 |
| B — reconstitution analytique + écrêtage | 566,6 | 373,9 |
| empilement linéaire pondéré par aéroport | 538,3 | — |

Lecture honnête : sur la population apprenable, les deux pistes sont **quasi équivalentes**
(382,8 vs 373,9 s, −2,3 %), et l'empilement linéaire n'apporte que 19 s parce que les deux
pistes échouent sur les **mêmes** lignes invraisemblables. Le gain réel du proxy est d'entrer
comme variable dans le modèle, pas comme prédiction concurrente.

## Position de dépôt

- La piste A est celle qui répond au sujet (« prédire le temps de roulage ») et à l'esprit des
  règles ; elle sert de **solution par défaut** et de repli.
- La piste B est produite et documentée, étiquetée « reconstitution », et ne sera soumise que
  sur décision explicite assumée dans `DECISIONS.md` (D‑004), parce qu'un classement obtenu avec
  le décollage fourni n'aurait pas la même signification.
- Aucune des deux pistes n'utilise quoi que ce soit issu du processus de classement : la limite
  officielle de 5 soumissions/jour est respectée, sans sondage exploratoire des cibles cachées.
