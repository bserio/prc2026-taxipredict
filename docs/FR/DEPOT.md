# Dépôt — ordre, contrôles, et décision du fichier unique

Document d'exécution pour l'équipe. Rien ici ne nécessite de rouvrir un modèle : les trois fichiers sont
déjà produits, gelés et contrôlés. Échéance officielle : **2026‑10‑14 12:00 CET (10:00 Z)**.

## Ce que les règles imposent (vérifié le 2026‑10‑10 sur les pages officielles)

| point | règle |
| --- | --- |
| métrique | RMSE sur les lignes du gabarit ; **le classement retient la meilleure soumission** de l'équipe |
| portée réelle | « The applied ranking will use RMSE for submitted predictions for the movements in **January and July 2026** » — le gabarit fait quatre mois, le score en note deux |
| dépôt | client MinIO uniquement (jamais l'interface web) ; `<team>_v<N>.parquet`, puis un unique `<team>_final.parquet` |
| quota | 5 soumissions/jour, 1 Go maximum par bucket |
| loyauté | les soumissions sont surveillées contre toute tentative d'« apprendre du classement ou de l'exploiter » |

Notre ligne tenue (D‑009, D‑036) : un **relevé unique** du fichier de référence, dont la RMSE locale est
connue d'avance, pour calibrer le facteur local→classement. Aucune itération de recette pilotée par les
scores affichés.

## Étape 0 — préparer les noms (5 minutes)

Le nom d'équipe est le seul élément manquant. Une fois connu :

```bash
cd prc2026-v1
EQUIPE=<nom-exact-de-l-equipe>          # identique au compte rendu aux organisateurs
cp submission/ATTENTE-nom-equipe_reference-proxy_v1.parquet  submission/${EQUIPE}_v1.parquet
cp submission/ATTENTE-nom-equipe_causal_v1.parquet           submission/${EQUIPE}_prediction_v2.parquet
cp submission/ATTENTE-nom-equipe_reconstitution_v1.parquet   submission/${EQUIPE}_reconstitution_v3.parquet

.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_v1.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_prediction_v2.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_reconstitution_v3.parquet
shasum -a 256 submission/${EQUIPE}_*.parquet      # a consigner dans DECISIONS.md
```

Chaque fichier doit être validé **sans erreur ni avertissement** : 670 790 lignes, identifiants et ordre du
gabarit, types conformes, valeurs finies. Les trois fichiers attendus, avec leur empreinte complète :

| fichier source | piste | RMSE locale janv.+juil. | destination après renommage | SHA‑256 |
| --- | --- | ---: | --- | --- |
| `submission/ATTENTE-nom-equipe_reference-proxy_v1.parquet` | référence sans apprentissage | 643,6 s | `${EQUIPE}_v1.parquet` | `d0ab0cb87d0fea373b90ff3227c685e8bd0b7aeb8a3919fcd8c06a0dc04cda3e` |
| `submission/ATTENTE-nom-equipe_causal_v1.parquet` | prédiction causale | 603,5 s | `${EQUIPE}_prediction_v2.parquet` | `dd0050319e63c00677a4ee05b772fbcee8bde8c862443fe2c8c4ddfeb5eaf3af` |
| `submission/ATTENTE-nom-equipe_reconstitution_v1.parquet` | reconstitution | 519,9 s | `${EQUIPE}_reconstitution_v3.parquet` | `66223d9b23c005f4cd2fd9c1f7769100baa6684186ba39e8be4ca418425f8870` |

Le renommage ne change pas les octets : les empreintes doivent se retrouver à l'identique sous les nouveaux
noms. Les trois fichiers sont **régénérables** — commandes `src.predict` (pistes `hybrid`, `causal`,
`residual`) dans le README §9 ; revérifié le 2026‑10‑10, les trois empreintes ont été retrouvées à l'octet
près après regeneration. Si une empreinte diffère, ne pas déposer : la recette ou les entrées ont bougé.

## Étape 1 — dépôt de mesure : le fichier de référence d'abord

```bash
# alias MinIO : cles generees depuis le compte OpenSky (instructions officielles, section « Using MinIO client »)
mc alias set prc2026 https://<endpoint-minio> <CLE> <SECRET>
mc cp submission/${EQUIPE}_v1.parquet  prc2026/<bucket-equipe>/${EQUIPE}_v1.parquet
```

**Ce qu'on attend** (D‑036) : comme le classement ne note que janvier + juillet, la comparaison locale utile
est **643,6 s** (et non les 591,7 s des quatre mois). Après application du facteur mesuré sur les vraies
étiquettes d'arrivée (×1,045 à ×1,067), l'ordre de grandeur attendu est **≈ 672 – 687 s**.

- Si le score officiel tombe dans cette fourchette : le facteur local→classement est confirmé, on passe à
  l'étape 2 sans autre mesure.
- S'il en sort nettement : c'est une information sur la **population des départs** que les arrivées ne
  pouvaient pas donner. On consigne l'écart dans `DECISIONS.md`, on recalcule les deux autres fichiers
  attendus avec le facteur mesuré — et on s'arrête là : pas de nouvelle soumission pour affiner.

## Étape 2 — choisir le fichier unique `<team>_final.parquet`

Le classement retient la meilleure soumission, mais vous ne voulez qu'un fichier final. Le choix se fait sur
le tableau ci‑dessous, corrigé du facteur (mesuré D‑036, confirmé éventuellement par l'étape 1) :

| fichier | local janv.+juil. | attendu au classement | nature de la mesure |
| --- | ---: | ---: | --- |
| référence (proxy + biais) | 643,6 | ≈ 672 – 687 s | transparente, sans apprentissage |
| prédiction (causale) | 603,5 | ≈ 631 – 644 s | ne lit aucune information postérieure au pushback |
| reconstitution (proxy + correction) | **519,9** | **≈ 543 – 555 s** | lit l'heure de décollage présente dans les entrées |

Les trois chiffres sont des RMSE **sur janvier + juillet**, population et lignes du classement. L'écart de la
reconstitution sur la prédiction (−13,9 %) se retrouve sur chacun des quatre mois et sur la réserve interne
(−18,2 %), donc il ne dépend pas d'un mois chanceux ; en revanche il repose sur une information que nous
qualifions nous‑mêmes de postérieure au départ (`FEATURE_ADMISSIBILITY.md`, D‑004). Les règles ne fixent
aucun instant et n'interdisent aucune colonne — mais l'absence d'interdiction ne vaut pas autorisation, et la
décision vous appartient. Deux phrases prêtes à citer dans la réponse, selon le choix :

- *reconstitution retenue* : « Le règlement ne fixe aucun instant de prédiction ; notre solution exploite les
  temps réellement réalisés fournis avec les entrées, et nous documentons séparément une variante purement
  prédictive (603,5 s sur janvier+juillet) pour que le lecteur puisse juger l'écart. »
- *prédiction retenue* : « Nous avons volontairement écarté toute information postérieure au pushback ; la
  variante qui lit l'heure de décollage réellement fournie dans les entrées atteindrait ≈ 543 – 555 s, nous
  la documentons sans la déposer. »

```bash
cp submission/${EQUIPE}_<choix>.parquet  submission/${EQUIPE}_final.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_final.parquet
mc cp submission/${EQUIPE}_final.parquet prc2026/<bucket-equipe>/${EQUIPE}_final.parquet
```

## Étape 3 — consignation (obligatoire pour l'éligibilité)

1. Dans `DECISIONS.md`, ajouter la décision de dépôt : fichier retenu, score officiel relevé à l'étape 1,
   empreinte SHA‑256 du fichier final, date et heure.
2. Rappeler les deux obligations d'éligibilité non encore remplies : **code public sous GPLv3** sur GitHub
   (fork du compte du challenge — le dépôt local n'a encore **aucun commit**, à créer avant publication) et
   **nom d'équipe** cohérent partout (`RULES.md`, section Éligibilité).
3. Conserver les journaux `reports/` et ce dossier : la reproductibilité fait partie du prix.

## Ce qu'il ne faut PAS faire

- Itérer des variantes en fonction des scores affichés : c'est exactement la pratique visée par l'avertissement
  officiel, et notre réglage est de toute façon terminé : trente‑deux expériences consignées dans
  `experiments/REGISTRY.md`, aucune variante adoptée hors les deux pistes gelées.
- Déposer un fichier partiellement rempli « pour voir » : le script de classement refuse toute ligne
  manquante ou en trop, et cela consommerait une place.
- Utiliser les scores du classement comme donnée d'entrée d'un modèle ou d'un choix de variables.
