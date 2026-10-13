# Projection du score officiel — piste residual (`residual-r1`)

Généré le 2026-10-10T13:04:30+0200. **Aucune étiquette 2026 n'existe ni n'est utilisée** : le proxy est calculé sur les entrées officielles, le profil d'erreur vient de mois tenus hors. Aucun score n'a été demandé au classement.

## 1. Contrôle de validité (rejouer la procédure sur un mois tenu hors)

| mois | projeté | réel | écart |
| --- | ---: | ---: | ---: |
| 2025-01 | 360.4 | 449.8 | -19.88 % |
| 2025-02 | 360.6 | 459.6 | -21.54 % |
| 2025-06 | 510.5 | 412.3 | +23.81 % |
| 2025-07 | 641.4 | 570.2 | +12.48 % |

Écart maximal **23.8 %**, dispersion résiduelle σ = 0.233 en log, soit un **facteur d'incertitude de ×1.58** sur le niveau.

La procédure est donc **bonne pour comparer des mois entre eux et mesurer une dérive de population**, mais **pas pour annoncer un niveau absolu** : à distribution de difficulté égale, deux mois réels diffèrent ici de ±20 %. Affiner les tranches n'y change rien (23,8 % → 22,7 % avec une queue en onze tranches) — ce qui varie d'un mois à l'autre n'est pas la fréquence des vols extrêmes mais **leur ampleur**, et elle n'est inscrite dans aucune colonne.

## 2. Projection sur les entrées officielles

Intervalle = incertitude d'estimation (bootstrap) **et** effet mois (×1.58).

| population | RMSE projetée | IC estimation | intervalle complet | lignes |
| --- | ---: | ---: | ---: | ---: |
| 2026-01 | 450.9 | [402.3 ; 518.4] | [285.6 ; 712.0] | 152,719 |
| 2026-02 | 395.7 | [347.5 ; 452.5] | [250.6 ; 624.8] | 144,158 |
| 2026-06 | 470.0 | [398.5 ; 534.4] | [297.6 ; 742.1] | 181,791 |
| 2026-07 | 564.8 | [468.9 ; 663.2] | [357.7 ; 891.9] | 192,122 |
| poolé | 480.8 | [400.8 ; 550.9] | [304.5 ; 759.2] | 670,790 |
| **janvier + juillet 2026** | **517.5** | — | [327.7 ; 817.2] | 344,841 |

Pour atteindre **385 s** sur janvier + juillet, il faudrait un gain de **26 %** par rapport à la projection centrale, ou **-18 %** si la population 2026 tombe dans le bas de l'intervalle. Un seul point du classement officiel — le score du fichier de référence, dont notre RMSE locale est connue — suffirait à lever l'essentiel de cette incertitude (D‑022).

## 3. Dérive 2025 → 2026 (population plus dure ou plus facile ?)

| population | mois | n | sans fiche réseau | proxy > 1 h | proxy > 2 h | Rome | médiane | p99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 (mois cibles, étiquettes connues) | — | 671,292 | 1.338 % | 0.101 % | 0.0012 % | 7.74 % | 957.0 | 2225.0 |
| 2026 (entrée officielle) | 2026-01 | 152,719 | 1.606 % | 0.369 % | 0.0 % | 7.24 % | 1001.0 | 2637.0 |
| 2026 (entrée officielle) | 2026-02 | 144,158 | 0.916 % | 0.078 % | 0.0014 % | 7.12 % | 956.0 | 2103.0 |
| 2026 (entrée officielle) | 2026-06 | 181,791 | 1.357 % | 0.164 % | 0.0006 % | 8.24 % | 958.0 | 2099.0 |
| 2026 (entrée officielle) | 2026-07 | 192,122 | 1.477 % | 0.177 % | 0.0026 % | 8.24 % | 965.0 | 2049.0 |
## 4. Profil conditionnel utilisé (RMSE par cellule, mois tenus hors)

| cellule | RMSE | n |
| --- | ---: | ---: |
| 0-900|LIRF | 379.1 | 25,206 |
| 0-900|autre | 187.8 | 267,335 |
| 1800-2700|LIRF | 622.4 | 90 |
| 1800-2700|autre | 462.2 | 17,325 |
| 2700-3600|autre | 759.3 | 1,837 |
| 3600-5400|LIRF | 986.6 | 2 |
| 3600-5400|autre | 678.0 | 649 |
| 5400-7200|autre | 1319.1 | 17 |
| 900-1800|LIRF | 446.8 | 25,981 |
| 900-1800|autre | 223.4 | 323,492 |
| >7200|LIRF | 425.5 | 2 |
| >7200|autre | 3489.8 | 6 |
| sans fiche réseau|LIRF | 12269.5 | 646 |
| sans fiche réseau|autre | 1428.8 | 8,704 |

### Replis appliqués (cellules trop peu nombreuses dans le profil)

- cellule 1800-2700|LIRF (poids 0.000) remplacée par sa tranche
- cellule 2700-3600|LIRF (poids 0.000) remplacée par sa tranche
- cellule 3600-5400|LIRF (poids 0.000) remplacée par sa tranche
- cellule 5400-7200|autre (poids 0.000) remplacée par l'erreur globale
- cellule 5400-7200|autre (poids 0.001) remplacée par l'erreur globale
- cellule >7200|LIRF (poids 0.000) remplacée par l'erreur globale
- cellule >7200|autre (poids 0.000) remplacée par l'erreur globale
