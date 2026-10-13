# Protocole de validation (figé avant toute recette gelée)

## Métrique principal

RMSE **globale** sur toutes les lignes évaluées, comme la métrique officielle. Les rapports par
mois, par aéroport, la MAE, le biais (`moyenne(pred − cible)`) et la couverture sont secondaires
et ne servent jamais à choisir une recette. La moyenne non pondérée des RMSE mensuelles est
explicitement rejetée : un test (`tests/test_metrics.py::test_rmse_non_ponderee_par_groupe`) en
vérifie la divergence.

Aucune ligne n'est écartée du score de validation, y compris les cibles physiquement
impossibles : l'organisateur ne les retire pas, et une exclusion silencieuse améliorerait le
score sans améliorer la soumission. La distribution des erreurs est reportée séparément pour
comprendre, pas pour marquer.

## Partitions (`configs/splits.toml`)

- 12 mois d'entraînement 2025 : janvier → décembre.
- **Plis de développement** : un mois tenu hors parmi `2025-01`, `2025-02`, `2025-06`, `2025-07`
  — les quatre mois dont la distribution doit être prédite en finale (janvier, février, juin,
  juillet 2026). Chaque pli entraîne sur les autres mois de développement.
- **Réserve interne** : `2025-11` + `2025-12`. Jamais utilisée pour l'entraînement, le réglage
  ou le choix de recette. Ouverture **unique**, après gel de la recette et accord explicite,
  comme estimation non réutilisable de la performance finale.
- La réserve est postérieure à tous les plis ; aucun pli n'inclut la réserve (`tests/test_temporal_splits.py`).

## Règles anti‑fuite appliquées au code

1. Encodages par cible (aéroport, opérateur, type d'appareil, STAND), moyennes de congestion et
   statistiques de géométrie sont ajustés **uniquement sur le mois d'entraînement** du pli, puis
   appliqués tels quels au mois validé (`tests/test_features_no_leak.py`).
2. Le lissage des encodages utilise une constante et un prior issus de l'entraînement seulement.
3. Les colonnes post‑hoc sont retirées du cadre avant ajustement *et* transformation en piste
   causale ; un test passe ces colonnes en NaN et vérifie que la matrice de variables est
   inchangée, plus un test d'inventaire qui refuse toute colonne interdite.
4. Les agrégations temporelles (débits réseau) sont calculées sur la fenêtre soumise à la
   transformation, jamais sur un mélange entraînement + validation.
5. Quand une variante utilise du trafic **réalisé** avant l'ancre (`src.refattente`), les fenêtres sont
   strictement antérieures à l'ancre, les événements futurs sont exclus, et le vol évalué est exclu de ses
   propres compteurs : `tests/test_observed_traffic.py` contrôle ces trois propriétés.

## Réglage et sélection

- Early stopping sur un sous‑ensemble **tiré du mois d'entraînement** (jamais du mois validé),
  afin que le nombre d'itérations ne soit pas choisi avec l'étiquette du pli évalué.
- **Règle d'adoption en vigueur (D‑029)** : RMSE inférieure d'au moins **1 % sur chacun des quatre mois
  cibles**, calculée sur 100 % des lignes, **et** bootstrap apparié par ligne dont l'intervalle à 95 % du
  rapport de RMSE exclut 1. Les deux conditions à la fois ; `scripts/check_adoption.py` les applique
  mécaniquement. Historique : seuil initial 0,5 % relevé à 2 % (D‑026) car avec 74 % du carré d'erreur dans
  1,34 % des lignes, quelques dixièmes de pour cent sont du bruit ; complété par le bootstrap le 2026‑10‑10
  (D‑029).
- **Portée réelle du classement** (page d'accueil, relue le 2026‑10‑10) : la RMSE officielle est calculée sur
  **janvier et juillet 2026**. Toute comparaison destinée à une décision de dépôt est donc lue en priorité sur
  **janvier + juillet combinés** (`scripts/d035_sensitivity.py` le fournit), les quatre mois restant le garde‑fou
  de stabilité exigé par la règle ci‑dessus.
- Le critère est unique : aucun argument secondaire (erreur par catégorie, élégance du modèle) ne peut
  faire adopter une variante qui échoue au test ci‑dessus.
- Le gel enregistre : empreinte des fichiers officiels (SHA‑256), version du venv, hash de la
  configuration et identifiant d'exécution (`experiments/REGISTRY.md`).

## Ce qui reste hors du protocole

- Les entrées officielles de finale (`final_ranking.parquet`) ne servent **qu'à l'inférence pour les
  départs** : aucune cible de départ n'y est disponible, elles n'entrent dans aucun pli.
- Elles contiennent en revanche les **temps de roulage réels des arrivées** (670 407 lignes). Nous les
  utilisons exactement deux fois, et jamais pour régler : contrôler la dérive de population 2025 → 2026
  (D‑034) et mesurer le facteur local → mois notés (D‑036). Aucune variante n'a été choisie d'après un
  chiffre calculé sur 2026.
- La RMSE réelle sur les départs de janvier/février/juin/juillet 2026 ne sera connue que par le classement
  officiel ; la réserve interne est notre seule estimation non contaminée (déjà consommée, D‑030).
- Un dépôt de mesure unique (fichier de référence, RMSE locale connue d'avance) est autorisé par les règles
  et documenté (`DEPOT.md`) ; aucune itération de recette pilotée par les scores affichés ne le sera
  (D‑009).
