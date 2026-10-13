# Clean-room — ce qui a été lu, et ce qui ne l'a jamais été

Constat vérifiable : le dossier voisin `~/opencode/EuroControlPRC` contient très probablement un
travail antérieur sur le même concours. Il est traité comme **interdit**.

## Jamais ouvert, lu, copié ou exécuté

- `~/opencode/EuroControlPRC` (et tout ce qu'il contient : code, modèles, poids, notebooks,
  soumissions, carnets d'expériences, résultats de classement antérieurs) ;
- aucun dépôt GitHub tiers contenant une solution au PRC Data Challenge 2026 ;
- aucune prédiction, métrique ou score obtenu lors d'une session antérieure sur le même classement.

Aucune commande de ce projet n'a listé, `cat`‑té, importé ou exécuté un fichier de ce dossier.
Le présent dépôt ne contient aucun chemin absolu vers l'extérieur du projet, sauf la racine des
données officielles (`configs/paths.local.toml`, générée par copié‑collé du chemin fourni).

## Ce qui a été utilisé

| source | usage | tracabilité |
| --- | --- | --- |
| dossier officiel `10-09-2026-09-52-54_files_list/` | seules données d'entrée, en lecture seule | hachage SHA‑256 des fichiers enregistré à chaque exécution (`--no-fingerprint` désactive) |
| pages officielles du challenge | règles, métrique, calendrier, schéma | URLs et citations dans `RULES.md` |
| documentation publique de LightGBM / pandas / numpy | API des bibliothèques | aucune idée de solution importée d'un tiers |
| paquets installés depuis le cache local `uv` | environnement reproductible | `requirements.lock.txt` (empreintes SHA‑256) |

## Données externes et météo

- **Aucune** donnée externe n'est téléchargée ni utilisée : pas de météo, pas de coordonnées
  d'aéroports, pas de plans de pistes, pas de calendriers NOP hors fichiers fournis.
- Le prompt indiquait que la météo serait inutile pour la RMSE visée ; elle n'a donc jamais été
  demandée, et rien n'a été ajouté qui rendrait la solution non reproductible hors du dossier fourni.
- Conséquence licence : l'éligibilité au prix exige « aucune donnée externe non ouverte » ; le
  projet n'utilise que les données du challenge, donc ce point est satisfait par construction.

## Météo et variables non fournies : décision documentée plutôt que silencieuse

Aucune approximation maison (distance piste‑stand, distance parcourue) n'est introduite sans
source dans les fichiers fournis. Les seules quantités dérivées sont des agrégations des colonnes
fournies (débits réseau par créneau, moyennes par STAND, écart aux horaires planifiés).

## Code et licence

- Le dépôt devra être publié sous **GNU GPLv3** avant la clôture pour l'éligibilité au prix
  (action restante listée dans `DECISIONS.md`, D‑008).
- Aucune réutilisation d'implémentation existante : si cela devait arriver, l'accord des auteurs
  et des modifications algorithmiques significatives seraient requis ; ce n'est pas le cas ici.

## Auto‑évaluation honnête

- Risque résiduel : la mémoire de session peut contenir des faits généraux sur les temps de
  roulage (culture de domaine), inévitables et non spécifiques au concours.
- Ce qui n'a **pas** été fait volontairement : chercher en ligne une solution au challenge, sonder
  le classement pour déduire des cibles, ou réutiliser un modèle antérieur.
