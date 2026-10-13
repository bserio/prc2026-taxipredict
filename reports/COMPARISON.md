# Comparaison des recettes — développement (mois tenus hors 2025)

RMSE en secondes, calculée sur les quatre mois tenus hors concaténés (janv, févr, juin, juil 2025),
**aucune ligne exclue**, conformément à la métrique officielle. La réserve interne
(nov + déc 2025) n'a pas été ouverte.

## Classement

| rang | recette | piste | RMSE (s) | vs tronc causal |
| ---: | --- | --- | ---: | ---: |
| 1 | `residual-r1` | reconstitution | **479,9** | −13,9 % |
| 2 | `hybrid-model-r1` | reconstitution | 490,8 | −11,9 % |
| 3 | `hybrid-model-r2-norwy` | reconstitution (sans piste réelle) | 498,4 | −10,5 % |
| — | tronc `causal-r2` | prédiction | 557,1 | — |
| — | `causal-r7-dest` | prédiction (+ pression destination) | 556,7 | −0,1 % (non concluant) |
| ref. | `baseline-mean` | moyenne globale | 640,8 | +15,0 % |

Recettes rejetées, conservées parce qu'elles instruisent : `causal-r4-filtered` 570,1 (+2,3 %,
D‑011), `causal-r5-big` 569,7 (+2,3 %), `hybrid-r2` analytique + écrêtage 566,6 (+1,7 %),
`residual-r2-dest` 494,9 (+3,1 % vs résiduel, D‑016), `residual-r3-long` 480,6 (neutralité de la
capacité : 4000 → 9000 itérations ne change rien).

## D'où vient l'erreur

Sur les 671 292 lignes évaluées, **768 lignes (0,11 %) ont une cible physiquement invraisemblable**
(> 7200 s ou ≤ 60 s) et concentrent la majeure partie du carré d'erreur.

| recette | RMSE hors lignes aberrantes | RMSE sur ces lignes |
| --- | ---: | ---: |
| `causal-r2` | 382,8 | 11 974 |
| `hybrid-model-r1` | **283,0** | 11 859 |
| `residual-r1` | 284,1 | 11 438 |

Répartition par aéroport (`residual-r1`) : LIRF 1 429 · LFPG 448 · LTFM 378 · EGLL 268 · LSZH 224 ·
LEBL 217 · EDDF 194 · EDDM 190 · EHAM 187 · LEMD 186. **Rome représente 7,7 % des lignes mais
environ 70 % du carré d'erreur** — c'est le premier levier restant, et aussi le plus difficile :
sur les lignes *normales* de Rome, le proxy brut (584 s) était déjà meilleur que le modèle absolu
(603 s), ce qui a motivé la porte par aéroport.

## Ce qui a été essayé et n'a pas marché

| hypothèse | mesure | verdict |
| --- | --- | --- |
| exclure les cibles aberrantes de l'apprentissage | 570,1 vs 557,1 | nuisible : la RMSE vise la moyenne conditionnelle |
| modèle plus lent et plus profond (causal) | 569,7 | nuisible |
| reconstitution analytique avec écrêtage aux quantiles | 566,6 | l'écrêtage détruit la queue qui domine le score |
| empilement linéaire causal + proxy, poids par aéroport | 538,3 | les deux pistes se trompent sur les mêmes lignes |
| pression réseau à l'aéroport de destination | résiduel 494,9 ; causal 556,7 | nuisible en résiduel, nul en causal → désactivé |
| davantage d'itérations en résiduel | 480,6 vs 479,9 | neutre : la capacité n'est pas le facteur limitant |

## Ce qui a marché

1. **Le proxy comme variable du modèle**, et non comme prédiction concurrente : −11,9 % (D‑012).
2. **La formulation en résidu du proxy**, sans aucun écrêtage : −2,2 % supplémentaires (D‑013),
   avec un gain borné par le fait que le proxy est *absent* sur 63 % des lignes aberrantes
   (87 % à Rome) — ces lignes retombent donc sur le repli causal.
3. **Garder la queue à l'apprentissage** en L2, contre l'intuition de nettoyage (D‑011).

## Position au moment du gel

- Piste **prédiction** : 556,7–557,1 s ; aucun réglage testé ne l'a améliorée de façon concluante.
- Piste **reconstitution** : 479,9 s, soit 13,9 % mieux que le tronc causal — mais elle lit
  `MVT_TIME` et `AOBT_3`, informations postérieures à l'off‑block (voir `FEATURE_ADMISSIBILITY.md`).
- La décision de dépôt (D‑004) reste à trancher par le responsable du projet : le classement
  officiel ne distingue pas les deux natures d'information.
