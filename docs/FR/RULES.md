# Règles officielles — PRC Data Challenge 2026 (finale)

Sources consultées le 2026‑10‑09, **relues le 2026‑10‑10** (la relecture a changé notre compréhension
de la portée du classement — voir ci‑dessous), pages officielles :

| source | contenu retenu |
| --- | --- |
| `https://prc-data-challenge-2026.netlify.app/index.html` | objectif, portée, calendrier |
| `https://prc-data-challenge-2026.netlify.app/ranking.html` | métrique, gabarit, dépôt, limites |
| `https://prc-data-challenge-2026.netlify.app/eligibility.html` (via `docs/01_eligibility.md`) | éligibilité au prix |
| `https://ansperformance.eu/study/data-challenge/dc2026/data.html` | données, colonnes, fichiers |

## Cible et population

> « The submitting dataset is the template to be filled with the predicted taxi‑out times,
> i.e. `TAXITIME_SEC_mvt` = `MVT_TIME_UTC_mvt` - `BLOCK_TIME_UTC_mvt` (for the departure). »
> — page Data, section *The Submitting Dataset*

- Cible : `TAXITIME_SEC_mvt` des **départs** (`PHASE_mvt = "DEP"`) ; le gabarit ne contient
  que les départs (vérifié : 670 790 lignes = exactement les départs de `final_ranking.parquet`).
- 10 aéroports : EDDF, EDDM, EGLL, EHAM, LEBL, LEMD, LFPG, LIRF, LTFM, LSZH.
- Les mouvements militaires, chefs d'État et sensibles sont retirés ; aucune donnée synthétique.

## Portée réelle du classement (précision obtenue à la relecture du 2026‑10‑10)

> « The applied ranking will use Root Mean Square Error (RMSE) for submitted predictions for the
> movements in **January and July 2026**. » — page d'accueil, section *Ranking*

- Le **gabarit** à remplir couvre les quatre mois (`final_submitting.parquet`, 670 790 départs :
  janvier, février, juin, juillet 2026) et le script de classement refuse toute ligne manquante ou
  en trop : nous remplissons donc bien les quatre mois.
- Mais le **classement** est calculé sur **janvier + juillet 2026**. Nos décisions de méthode doivent
  donc être jugées en priorité sur ces deux mois ; les quatre mois restent notre contrôle de stabilité.
- Les fichiers d'évaluation livrent, en plus des départs à prédire, les **arrivées avec leur temps de
  roulage réel** : `ranking.parquet` (janvier + juillet 2026, 8 plateformes de la phase précédente) et
  `final_ranking.parquet` (les quatre mois, sur nos dix plateformes, **670 407 arrivées étiquetées**).
  C'est de la vérité 2026 fournie par l'organisateur : nous l'utilisons comme **contexte observable**
  (trafic réellement posé avant l'ancre) et comme **contrôle de dérive**, jamais comme cible réglée,
  puisque notre population notée est celle des départs.

## Métrique et classement

> « Teams will be ranked based on the best Root Mean Square Error (RMSE) achieved across
> their submissions. » — page Ranking

- RMSE sur les lignes du gabarit ; toute ligne manquante, en trop ou tout `MVT_ID_mvt`
  non apparié fait échouer le script de classement.
- La moyenne non pondérée des RMSE mensuelles **n'est pas** la RMSE globale : notre rapport
  principal est donc la RMSE calculée sur toutes les lignes évaluées.

## Dépôt

- Classement : « Teams will be ranked based on the **best** Root Mean Square Error (RMSE) achieved
  across their submissions. » — la meilleure soumission d'une équipe compte ; les autres ne lui
  nuisent pas.
- Nom courant : `<team-name>_v<entier incrémental>.parquet` ; finale unique : `<team-name>_final.parquet`.
- 5 soumissions/jour, 1 Go maximum par bucket ; dépôt par client MinIO (jamais par le web).
- Avertissement officiel : les soumissions sont surveillées pour détecter toute tentative
  d'« apprendre du processus de classement ou de l'exploiter », considérée comme déloyale.
  → aucune soumission exploratoire pour soutirer de l'information sur les cibles cachées.
- **Ligne que nous nous fixons** : déposer en premier le fichier de *référence* (proxy + biais, sans
  apprentissage, RMSE locale connue d'avance) est un relevé unique et justifié — il calibre le facteur
  de transfert local→classement, et aucune recette n'est réglée avec ce chiffre. En revanche, itérer
  des variantes en fonction des scores affichés serait exactement la pratique visée par l'avertissement :
  nous ne le ferons pas. Tous les choix de modèle restent pris sur données locales (D‑009, D‑030).

## Calendrier

- Compétition du 1ᵉʳ septembre au **14 octobre 2026, 12:00 CET (10:00 Z)**, échéance prolongée.
- Objectif interne : recette gelée ≥ 24 h avant l'échéance.

## Éligibilité au prix

1. Aucune donnée externe non ouverte ; toute donnée additionnelle sous licence ouverte et documentée.
2. Code public sur GitHub sous **GNU GPLv3** (forké par le compte du challenge).
3. Documentation suffisante pour reproduire les résultats.
4. Solution originale : réutiliser une implémentation existante exige l'accord des auteurs **et**
   des modifications significatives de l'algorithme ou du modèle.

## Ce que les règles ne disent pas (et qu'il ne faut pas inventer)

- **Aucun instant de prédiction n'est spécifié** : aucun texte n'impose de prédire avant le
  pushback, avant le décollage, ou à tout autre moment.
- **Aucune liste de variables interdites** : les règles décrivent les colonnes, elles ne
  déclarent aucune colonne inutilisable.
- Conséquence méthodologique (prompt §6) : l'absence d'interdiction **ne prouve pas**
  l'admissibilité. Les deux pistes du projet sont donc explicitement étiquetées
  *prédiction* ou *reconstitution* dans `FEATURE_ADMISSIBILITY.md`, et la décision de dépôt
  est tracée dans `DECISIONS.md`.
