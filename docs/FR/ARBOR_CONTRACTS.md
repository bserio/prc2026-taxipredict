# Contrats Arbor de cette session (état réel, vérifié par appels)

## État et identifiants

- `run_name` : `prc2026-v1`. Un appel `tree_view` a confirmé l'existence de l'arbre (racine `ROOT`,
  un nœud). Les métadonnées enregistrées sont les valeurs **mesurées**, pas des estimations :
  `baseline_score = 640,8` (moyenne globale sur le dev), `trunk_score = 557,1` (piste causale),
  `metric_direction = minimize`, `eval_timeout = 1800 s`.
- Arbre au moment de la rédaction :

| nœud | hypothèse | score dev | statut |
| --- | --- | ---: | --- |
| 1 | piste causale LightGBM | 557,1 | adopté (tronc) |
| 1.1 | exclure les cibles > 7200 s | 570,1 | refusée (D‑011) |
| 2 | reconstitution analytique + écrêtage | 566,6 | remplacée |
| 2.1 | proxy comme variable dans LightGBM | **490,8** | meilleure mesurée |

- `code_ref` de chaque nœud pointe vers le fichier de configuration et le rapport JSON réels, donc
  tout score affiché dans l'arbre est vérifiable dans `reports/`.

## Correspondance Arbor ↔ ce dépôt

| notion Arbor | équivalent ici |
| --- | --- |
| B_dev | les quatre mois tenus hors (janv, févr, juin, juil 2025) concaténés |
| B_test | **réserve interne nov + déc 2025**, volontairement jamais ouverte |
| tronc | `configs/tabular_causal.toml` (`causal-r2`) |
| expérience | un `run-id` avec son `reports/<id>.json`, ses modèles et sa config |
| worktree expérimentale | non utilisée : chaque recette est isolée par `--run-id`, les artefacts sont séparés, la donnée officielle est en lecture seule |

## Pourquoi aucune fusion Arbor n'a encore été faite (important)

`git_merge_branch` refuse une fusion **sans score B_test** et exige une amélioration sur ce score.
Or le protocole (D‑005) interdit d'ouvrir la réserve avant le gel de recette, sous peine de la
rendre inutilisable comme estimation non contaminée. Conséquence assumée :

- les décisions intermédiaires sont prises **uniquement** sur B_dev et tracées dans `DECISIONS.md` ;
- la fusion Arbor (ou son équivalent par branche git) n'interviendra qu'après gel, avec une
  ouverture unique de la réserve pour produire le score B_test ;
- aucun contournement du garde‑fou (par exemple en appelant la réserve « dev ») ne sera tenté :
  ce garde‑fou protège précisément la validité de l'estimation finale.

## Ce qui reste à vérifier côté Arbor

- `metric_direction = minimize` a été accepté par `tree_set_meta`, mais le comportement des
  médailles et des comparaisons de tronc n'a pas encore été observé avec une RMSE : à confirmer au
  premier dépôt de score officiel.
- Les commandes d'évaluation enregistrées utilisent un gabarit `{node_id}` ; la génération réelle
  de commande par l'outil n'a pas encore été exercée dans cette session.

## Ce qu'Arbor ne décide pas ici

Le choix entre piste causale et piste de reconstitution (D‑004) est une question d'admissibilité,
pas de score : l'arbre peut classer 490,8 < 557,1, ce n'est pas pour autant une autorisation de
dépôt. Cette décision reste écrite dans `DECISIONS.md` et soumise au responsable du projet.
