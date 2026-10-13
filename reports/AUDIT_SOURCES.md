# Audit des sources — les deux mesures du même off‑block

Objectif : comprendre **pourquoi** certains vols affichent des temps de roulage énormes, sans
déclarer qu'une source a raison et l'autre tort, et sans rien enlever de l'évaluation.

## Méthode

La cible officielle vient des mouvements, le réseau en fournit une seconde :

```
cible (mouvements) = MVT_TIME - BLOCK_TIME_UTC_mvt
proxy (réseau)     = MVT_TIME - AOBT_3_flt
cible - proxy      = AOBT_3_flt - BLOCK_TIME_UTC_mvt      <- les deux sources se soustraient
```

Soustraire élimine `MVT_TIME` : l'écart restant est un **désaccord pur sur l'heure de pushback**.
Chaque vol est classé sans juger qui ment (`src/audit.py`) :

| catégorie | définition | lignes (mois cibles 2025) | part |
| --- | --- | ---: | ---: |
| concordant | \|écart\| ≤ 900 s | 643 966 | 95,93 % |
| désaccord modéré | 900–1 800 s | 14 231 | 2,12 % |
| désaccord fort | > 1 800 s | 4 111 | 0,61 % |
| sans information réseau | `AOBT_3` absent | 8 984 | 1,34 % |

Médiane de l'écart dans le désaccord fort : **+2 215 s** — le pushback *calculé par le réseau* est
environ 37 minutes **plus tardif** que celui déclaré par le mouvement. C'est dans ce sens‑là que se
situe le débat : le temps que le réseau attribue à l'attente *avant* le pushback, la cible officielle
le compte dans le roulage.

La classification ne dépend pas d'un réglage hasardeux — en faisant varier les seuils de 600/1200 s à
1800/3600 s, la part « sans information réseau » reste à 1,34 % et, pour les roulages au‑delà de deux
heures, la part concordante reste **à 0,4 % dans les quatre cas testés**.

## Réponse à la question posée

> Les vols à roulage long sont‑ils confirmés par les deux sources, ou portés par leur désaccord ?

| population | n | concordants | désaccord fort | sans info réseau |
| --- | ---: | ---: | ---: | ---: |
| cible > 3 600 s | 2 137 | 5,3 % à 18,0 % selon le seuil | 40 à 56 % | **25,6 %** |
| cible > 7 200 s | 259 | **0,4 %** (un seul vol) | 20,1 % | **79,5 %** |

Les roulages extrêmes ne sont donc **jamais corroborés** par deux mesures indépendantes : soit le
réseau n'a pas d'enregistrement pour ce vol (8 cas sur 10 au‑delà de deux heures), soit il est en
désaccord fort. Un seul vol cumule « cible > 2 h » et « les deux sources d'accord ».

## Troisième repère : le vol a‑t‑il vraiment traîné au sol ?

Les deux sources partagent le même `MVT_TIME`, donc un décollage faux les rendrait solidaires. Nous
avons donc comparé, pour ces mêmes vols, le **temps au sol total** (`MVT_TIME − SCHED_TIME`) et
l'écart au calcul pré‑départ du réseau (`MVT_TIME − LOBT_flt`) :

| catégorie (cible > 7 200 s) | n | temps au sol total médian | > 2 h dans | décollage − LOBT médian |
| --- | ---: | ---: | ---: | ---: |
| désaccord fort | 52 | 153,5 min | 100 % | 137,4 min |
| sans info réseau | 206 | 170,0 min | 92,7 % | — (pas de `LOBT` non plus) |

Ces vols ont bien passé des heures au sol : la valeur énorme n'est pas une erreur isolée de l'horloge
de décollage. Ce qui est disputé, c'est **l'imputation** — quelle part de ce temps au sol relève du
roulage après pushback, et laquelle de l'attente avant pushback.

## Erreur des modèles, par catégorie (évaluation sur 100 % des lignes)

| modèle | catégorie | n | RMSE | biais | part du carré d'erreur |
| --- | --- | ---: | ---: | ---: | ---: |
| causal | concordant | 643 966 | 306,2 s | +15,8 | 29,0 % |
| causal | désaccord modéré | 14 231 | 965,1 s | −641,1 | 6,4 % |
| causal | désaccord fort | 4 111 | 2 229,8 s | −1 692,5 | 9,8 % |
| causal | sans info réseau | 8 984 | 3 566,7 s | −109,4 | **54,9 %** |
| résiduel | concordant | 643 966 | **193,4 s** | +9,8 | 15,6 % |
| résiduel | désaccord modéré | 14 231 | 678,7 s | −289,1 | 4,2 % |
| résiduel | désaccord fort | 4 111 | 1 532,6 s | −926,7 | 6,2 % |
| résiduel | sans info réseau | 8 984 | 3 566,7 s | −109,4 | **73,9 %** |
| référence (proxy + biais) | concordant | 643 966 | 276,1 s | +17,3 | 20,9 % |
| référence | sans info réseau | 8 984 | 3 889,1 s | −525,7 | 57,8 % |

Trois lectures :

1. **L'erreur dominante est inauditable.** 1,34 % des lignes — celles sans enregistrement réseau —
   portent 55 % du carré d'erreur (causal) à 74 % (résiduel). Par construction, le modèle résiduel y
   est identique au causal (il retombe sur son repli) : toute la supériorité de la reconstitution
   vient des lignes auditablement concordantes, où elle passe de 306 s à **193 s**.
2. **Les biais négatifs sur les lignes en désaccord** (−1 693 s en causal) vont dans le sens d'une
   cible qui compte de l'attente avant pushback : aucun modèle, quelles que soient ses variables
   d'avant‑départ, ne peut deviner cette attribution.
3. **La levier « filtrer ou sous‑pondérer » est petit.** La classe « désaccord fort » ne pèse que
   0,61 % des lignes et 9,8 % (causal) / 6,2 % (résiduel) du carré d'erreur ; la classe dominante n'a
   pas de seconde source, donc **aucun signal de pondération n'existe pour elle**. C'est la raison
   chiffrée pour laquelle nous n'avons pas relancé les trois entraînements comparés : ils ne pouvaient
   agir que sur la plus petite des deux poches d'erreur.

## Limites, énoncées clairement

* Les deux sources partagent `MVT_TIME` : leur accord ne prouve pas la justesse du décollage (le vol
  concordant à 87 002 s l'illustre). Le troisième repère réduit ce risque, il ne le supprime pas.
* L'audit utilise une information **connue après le vol**. Elle n'est entrée dans aucune variable des
  deux pistes ; elle sert uniquement à diagnostiquer. En exploitation, rien de ce fichier n'est requis.
* Nous ne tranchons pas entre les sources : la cible du concours reste celle des mouvements, et
  l'évaluation conserve 100 % des lignes, y compris celles dont l'étiquette nous paraît douteuse.

## Décision associée

`docs/DECISIONS.md`, D‑024 : aucun filtrage ni sous‑pondération fondé sur l'accord des sources ; les
fichiers gelés restent ceux fournis. Ce rapport est joint à la documentation pour les organisateurs.
