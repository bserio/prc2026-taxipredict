# Décisions — journal daté, avec la mesure qui les justifie

Convention : une décision porte un numéro `D‑xxx`, sa date, son statut (adoptée / révisée /
annulée), la preuve mesurée, et ce qui la rendrait fausse.

## D‑001 — Deux pistes séparées, jamais un mélange implicite (2026‑10‑09, adoptée)

Les règles ne fixent aucun instant de prédiction mais `MVT_TIME_UTC_mvt` est fourni dans les
entrées de finale. Plutôt que de trancher par une hypothèse muette, le projet maintient une piste
**causale** (prédiction au sens du sujet) et une piste **de reconstitution**, chacune nommée dans
chaque rapport. Révisable si l'organisateur précise l'instant de prédiction.

## D‑002 — `MVT_TIME` et `AOBT_3` exclus de la piste causale (adoptée)

Preuve : le proxy `MVT_TIME − AOBT_3` reconstruit la cible à 384,9 s contre 677–740 s pour
`EOBT_1/IOBT/LOBT`. Ces trois‑là restent donc dans la piste causale (champs de planification) ;
`AOBT_3` et `MVT_TIME` sont réservés à la reconstitution. Test anti‑fuite : passer ces colonnes en
NaN ne change en rien la matrice de variables causale.

## D‑003 — `RUNWAY_mvt` réel exclu du causal, variante mesurée (adoptée)

Coût estimé faible hors LSZH/LTFM/EHAM ; la variante avec piste réellement utilisée est exécutée
comme recette séparée pour chiffrer l'écart plutôt que le supposer.

## D‑004 — La soumission par défaut reste la piste causale (adoptée, décision de dépôt)

Justification : le sujet demande de *prédire* le temps de roulage ; une piste qui utilise
l'heure de décollage fournie produirait un score dont la signification n'est pas la même. La
piste de reconstitution est développée, mesurée et documentée, et ne sera déposée que sur
décision explicite — le classement officiel ne distingue pas les deux, c'est précisément pourquoi
la décision doit être écrite ici avant le dépôt.

## D‑005 — Réserve interne novembre + décembre 2025 (adoptée)

Plis de développement = janvier, février, juin, juillet 2025 (les mois cibles de la finale).
Novembre et décembre ne servent ni à l'entraînement ni au réglage ; ouverture unique après gel.

## D‑006 — RMSE globale non pondérée comme critère unique (adoptée)

La métrique officielle est une RMSE sur toutes les lignes ; la moyenne des RMSE mensuelles peut
conduire à un choix contraire (test dédié).

## D‑007 — Aucune ligne écartée du score de validation (adoptée)

L'organisateur n'en retire aucune. Exclure silencieusement les lignes difficiles gonflerait le
score sans améliorer la soumission. La répartition des erreurs est reportée à part.

## D‑011 — Les cibles aberrantes restent à l'entraînement en L2 (2026‑10‑09, adoptée après mesure)

- Hypothèse initiale : les 768 lignes > 7200 s du dev (0,04 % des lignes, 53–56 % du carré
  d'erreur) sont du bruit ; les exclure devrait aider.
- Mesure : entraînement filtré 60–7200 s → **570,1 s** contre **557,1 s** sans filtre
  (`causal-r4-filtered` vs `causal-r2`) : le filtre coûte 13 s (+2,3 %) et rend le modèle aveugle
  sur la queue qui domine la RMSE.
- Décision : `train_filter = false`. La RMSE vise la moyenne conditionnelle ; supprimer la queue
  de l'apprentissage déplace la prédiction vers la médiane, ce qui est pénalisé.
- Devient faux si : l'organisateur retire ces lignes du calcul de RMSE (rien ne le dit).

## D‑012 — Le proxy sert de variable et de base, pas de concurrent linéaire (adoptée après mesure)

| recette | RMSE dev globale | hors cibles aberrantes |
| --- | ---: | ---: |
| causale (`causal-r2`) | 557,1 | 382,8 |
| reconstitution analytique + écrêtage (`hybrid-r2`) | 566,6 | 373,9 |
| empilement linéaire pondéré par aéroport | 538,3 | — |
| proxy comme **variable** dans LightGBM (`hybrid-model-r1`) | **490,8** | **283,0** |

L'écrêtage analytique nuit (il écrase la queue) ; l'empilement linéaire n'apporte que 19 s parce
que les deux pistes se trompent sur les mêmes lignes. D'où `D‑013`.

## D‑013 — Formulation en résidu du proxy, sans écrêtage (2026‑10‑09, **hypothèse réduite par la mesure**)

Idée de départ : le proxy porte les mêmes aberrations que la cible, donc prédire
`cible − (proxy + biais aéroport)` éviterait d'extrapoler sur les lignes extrêmes.

Mesure sur le dev (`hybrid-model-r1`, 768 lignes aberrantes = cible > 7200 s ou ≤ 60 s) :

| population | n | proxy présent | RMSE du proxy brut | RMSE du modèle |
| --- | ---: | ---: | ---: | ---: |
| LIRF aberrantes | 197 | **13 %** | 6 564 | 22 017 |
| toutes aberrantes | 768 | **37 %** | 3 312 | 11 859 |
| LIRF normales | 51 730 | 99 % | 584,5 | 603,2 |
| toutes normales | 670 524 | 99 % | 400,0 | **283,0** |

Deux conclusions, dont une qui contredit l'hypothèse :

1. **Là où le proxy existe**, l'ancrage en résidu est le bon choix : sur les lignes aberrantes
   avec proxy, le proxy brut fait 3 312 s là où le modèle en valeur absolue échoue à 11 859 s —
   les feuilles de LightGBM ne peuvent pas extrapoler au‑delà de leurs moyennes.
2. **Mais** sur 63 % des lignes aberrantes le proxy est *absent* (et 87 % à Rome) : la formulation
   en résidu ne peut donc pas les sauver, elles retombent sur le repli. Le gain attendu sur la RMSE
   globale est réel mais borné, pas spectaculaire.

À noter aussi : à Rome, sur les lignes *normales*, le modèle (603 s) n'apporte presque rien par
rapport au proxy brut (584 s) — l'aéroport est intrinsèquement très variable.

## D‑014 — LIRF est le levier dominant, traité comme tel (adoptée après mesure)

Rome représente **7,7 % des lignes mais 70,7 % du carré d'erreur total** en dev
(RMSE 1 484 s contre 187–454 s ailleurs). Toute amélioration globale passera par Rome : modèle ou
régularisation spécifique, et non par un réglage global supplémentaire (les deux variantes
globales testées, `causal-r4` et `causal-r5`, ont toutes deux **dégradé** le score).

## D‑015 — Cible en log pour la queue inaccessible au proxy (2026‑10‑10, **refermée par la mesure**)

Sur les lignes aberrantes sans proxy, aucune piste ne peut lire la valeur réelle ; la seule
question est de savoir si des variables causales (retard planifié, créneau, saison) annoncent un
roulage démesuré. Une cible transformée en `log1p` permet au modèle de sortir des valeurs extrêmes
sans que les feuilles restent bloquées sous la moyenne, ce que la formulation linéaire interdit.

**Mesure (D‑028).** L'hypothèse a été testée là où son mécanisme devait nécessairement apparaître : sur la
poche sans fiche réseau, avec un modèle qui lui est consacré. `log1p` + L2 donne 473,1 s contre 449,8 s en
janvier (+5,2 %). La cause n'est pas l'idée mais la perte de cohérence avec la métrique : L2 sur `log1p`
estime une moyenne géométrique et `expm1` la réinjecte trop basse sur une cible à queue épaisse (biais de
retransformation). Corrigée en Tweedie — qui prédit en secondes sans transformation, tout en acceptant une
variance croissante avec la moyenne — la variante redevient neutre (481,6 s, +0,4 %), donc toujours sans
gain.

Une variante globale (toutes lignes, cible en log) n'a **pas** été lancée, et ce choix est assumé : la
métrique officielle est une RMSE, c'est‑à‑dire une moyenne arithmétique des carrés en secondes ; optimiser
une moyenne géométrique sur l'ensemble des lignes serait mal aligné avec le score même si la queue s'en
trouvait mieux dessinée. Le test ciblé suffisait à trancher le mécanisme. **Verdict : rejetée.**


## D‑016 — Pression réseau à la destination : variable mesurée puis désactivée (2026‑10‑09, rejetée)

Idée : un vol dont l'aéroport d'arrivée est saturé est retenu au sol ; on ajoute donc le nombre
d'arrivées et de départs *planifiés* à la destination sur le même créneau (`dest_arr_sched`,
`dest_dep_sched`) — variable causale, disponible dans les entrées de finale.

| recette | sans la variable | avec | écart |
| --- | ---: | ---: | ---: |
| résiduelle (`residual-r1` → `residual-r2-dest`) | 479,9 | 494,9 | **+3,1 %** |
| causale (`causal-r2` → `causal-r7-dest`) | 557,1 | 556,7 | −0,1 % (non concluant) |

Décision : variable conservée dans le code mais **désactivée par défaut**
(`features.dest_pressure = false`, portée par `FeatureSpec` et sérialisée avec le modèle), car elle
est au mieux neutre et clairement nuisible dès qu'un proxy sert de base.

Leçon de méthode, consignée parce qu'elle a faussé une mesure : la première exécution causale
(`causal-r6-dest`, 569,1) comparait en réalité *filtre activé* contre *filtre désactivé* — la
configuration de base avait gardé `train_filter = true` alors que D‑011 l'avait rejeté. Le score
reproduisait à 1 s près `causal-r4-filtered` (570,1), ce qui a révélé la confusion. Depuis :
`configs/tabular_causal.toml` porte `train_filter = false`, et toute comparaison entre recettes
vérifie d'abord que les configurations ne diffèrent que du facteur testé.

## D‑017 — Nombre d'itérations du gel pris de la médiane des plis de développement (adoptée)

Sans jeu de validation au moment du gel, `train_final` ne peut pas faire d'early stopping : il
prend la médiane des `best_iteration` des quatre plis (`--from-report`), valeur consignée dans
`meta.json` avec sa source. Mesure en cours (`residual-r3-long`) : à 4000 itérations,
l'early stopping n'avait jamais déclenché — si un volume plus long améliore le développement, la
médiane des plis suivra automatiquement.

## D‑018 — Le plantage silencieux de deux exécutions était un défaut de code, pas une limite machine (2026‑10‑09, résolu)

Symptôme : deux entraînements tués par `SIGKILL` (code 137) sans trace d'erreur, apparemment par
manque de mémoire — alors que la machine dispose de 512 Go et d'environ 300 Go libres.

Mesure : `/usr/bin/time -l` sur l'exécution fautive donne un pic de **343 Go** de mémoire
résidente, contre 4,1 Go après correction. La cause est une diffusion involontaire :
`pd.util.hash_array()` appliqué à un tableau de forme `(N, 1)` renvoie `(N, 1)`, si bien que la
comparaison suivante fabriquait une matrice booléenne `N × N` (≈ 24 milliards de cases).

Corrections apportées :
- `id_bucket()` remplace le hachage (modulo déterministe sur l'identifiant), refuse toute entrée
  non unidimensionnelle ou non finie, et un contrôle d'assertion vérifie la forme des masques ;
- trois tests de non‑régression (`tests/test_residual_gate.py`), dont celui qui reproduisait
  exactement la diffusion en matrice ;
- la mémoire résidente est désormais mesurée par `/usr/bin/time -l` lors des exécutions longues,
  au lieu de se fier uniquement à l'auto‑mesure du rapport.

Leçon consignée : un `SIGKILL` sans trace ne doit pas être attribué à la machine avant d'avoir
mesuré l'empreinte mémoire réelle du processus.

## D‑019 — Post‑traitement de sortie : plancher à zéro, aucun plafond (2026‑10‑09, adoptée après mesure)

Mesure sur les prédictions de développement (RMSE de référence entre parenthèses) :

| post‑traitement | `causal-r2` (557,1) | `residual-r1` (479,9) |
| --- | ---: | ---: |
| aucun | 557,1 | 479,9 |
| plancher à 0 s | 557,1 (±0,00 %) | **479,4 (−0,10 %)** |
| plancher à 60 s / 120 s | 557,1 (±0,00 %) | 479,4 (−0,11 %) |
| plafond à 20 000 s | 557,1 | 486,8 (+1,44 %) |
| plafond à 7 200 s | 558,9 (+0,31 %) | 491,9 (**+2,49 %**) |

Décision : `max(prédiction, 0)` uniquement. Le plancher est gratuit en RMSE et élimine les valeurs
négatives que produisaient les deux pistes (23 lignes en causal, 71 en reconstitution sur le
gabarit 2026). Tout plafond est proscrit : il écrase précisément les valeurs extrêmes qui pèsent
le plus dans la RMSE — troisième confirmation du même effet (après D‑011 et D‑013).

## D‑020 — Correction d'un relevé erroné : le gabarit est en float64, pas en int32 (2026‑10‑09)

Le dictionnaire des données notait `TAXITIME_SEC_mvt` en `int32` pour le gabarit de finale. C'est
exact pour les fichiers d'**entraînement**, faux pour le **gabarit** : les deux colonnes du gabarit
sont en `float64` (avec `NaN` à remplir). Vérifié sur le fichier, et le contrôle de soumission
l'avait signalé comme avertissement sur les premières générations.

Correction : `src/predict.py` ne durcit plus de type, il reprend `template["TAXITIME_SEC_mvt"].dtype`.
Les deux fichiers produits passent désormais sans erreur **ni avertissement**. Le plancher à zéro a
été appliqué après coup, d'où une nouvelle empreinte SHA‑256 pour les deux soumissions.

## D‑021 — Ajout de deux mois témoins à la rotation (2026‑10‑09, adoptée)

Demande du responsable de projet : élargir la rotation plutôt que de déplacer la réserve.

- `configs/splits.toml` reçoit `witness_months = ["2025-03","2025-10"]` ; `Protocol.witness_folds()`
  et les options `--witness` / `--split witness` les entraînent dans les mêmes conditions que les
  plis normaux (mêmes mois d'entraînement, même repli, aucun réglage commun).
- **Règle de discipline** : ces mois ne départagent jamais deux recettes. Le critère de choix reste
  la rotation sur janvier/février/juin/juillet ; les témoins élargissent seulement l'estimation et
  montrent qu'une victoire n'est pas un hasard de saison. La réserve (novembre + décembre) reste
  fermée et conserve son rôle de chiffre unique non contaminé.
- Mesure : causale 355,0 s et reconstitution 278,7 s sur mars + octobre — mois plus faciles que les
  mois cibles, ce qui explique pourquoi l'estimation poolée baisse dès qu'on les ajoute (497,2 s et
  421,9 s sur six mois contre 557,1 s et 479,9 s sur quatre). Les deux chiffres sont utiles, mais
  pour le classement de la finale **ce sont les quatre mois cibles qui représentent la tâche**.

## D‑022 — Un fichier de référence sans apprentissage comme ancre de comparaison (2026‑10‑09, adoptée)

Besoin : relier nos mesures locales (2025) au score officiel (janvier + juillet **2026**), sans
transformer le dépôt en instrument de mesure du classement.

- Fichier fourni : `proxy brut + biais par aéroport`, méthode simple et transparente, **sans aucun
  apprentissage** (`configs/tabular_hybrid_noclip.toml`, repli moyenne aéroport‑heure). RMSE locale
  connue : **591,7 s** sur les quatre mois cibles (643,6 s sur janvier + juillet ; 379,0 s hors
  lignes aberrantes).
- Usage : le score officiel de ce fichier donne un **facteur de transfert** entre nos mesures locales
  et la réalité du classement, applicable aux deux autres fichiers. Un point, documenté à l'avance.
- Garde‑fous : aucun dépôt « pour voir », aucune itération guidée par le classement (règle officielle
  sur l'exploitation du processus de classement) ; les cinq dépôts quotidiens ne sont pas consommés en
  explorations.
- **Clean‑room** : les scores d'une session antérieure sur ce même challenge (le responsable de projet
  mentionne ~521 s en causal et ~385 s en proxy résiduel sur janvier + juillet) n'ont été **ni lus, ni
  recoverés, ni utilisés** par ce dépôt. Ils ne servent à aucune décision de modélisation ni de réglage.
  La comparaison est d'ailleurs délicate : un score officiel et une RMSE locale ne sont comparables que
  si la population, les mois et les lignes incluses sont identiques — nos chiffres locaux sur janvier +
  juillet 2025 sont 603,5 s (causal) et 519,9 s (résiduel), ce qui laisse penser que les chiffres dont
  il se souvient correspondaient à une autre population (ou à un périmètre hors lignes aberrantes).
  C'est exactement l'ambiguïté que le fichier de référence permet de lever.

## D‑023 — Ouverture unique de la réserve interne (2026‑10‑10 06:17 +0200, exécutée)

Les recettes étaient gelées depuis le 9 octobre (modèles entraînés sur janvier → octobre uniquement,
itérations fixées par la médiane des plis de développement, D‑017). Les trois recettes intéressées
ont été évaluées **dans une seule commande**, parce que le marqueur `reports/RESERVE_OPENED.json`
interdit toute ouverture ultérieure — sinon la première évaluation aurait consommé la réserve pour
une seule recette.

Novembre + décembre 2025, **328 009 départs, aucune ligne exclue** :

| recette | RMSE réserve | hors lignes aberrantes | biais |
| --- | ---: | ---: | ---: |
| prédiction constante (moyenne d'entraînement, 990,3 s) | 523,4 | 413,1 | — |
| fichier de référence (proxy + biais, sans apprentissage) | 470,0 | 344,3 | +3,4 |
| **prédiction** (causale gelée) | 432,8 | 342,5 | +8,3 |
| **reconstitution** (proxy + correction, gelée) | **353,9** | 237,3 | −13,1 |

Ce que ça confirme : l'avantage de la reconstitution se retrouve sur des données jamais touchées
(−18,2 % vs causal ici, −13,9 % en développement, −21,5 % sur les mois témoins). Ce n'est pas un
artefact du choix des recettes.

Ce que ça ne dit pas : le niveau attendu sur la finale. Novembre et décembre sont des mois **plus
faciles** que janvier/février/juin/juillet (432,8 s contre 557,1 s pour le même modèle causal) ; les
mois visés par le classement restent les plus durs de notre échantillon.

**Discipline après ouverture** : aucun réglage, aucune nouvelle variable, aucun changement de recette
ne sera décidé à partir de ces chiffres — ils ne servent qu'à estimer. Si une amélioration était
tentée ensuite, la réserve perdrait sa valeur et il faudrait la considérer comme du développement.
Le dépôt reste donc exactement dans l'état gelé, à l'exception du renommage des fichiers.

## D‑024 — Audit des deux sources d'off‑block, sans filtrage ni sous‑pondération (2026‑10‑10, adoptée)

Proposition du responsable de projet : utiliser les champs réalisés `_flt` comme **outil d'audit** de
l'apprentissage, jamais comme entrée du prédicteur avant départ ; comparer trois entraînements
(toutes lignes / exclusion des cas suspects / sous‑pondération) ; évaluer chaque modèle sur le même
mois tenu hors, cible officielle intacte ; rapporter séparément concordants, discordants et sans
information réseau. Détail complet et tableaux : `reports/AUDIT_SOURCES.md`, outil `src/audit.py`.

Ce que l'audit établit (mois cibles 2025, 671 292 lignes) :

* les roulages au‑delà de deux heures ne sont **pas corroborés** : sur 259 lignes, **une seule** est
  concordante entre les deux sources, 20,1 % sont en désaccord fort, **79,5 % n'ont aucun enregistrement
  réseau** — et ce résultat ne bouge pas quand on fait varier les seuils de 600/1200 s à 1800/3600 s ;
* le temps au sol total de ces vols (décollage − horaire planifié) est bien de 2,5 h ou plus : la
  valeur énorme n'est pas une horloge folle, c'est une **attribution** disputée entre attente avant
  pushback et roulage après pushback (écart médian +2 215 s, le réseau plaçant le pushback ~37 min plus
  tard) ;
* la poche d'erreur dominante est précisément celle qui ne peut pas être auditée : 1,34 % des lignes
  sans information réseau portent **54,9 %** du carré d'erreur en causal et **73,9 %** en résiduel ;
* la classe « désaccord fort » — seule sur laquelle un filtrage ou une sous‑pondération pourrait agir —
  ne pèse que 0,61 % des lignes et 9,8 % / 6,2 % du carré d'erreur.

Décision : **aucun filtrage, aucune sous‑pondération fondée sur l'accord des sources**, et les trois
entraînements comparés ne sont pas lancés — la raison est chiffrée ci‑dessus (levier borné à la plus
petite des deux poches d'erreur), pas idéologique. Deux motifs supplémentaires, de méthode :

1. un filtrage sur l'accord des sources rendrait l'apprentissage **moins représentatif** de la population
   réellement classée, qui contient ces lignes ;
2. la cible du concours reste celle des mouvements : écarter les étiquettes qui nous semblent douteuses,
   c'est optimiser un autre problème que celui qui est noté (même effet mesuré qu'en D‑011 : +2,3 %).

En revanche l'audit **confirme et précise** deux choix déjà pris : ne rien écrêter en haut (D‑013, D‑019),
et considérer que la supériorité de la piste de reconstitution porte sur les lignes auditablement
concordantes — où elle descend à 193,4 s contre 306,2 s en causal — et non sur les lignes extrêmes, où
elle retombe sur le repli causal (RMSE identique par construction).

## D‑025 — Règle d'adoption pré‑enregistrée pour les essais ciblés sur la poche sans information réseau (2026‑10‑10, écrite AVANT toute exécution ; **exécutée → résultats en D‑028**)

Contexte : l'audit (D‑024) montre que 1,34 % des départs n'ont **aucune** information réseau — les
onze colonnes `_flt` y sont absentes à 100 %, y compris dans les entrées de finale (1,35 % des lignes).
Cette poche porte 54,9 % du carré d'erreur en causal et 73,9 % en résiduel. Deux essais sont donc
justifiés :

1. **indicateur de régime** (`regime_sans_reseau`) dans la piste causale, pour que les arbres spécialisent
   leurs feuilles au lieu de noyer ce régime sous des `NaN` ;
2. **modèle spécialisé** sur les seules lignes sans information réseau (19 465 lignes d'apprentissage),
   avec cible transformée en `log1p` pour que les feuilles puissent atteindre des valeurs extrêmes,
   utilisé comme repli à la place du modèle causal générique dans la piste résiduelle.

**Critère d'adoption, fixé avant de regarder le moindre résultat :** la variante n'est adoptée que si sa
RMSE est **inférieure d'au moins 2 % sur chacun des quatre mois cibles** (janvier, février, juin, juillet),
calculée sur **100 % des lignes**, cible officielle intacte. Sinon elle est refusée et les fichiers gelés
restrent ceux fournis. Aucun critère secondaire (erreur par catégorie, esthétique du modèle) ne peut
sauver une variante qui échoue à ce test.

Pourquoi un seuil aussi franc : avec 74 % du carré d'erreur concentré dans 1,34 % des lignes, la RMSE
d'un mois est très sensible à quelques dizaines de vols. Un écart de quelques dixièmes de pour cent
n'est pas un signal — c'est du bruit d'échantillonnage, et notre seuil habituel de 0,5 % était trop laxiste
pour cette métrique‑là (correction de portée assumée, voir D‑026).

**Ce qui reste vrai après adoption éventuelle** : la réserve interne est consommée (D‑023), donc toute
recette modifiée ici est jugée sur développement uniquement. Si une variante était retenue, `DECISIONS.md`
devrait le dire explicitement, avec l'horodatage du regel et l'empreinte des nouveaux fichiers.

## D‑026 — Correction de portée : notre seuil de comparaison était trop serré pour cette métrique (2026‑10‑10)

Les premiers arbitrages traitaient un écart inférieur à 0,5 % comme non concluant. C'était raisonnable
en moyenne, mais trop faible comme garde‑fou étant donné la concentration mesurée en D‑024 : la RMSE d'un
mois tenu hors est dominée par une poignée de lignes dont l'étiquette est mono‑source. Les décisions déjà
prises n'en sont pas ébranlées — les écarts refusés étaient dans le sens « ne rien changer » (conservateur),
et ceux adoptés (D‑012 −11,9 %, D‑013 −2,2 %) dépassent le nouveau seuil — mais la règle devient 2 % par
mois sur tous les mois cibles pour toute adoption future.

## D‑027 — Ordre d'exposition distinct de l'ordre de découverte (2026‑10‑10)

L'audit des sources aurait dû précéder la modélisation ; il est venu après, et deux expériences ont été
menées pour rien (D‑011 filtrage, D‑016 pression à destination). Choix assumé : **le journal des décisions
garde l'ordre chronologique réel** (c'est la trace honnête, avec ses mesures ratées), tandis que le `README.md`
suit l'ordre pédagogique — le diagnostic des données avant les choix de modèle. Un lecteur doit pouvoir
voir dans quel ordre réel les choses ont été apprises : cette note est là pour ça.

## D‑028 — Les trois attaques de la poche sans information réseau sont mesurées et refusées (2026‑10‑10, exécutée)

Les essais prévus en D‑025 ont été menés, plus deux variantes ajoutées en cours de route parce que la
première a échoué pour une raison comprise. Le critère est resté celui écrit avant exécution : **−2 % sur
chacun des quatre mois cibles**, sur 100 % des lignes (`scripts/check_adoption.py`, qui applique la règle
mécaniquement et refuse de conclure si les populations diffèrent).

| variante | janvier | février | juin | juillet | global | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| référence (gelée) | 449,8 | 459,6 | 412,3 | 570,2 | **479,9** | — |
| indicateur de régime, piste causale (`causal-r8-regime`) | +0,34 % | +0,19 % | +0,07 % | −0,02 % | 557,8 (vs 557,1) | refusé 0/4 |
| spécialiste `log1p` (`residual-r5-spec`) | **+5,18 %** | — | — | — | abandonné au pli 1 | refusé |
| spécialiste brut, L2 sur secondes (`residual-r5-spec-raw`) | +5,46 % | +1,44 % | +4,07 % | +3,86 % | 497,9 (+3,8 %) | refusé 0/4 |
| spécialiste Tweedie 1,3 (`residual-r6-spec-tweedie`) | +0,14 % | −0,06 % | +1,18 % | +0,26 % | 481,6 (+0,36 %) | refusé 0/4 |

Trois enseignements, dans l'ordre où ils ont été compris :

1. **L'indicateur de régime n'apprenait rien de neuf.** La piste causale contenait déjà `miss_EOBT_1_flt`,
   `miss_IOBT_flt`, `miss_LOBT_flt` — créés pour un tout autre besoin. Les arbres savaient donc déjà séparer
   le regime ; le drapeau joint est redondant (écart ≤ 0,34 % partout).
2. **Le premier échec du spécialiste était un défaut statistique, pas l'idée.** `log1p` + L2 estime une
   moyenne géométrique, et `expm1` la réinjecte trop basse sur une cible à queue épaisse : c'est le biais de
   retransformation. Le Tweedie — qui prédit directement en secondes — efface presque tout le handicap
   (+3,8 % → +0,36 %). La correction était donc la bonne ; l'idée restante ne rapporte toujours rien.
3. **La spécialisation nuit, et deux mesures indépendantes le disent.** Recycler le repli vers la moyenne
   aéroport ne gagne rien (λ = 1 est optimal : pool 3 566,7 s contre 3 566,5 s à λ = 0,85, puis ça se
   dégrade) — donc le modèle générique n'est pas sur‑ajusté sur cette poche. Et dans cette poche, **le 1 %
   de lignes le pire porte 81 à 93 % du carré d'erreur**, avec des cibles jusqu'à 131 167 s : un modèle
   formé sur ~20 000 lignes de ce régime perd davantage en généralité qu'il ne gagne en connaissance du
   régime.

**Ce que l'audit a donc réellement rapporté** : pas un point de RMSE, mais une **borne basse mesurée**. Sur
les lignes sans fiche réseau, notre repli fait 4 026 / 4 411 / 2 908 / 3 502 s par mois ; la moyenne par
aéroport y ferait 4 106 / 4 465 / 2 959 / 3 579 s et la moyenne globale 4 282 / 4 744 / 3 252 / 3 834 s.
Nous sommes déjà proches du plancher atteignable sans savoir *lequel* de ces vols restera bloqué
vingt‑quatre heures — information que **aucune** colonne fournie ne contient, pas même pour le réseau.

**Fichiers gelés inchangés.** Aucun des trois runs n'a été adopté ; les trois soumissions de la section 10
restrent bit à bit celles fournies (empreintes vérifiées après ces essais). Réserve toujours fermée : ces
variantes ont été jugées sur développement, comme l'exige D‑023.

## D‑029 — Règle d'adoption combinée pour les essais qui suivent (2026‑10‑10, écrite avant les résultats de D‑031)

Le seuil de D‑026 (−2 % sur chacun des quatre mois cibles) protège bien du bruit, mais il mesure le bruit
*brut* et non la *constance* d'un gain. Une amélioration répartie sur toute la masse ordinaire peut légitimement
rapporter −1 % sur les quatre mois : ce n'est pas du hasard si les quatre mois bougent dans le même sens, et
D‑026 rejetterait un vrai progrès.

**Nouvelle règle, applicable aux essais engagés après cette entrée** :

1. la RMSE de la variante est **inférieure d'au moins 1 % sur chacun des quatre mois cibles** — pas trois sur
   quatre, pas la moyenne ;
2. un **bootstrap apparié** sur les lignes (2 000 tirages, ré‑échantillonnage par mois des différences de
   carrés d'erreur entre référence et variante) donne un intervalle à 95 % sur le rapport de RMSE dont la
   borne haute est **strictement inférieure à 1** ;
3. les deux conditions simultanées, calculées par `scripts/check_adoption.py --bootstrap`, sans exception de
   confort : une variante qui échoue à l'une des deux est refusée, même si son mécanisme paraît élégant.

Pourquoi c'est plus solide et pas seulement plus souple : D‑026 exigeait un effet fort parce qu'il n'avait
aucune mesure de la significité ; ici la significité est calculée sur les mêmes lignes, ce qui retire
l'essentiel du bruit d'échantillonnage qui motivait le seuil de 2 %. Le nombre d'essais tentés reste consigné
en entier dans `experiments/REGISTRY.md` — avec neuf variantes déjà engagées sur la seule poche sans réseau,
c'est la seule défense utile contre l'auto‑suggestion.

## D‑030 — Projection du score officiel sans étiquette : utile en relatif, **invalide en niveau** (2026‑10‑10, mesurée)

**Question posée** : peut‑on estimer notre RMSE officielle sur janvier + juillet 2026 *avant* de déposer,
sans toucher au classement ? Oui en partie. Dans les entrées officielles, `MVT_TIME_UTC_mvt` et
`AOBT_3_flt` sont présentes : le proxy est donc calculable alors que la cible est masquée. On mesure la
distribution de la difficulté de la population 2026 (tranches de proxy × Rome/autre, plus la poche sans
fiche réseau) et on y rejoue notre profil d'erreur conditionnelle, mesuré sur les mois tenus hors.
Aucune étiquette 2026 n'existe ni n'est utilisée ; aucun score n'est demandé au classement.
Outil : `src/score_projection.py` → `reports/SCORE_PROJECTION.{md,json}` (11 s de calcul).

**Garde‑fou écrit avant l'exécution** : rétro‑validation — rejouer la procédure sur un mois de développement
en faisant semblant de l'ignorer. Le niveau n'est déclarable que si l'écart au vrai reste ≤ 5 %.

| mois tenu hors | projeté | réel | écart |
| --- | ---: | ---: | ---: |
| 2025‑01 | 360,4 | 449,8 | −19,9 % |
| 2025‑02 | 360,6 | 459,6 | −21,5 % |
| 2025‑06 | 510,5 | 412,3 | +23,8 % |
| 2025‑07 | 641,4 | 570,2 | +12,5 % |

**Le garde‑fou tombe : écart maximal 23,8 %, dispersion résiduelle σ = 0,233 en log, soit un facteur
d'incertitude de ×1,58 sur le niveau.** Ce n'est pas un défaut de découpage : passer de 7 à 11 tranches dans
la queue ne change presque rien (23,8 % → 22,7 %). Ce qui varie d'un mois à l'autre n'est pas la *fréquence*
des vols démesurés mais leur *ampleur*, et elle n'est inscrite dans aucune colonne — c'est le même mur que
D‑024, retrouvé depuis l'autre côté.

**Usage déclaré exploitable** : comparer des mois entre eux, et mesurer une dérive de population. Interdit :
annoncer un niveau absolu.

| population | sans fiche réseau | proxy > 1 h | Rome | p99 du proxy | RMSE projetée (intervalle complet) |
| --- | ---: | ---: | ---: | ---: | ---: |
| janvier 2026 | **1,61 %** | 0,369 % | 7,24 % | 2 637 s | 450,9 [285,6 ; 712,0] |
| février 2026 | 0,92 % | 0,078 % | 7,12 % | 2 103 s | 395,7 [250,6 ; 624,8] |
| juin 2026 | 1,36 % | 0,164 % | 8,24 % | 2 099 s | 470,0 [297,6 ; 742,1] |
| juillet 2026 | 1,48 % | 0,177 % | 8,24 % | 2 049 s | 564,8 [357,7 ; 891,9] |
| **janv. + juil.** | — | — | — | — | **517,5 [327,7 ; 817,2]** |

Lecture honnête de la cible de 385 s : la projection centrale demanderait **−25,6 %** de RMSE, mais la borne
basse de l'intervalle (327,7 s) est **déjà sous la barre**. Autrement dit, 385 n'est pas hors de portée par
hasard de population — c'est exactement le genre de question qu'un seul relevé du classement tranche.

**Conséquence opérationnelle, et c'est l'apport principal de cette décision** : le fichier de référence
(proxy + biais, sans apprentissage, RMSE locale connue d'avance : 591,7 s sur les quatre mois cibles,
643,6 s sur janvier + juillet) devient l'**instrument de mesure** qui convertit cet intervalle ×1,58 en un
facteur de transfert observé. Coût : une place de dépôt sur les cinq quotidiennes (D‑009). Il doit donc être
déposé **en premier**, avant toute autre soumission.

## D‑031 — Calibration de la base `proxy → cible` par aéroport (2026‑10‑10, **refusée après mesure**)

**Constat mesuré d'abord.** Le proxy est une *mesure bruitée* du off‑block : régresser la cible dessus donne
une pente globale de **0,691**, pas 1. La base utilisée depuis `residual-r1` (`proxy + constante par
aéroport`) laisse donc une erreur systématique qui croît avec l'écart — exactement la queue en désaccord où
notre biais mesuré est de −927 s (D‑024). Sur les seules lignes avec proxy, quatre mois tenus hors :

| base | RMSE poolée | janvier, lignes > 1 h |
| --- | ---: | ---: |
| `proxy + constante` (recette gelée) | 385,4 s | 1 949 s |
| droite par aéroport (`a + b·proxy`) | 367,2 (−4,7 %) | 1 392 s |
| isotonique par aéroport | **361,4 (−6,2 %)** | — |

**Ce qui est implémenté** : `fit_calibration` / `apply_calibration` dans `src/reconstruct.py`, mode choisi par
`[reconstruct] calibration` = `constante` (défaut, recettes gelées inchangées au bit près) | `lineaire` |
`isotonique`. Repli hiérarchique explicite : aéroport (si ≥ 5 000 lignes d'apprentissage) → droite globale →
filet isotonique global. La calibration est apprise **uniquement sur les mois d'entraînement du pli**, et
voyage dans `state.json` (les états antérieurs, dépourvus de la clé, restent en mode constante).

**Critère d'adoption, écrit avant exécution** : D‑029 — RMSE inférieure d'au moins 1 % sur **chacun** des
quatre mois cibles, et intervalle bootstrap apparié excluant 0.

**Mesure (quatre plis, règle D‑029)** :

| variante | janvier | février | juin | juillet | global | bootstrap apparié | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `residual-r1` (gelée, constante) | 449,8 | 459,6 | 412,3 | 570,2 | **479,9** | — | référence |
| droite par aéroport (`residual-r8-calib-lin`) | +0,10 % | +0,39 % | −0,12 % | −0,02 % | 480,2 (+0,06 %) | IC95 [0,9999 ; 1,0016] | refusée (neutre) |
| isotonique par aéroport (`residual-r7-calib-iso`) | +0,07 % | +0,46 % | +0,00 % | **+5,10 %** | 490,4 (+2,18 %) | IC95 [0,9997 ; 1,0749] | refusée (nuisible) |

**Pourquoi le −6,2 % mesuré sur la base seule ne se reporte pas** : le modèle voit déjà `proxy_sec` comme
variable. La pente d'atténuation que la constante ignorait, il l'apprenait lui‑même ; calibrer la base
déplace le travail de la base vers le modèle sans rien ajouter au total — la droite le montre exactement
(+0,06 %, intervalle collé à 1). L'isotonique ajoute un dommage qui lui est propre : apprise sur le cœur
(60–7200 s), elle s'aplatit au‑delà de son domaine et **écrête de fait les valeurs extrêmes** que l'on voulait
atteindre — d'où juillet à +5,1 %, le mois où Rome pèse le plus, donc le plus riche en queue.

**Ce que cette décision ferme** : la sous‑estimation systématique des lignes en désaccord (−927 s, D‑024)
n'est **pas** un artefact de calibration de la base. Elle subsiste quand on corrige cette calibration par la
pleine droite. Elle relève de l'attribution de l'attente avant pushback — pas d'un réglage que nous puissions
faire. Le code reste disponible (`[reconstruct] calibration`, défaut `constante`) pour reproduction, couvert
par `tests/test_calibration_base.py` ; **les recettes gelées sont inchangées** et les trois fichiers fournis
aussi (empreintes revérifiées après ces essais).

## D‑032 — Amorçages multiples : non lancés, et pourquoi (2026‑10‑10)

Le moyennage de cinq amorçages réduit typiquement la RMSE de quelques dixièmes de pour cent. Sous la règle
D‑029 (−1 % sur **chacun** des quatre mois), un gain de cette taille n'est pas adoptable, et le justifier par
la seule stabilité serait un changement de critère après coup. Nous le consignons comme option non exécutée
plutôt que de le faire passer pour un résultat. Si le dépôt du fichier de référence (D‑030) montre que la
population 2026 est proche de nos mois de développement, le calcul redevient intéressant : il aurait alors une
cible chiffrée à atteindre plutôt qu'un vague confort.

## D‑033 — Spécialisation sur la queue : plafonds calculés avant exécution, **variante lancée et refusée** (2026‑10‑10)

L'idée à tester (proposée par l'équipe) : un modèle **spécialisé** sur les lignes difficiles de la
reconstitution, là où le proxy est présent mais mauvais. Avant de lancer le moindre entraînement, nous avons
mesuré **ce qu'une spécialisation pourrait gagner au mieux**, avec le modèle gelé `residual-r1` et ses
prédictions conservées (aucun réentraînement pour ce diagnostic).

Deux candidatures sont **tuées par l'arithmétique**, pas par un échec :

| région | définition | part des lignes | RMSE du modèle | part du carré d'erreur | plafond si on divisait la RMSE par deux |
| --- | --- | ---: | ---: | ---: | ---: |
| amplitude du proxy | `proxy ≥ 1 800 s` | 2,97 % | 506 s | **3,4 %** | −0,84 % → sous le critère D‑029 |
| désaccord fort | `\|AOBT_3 − LOBT\| ≥ 60 min` | 0,28 % | 1 113 s | 1,5 % | −0,38 %, et seulement **3 993 lignes** d'apprentissage |
| sans fiche réseau | aucune colonne `_flt` | 1,34 % | 3 567 s | 73,9 % | déjà attaqué trois fois, refusé (D‑028) |

Autrement dit : « spécialiser sur les gros roulages » n'a pas de prise — quand le proxy est énorme, le modèle
est déjà bon (499 s entre 30 et 60 min de proxy). L'erreur n'habite pas là.

**La seule candidature au plafond assez haut** est la région `|AOBT_3 − LOBT| ≥ 30 minutes` : 5,1 % des lignes,
6,3 % du carré d'erreur, **80 991 lignes d'apprentissage**, et un désaccord calculable en exploitation (les
deux colonnes sont présentes dans les entrées de finale). Diviser sa RMSE par deux vaudrait −3,1 % global ;
un spécialiste réaliste vise 10 à 20 %, soit **−0,6 à −1,2 %**.

**Ce qui est lancé** : `residual-r9-tail-desac` — second modèle entraîné sur les seules lignes en désaccord
d'au moins 30 min, cible identique au modèle principal (l'écart à la base), appliqué uniquement à ces lignes.
Base, fonctionnalités et tout le reste inchangés ; derrière `--tail`, défaut désactivé, donc **marche arrière
à zéro coût** : les recettes gelées et les trois fichiers fournis ne sont pas touchés.

**Critère d'adoption** : D‑029, sans assouplissement (−1 % sur chacun des quatre mois cibles **et** bootstrap
apparié excluant 1).

**Résultat (quatre plis, règle D‑029)** : refusé. Global 480,4 s contre 479,9 s (+0,10 %), rapport bootstrap
[1,0006 ; 1,0017]. Et surtout, le diagnostic qui clôt la question :

| région | n | référence | avec spécialiste | écart |
| --- | ---: | ---: | ---: | ---: |
| désaccord ≥ 30 min (la cible du spécialiste) | 34 553 | 533,0 s | **541,7 s** | **+1,63 %** |
| désaccord < 30 min (intouchées) | 627 755 | 220,4 s | 220,4 s | 0,00 % |

Le spécialiste a donc bien modifié uniquement les lignes visées — et il y a **perdu**. Le mode d'échec annoncé
s'est réalisé tel quel : dans cette région le modèle de référence est déjà sans biais (−25 s), son erreur est
de la variance ; entraîner sur 81 000 lignes au lieu de 1 750 000 dégrade plus la généralisation qu'elle
n'apporte de connaissance du régime. C'est le troisième résultat convergent après D‑028 (poche sans fiche
réseau, +3,8 %) et D‑031 (calibration de base, neutre) : **sur ces données, la spécialisation ne rend rien.**

**Marche arrière effectuée, à zéro coût** : le mécanisme reste derrière `--tail` (défaut désactivé), les
recettes gelées et les trois fichiers fournis sont inchangés au bit près (empreintes revérifiées après essai).

**Décision de méthode qui suit cet essai** : nous arrêtons le réglage. Onze variantes mesurées, zéro adoptée,
et les plafonds calculés en D‑033 montrent qu'il ne reste plus rien à gagner de ce côté sans dépasser notre
propre critère. L'inconnu qui domine désormais — le transfert entre nos mesures locales et le classement — ne
se lève pas par le calcul mais par un dépôt : référence d'abord, puis reconstitution, puis prédiction (D‑030).

## D‑034 — Relecture des règles, étiquettes d'arrivée 2026, et un défaut d'échelle dans notre propre code (2026‑10‑10)

Trois découvertes le même jour, chacune avec sa correction. Elles viennent d'une relecture des pages
officielles demandée par l'équipe, pas d'un réglage.

**1. Le classement ne note que janvier et juillet 2026.** « The applied ranking will use Root Mean Square
Error (RMSE) for submitted predictions for the movements in **January and July 2026** » (page d'accueil).
Le gabarit couvre bien quatre mois et le script refuse toute ligne manquante ou en trop — nous remplissons
donc toujours les 670 790 lignes — mais **le critère de décision principal devient janvier + juillet
combinés**, les quatre mois restant le contrôle de stabilité. `RULES.md` est à jour ; l'outil
`scripts/check_adoption.py` garde les quatre mois comme garde-fou et nos rapports citent désormais les
deux lectures.

**2. Il existe deux paires de fichiers d'évaluation, et elles portent une vérité 2026.** La paire de
septembre (`ranking.parquet`, `submitting.parquet`) couvre janvier + juillet 2026 sur les 8 plateformes de
la phase précédente ; ses identifiants sont un sous-ensemble strict de `final_ranking` (689 534 sur
689 534). Surtout, **les arrivées y sont étiquetées à 100 %** : `final_ranking.parquet` fournit
**670 407 temps de roulage d'arrivée réels** sur nos dix plateformes et les quatre mois. Aucun départ
n'est étiqueté en 2026 — la réserve interne reste donc fermée et aucune règle d'adoption ne change.

Première utilisation, comme contrôle de dérive (mêmes aéroports, mêmes mois, 2025 contre 2026) :

| mois | médiane 2025 | médiane 2026 | écart | part > 10 min 2025 → 2026 |
| --- | ---: | ---: | ---: | ---: |
| janvier | 486 s | 487 s | +0,2 % | 34,3 % → 34,0 % |
| février | 477 s | 484 s | +1,5 % | 31,7 % → 33,4 % |
| juin | 483 s | 479 s | −0,8 % | 33,7 % → 32,6 % |
| juillet | 486 s | 470 s | −3,3 % | 34,8 % → 30,4 % |

La population 2026 est **stable à ±3 %** : l'hypothèse d'une année 2026 beaucoup plus douce (suggérée par
la seule projection du proxy) est **réfutée** sur étiquettes réelles. Par plateforme, l'écart reste modeste
(LTFM −6,1 %, EDDF −3,8 % en baisse ; LEBL +3,5 % en hausse).

**Au passage, une erreur de notre côté, consignée parce qu'elle a produit de faux chiffres dans la
conversation du jour :** une liste d'aéroports erronée (EGKK, LSGG, LOWW, LIME, EKCH, ESSA, ENGM…) a servi
à une analyse ponctuelle ; les vrais dix sont EDDF, EDDM, EGLL, EHAM, LEBL, LEMD, LFPG, LIRF, LTFM, LSZH.
Aucun fichier du projet ne contenait la liste fausse (`RULES.md` et tous les rapports étaient justes) ;
les chiffres d'arrivées cités avant cette décision (3 plateformes) sont donc **annulés et remplacés** par la
table ci-dessus.

**3. Un défaut d'échelle dans `src/prepare.py`.** `epoch()` calculait `astype("int64")/1e9`, ce qui suppose
une résolution nanoseconde ; les colonnes sont analysées en `datetime64[us]`, donc la fonction renvoyait des
**millisecondes**. Conséquence mesurée : `slot()` réduisait un mois entier à **4 créneaux** au lieu de ~2 976,
et tous les compteurs de congestion planifiée (`arr_prev/now/next`, `arr_load_ratio`, `dep_now`) étaient
devenus des constantes quasi dépourvues de sens — inoffensifs, mais inutiles. Corrigé via `total_seconds()`
(exact quelle que soit la résolution), test ajouté (`tests/test_observed_traffic.py`).

**Ce que la correction change au score, mesuré** : `causal-r12-epochfix` refait les quatre plis avec
l'échelle juste → 558,7 s contre 557,1 s (+0,3 % ; janvier +1,9 %, février −0,05 %, juin +0,4 %,
juillet −0,5 %). **Non adoptable** au sens de D‑029 : les compteurs justes n'apportent rien de mesurable
au-dessus du bruit, ce qui est cohérent avec le fait que la congestion planifiée était déjà redondante avec
l'heure et l'aéroport. La correction est donc gardée pour ce qu'elle est — une **justesse**, pas un gain.

**Reproduction garantie malgré tout** : `FeatureSpec` porte désormais un drapeau `epoch_seconds`, faux par
défaut. Les spécifications gelées (et donc `src.predict`, `src.train_final`) reproduisent l'ancienne
échelle ; vérifié en refaisant le pli de janvier (`causal-r13-repro` : **540,0 s**, identique à
`causal-r2`). Les fichiers fournis restent donc régénérables à l'identique, et les nouvelles courses
(`src.refattente`) demandent explicitement l'échelle juste. C'est le troisième défaut de notre propre code
trouvé, mesuré et consigné après D‑018 (hachage N×N) et D‑020 (dtype du gabarit).

## D‑035 — Ce que coûte une version « défendable sans discussion » : mesuré par réentraînement (2026‑10‑10)

Question posée par l'équipe : si l'on refusait de supposer que le poste de parking (`STAND_mvt`) et le
dernier horaire de pushback connu (`LOBT_flt`) sont disponibles à t0, combien cela coûterait-il ? L'audit
`T0_DISPONIBILITE.md` répondait par une effacement à l'inférence (+8,5 % pour le poste) ; cette décision
apporte la mesure forte : **réentraînement complet**, quatre plis tenus hors, tout le reste inchangé.

**Règle de lecture écrite avant exécution** : la variante épurée serait retenue si son coût restait
≤ 1 % au global et ≤ 1,5 % sur chacun des quatre mois cibles. Au-delà, on garde la version complète et la
réserve est écrite dans le document de réponse.

| variante | janvier | février | juin | juillet | janv.+juil. | global | bootstrap apparié (variante/référence) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `causal-r2` (référence) | 540,0 | 555,4 | 459,0 | 650,2 | 603,5 | **557,1** | — |
| sans poste (`causal-r10-nostand`) | +2,64 % | +1,58 % | +2,20 % | +1,48 % | **+1,90 %** | 567,6 (+1,88 %) | IC95 [1,0129 ; 1,0265] → **perte établie** |
| sans `LOBT` (`causal-r11-nolobt`) | +0,10 % | −0,14 % | +0,20 % | +0,01 % | **+0,04 %** | 557,3 (+0,04 %) | IC95 [0,9992 ; 1,0016] → non départageable |

**Où la perte du poste se concentre** (lignes appariées, par tranche de durée réelle) : 0–20 min
(76,4 % des lignes) **+7,96 %** ; 20–40 min (22,3 %) +2,27 % ; 40–60 min +0,84 % ; > 60 min **+0,45 %**.

L'hypothèse de l'équipe — « le poste pèse peu sur le ventre de la distribution et beaucoup sur les
anomalies » — est **l'inverse de la mesure** : le poste est une information du ventre (il dit « tel poste à
Rome roule en général 12 minutes, tel autre 35 »), et les anomalies ne sont expliquées par aucune variable
(Fait 4). C'est aussi la fin d'une hésitation sur le dépôt : retirer le poste coûterait ~2 % au fichier de
prédiction, exactement sur les mois notés.

**Décision** : variante sans poste **refusée** (coût établi, deux fois le seuil) ; variante sans `LOBT`
statistiquement gratuite (+0,04 %, intervalle contenant 1) mais **non adoptée** faute de raison de la
préférer — nous gardons `LOBT` et nous consignons ce fait dans l'argumentaire d'admissibilité : *si un
organisateur jugeait `LOBT` trop tardif, son retrait ne coûterait rien de mesurable*, contrairement au poste.
Outils : `configs/tabular_causal_nostand.toml`, `configs/tabular_causal_nolobt.toml`,
`scripts/d035_sensitivity.py`.

## D‑036 — Le facteur de transfert local → période notée est mesuré, plus seulement projeté (2026‑10‑10)

D‑030 avait échoué à projeter le score officiel depuis le seul proxy (écart maximal 24 %, intervalle ×1,58).
Les étiquettes d'arrivée découvertes en D‑034 permettent de faire la même mesure **sur du vrai**, sans
conserver ni cible cachée : une recette entraînée sur 2025 est évaluée deux fois, sur janvier + juillet 2025
(local) puis sur janvier + juillet 2026 (les mois notés), avec un entraînement strictement identique et
aucun réglage sur 2026.

**Critère écrit avant exécution** : si le facteur est dans [0,90 ; 1,15], nos chiffres locaux se reportent
sans correction autre que l'intervalle annoncé ; sinon on corrige toutes les attentes par ce facteur et on
l'écrit.

| mesure | RMSE | lignes |
| --- | ---: | ---: |
| modèle (discipline de la piste prédiction), local 2025 | **271,1 s** | 343 999 |
| même modèle, période notée 2026 | **289,1 s** | 344 693 |
| facteur mesuré (modèle) | **1,0666** | — |
| facteur mesuré (référence « moyenne par aéroport lissée ») | 1,0447 | — |

Le facteur est donc d'environ **+5 à +7 %**, et à peu près indépendant de la recette : la période notée est
légèrement plus dure que nos mois locaux, pas radicalement. En appliquant cette fourchette à nos fichiers :

| fichier | local janv.+juil. | attendu sur le classement (×1,045 à ×1,067) |
| --- | ---: | ---: |
| référence (proxy + biais) | 643,6 | ≈ 672 – 687 s |
| prédiction (causale) | 603,5 | ≈ 631 – 644 s |
| reconstitution (proxy + correction) | 519,9 | ≈ 543 – 555 s |

**Limites écrites, parce qu'elles comptent** : la mesure porte sur des **arrivées** (taxi‑in), dont
l'étiquette ne souffre pas du problème d'attribution du Fait 4 ; le transfert propre aux départs reste donc
non vérifié, et l'intervalle ci-dessus ne couvre que le **décalage de niveau**, pas l'incertitude sur les
extrêmes. Un seul relevé, aucun réglage derrière (D‑034). Outil : `src/arrival_transfer.py`,
`reports/ARRIVAL_TRANSFER.json`.

**Ce que ça change à la stratégie de dépôt** : le dépôt de mesure (fichier de référence) n'est plus la seule
façon d'obtenir un facteur — il en confirme un. Il reste utile parce qu'il porte sur **notre population de
départs**, ce que les arrivées ne remplacent pas.

## D‑037 — « Référence + attente » avec trafic réellement observé avant l'ancre : construit, mesuré, **refusé** (2026‑10‑10)

L'architecture demandée par l'équipe : à la prédiction causale existante (la « référence » : calendrier,
aéroport, type d'appareil, poste, opérateur, géométrie poste→piste apprise des arrivées) s'ajoute une
« attente » calculée sur le trafic **réellement réalisé strictement avant l'ancre** — décollages et
atterrissages passés dans des fenêtres de 15, 45 et 90 minutes, temps écoulé depuis le dernier mouvement,
ratio décollages/arrivées. Discipline vérifiée par tests (`tests/test_observed_traffic.py`) : fenêtres
strictement antérieures à l'ancre, futures exclues, et **le vol évalué ne compte jamais son propre
décollage**.

**Résultat (quatre plis tenus hors, contre `causal-r2`)** : 555,4 s contre 557,1 s, soit **−0,32 %** au
global comme sur janvier + juillet combinés ; par mois, janvier **+0,87 %**, février −0,68 %, juin
+0,10 %, juillet −0,98 %. Les neuf variables observées pèsent bien ~11 % des décisions (jusqu'à 3,0 % pour
`obs_arr_90` seul) — mais ne produisent pas le gain demandé. **Refusé au sens de D‑029** (il faudrait −1 %
sur chacun des quatre mois ; deux mois sont légèrement dégradés).

**Pourquoi ce résultat est utile malgré tout** : la congestion *réalisée* avant l'ancre apporte peu parce
qu'elle est largement redondante avec ce que le modèle sait déjà par l'heure, l'aéroport et le plan de vol —
le même constat qu'en D‑016 (pression à destination) et D‑034 (compteurs planifiés). L'information qui
manque n'est pas « combien d'avions ont bougé avant », mais **pourquoi celui-ci reste bloqué** : le Fait 4,
encore et toujours. Le code reste disponible (`src/refattente.py`) et documenté ; les recettes gelées et les
trois fichiers fournis ne sont pas touchés.

## D‑038 — Clôture de la journée d'audit : ce qui change, ce qui ne change pas (2026‑10‑10)

**Ce que cette journée a ajouté à la connaissance du problème** : la portée réelle du classement
(janvier + juillet, non quatre mois — D‑034) ; l'existence de 670 407 étiquettes d'arrivée 2026, qui réfute
l'hypothèse d'une population 2026 plus douce et fournit un facteur de transfert mesuré de +5 à +7 % (D‑034,
D‑036) ; le coût chiffré d'une version « défendable sans discussion » (+1,9 % sans poste, +0,04 % sans
`LOBT`, D‑035) ; un défaut d'échelle dans notre propre code, corrigé sans toucher aux fichiers fournis
(D‑034) ; et une réponse négative mais outillée à l'architecture « référence + attente » (−0,3 %, refusée,
D‑037).

**Ce qui ne change pas** : aucune recette n'a été adoptée aujourd'hui — D‑029 n'a passé aucune des quatre
variantes mesurées. Les trois fichiers fournis sont donc **inchangés au bit près**, et cette fois **prouvé par
regénération complète** (2026‑10‑10) : les trois pistes `src.predict` reproduisent leurs empreintes à l'octet
près — `dd005031…` (prédiction), `66223d9b…` (reconstitution), `d0ab0cb8…` (référence). Au passage, une lacune
de notre propre documentation a été corrigée : la commande qui produit le fichier de référence
(`--track hybrid --config configs/tabular_hybrid_noclip.toml`) n'était consignée nulle part ; elle est
désormais dans le README §9 et `DEPOT.md`, avec les trois empreintes complètes. La réserve interne reste
fermée (ouverture déjà consommée). Le réglage reste arrêté.

**Ce qui est prêt pour la suite**, dans `DEPOT.md` : renommage dès réception du nom d'équipe, validation
et empreintes avant envoi, dépôt de mesure du fichier de référence avec la fourchette attendue (**≈ 672 –
687 s**, à comparer aux 643,6 s locales sur janvier + juillet — et non aux 591,7 s des quatre mois), puis
choix tracé de l'unique `<team>_final.parquet` entre les trois options chiffrées.

**Documentations mises à jour dans le même mouvement** : `RULES.md` (portée du classement, arrivées
étiquetées, meilleure soumission retenue), `DATA_DICTIONARY.md` (taux d'absence mesurés champ par champ,
rôle réel des quatre fichiers d'évaluation), `VALIDATION_PROTOCOL.md` (janvier + juillet comme lecture
principale, discipline des fenêtres observées, usage encadré des étiquettes d'arrivée), README (Fait 4 chiffré
juste, section 7 sur la vérité 2026, limites, commandes de reproduction), `experiments/REGISTRY.md` (cinq
nouvelles lignes). Suite de tests : **57 tests** verts.

## D‑008 — Restitutions obligatoires avant clôture (ouvert)

1. Nom d'équipe + clés MinIO pour déposer (bloqué : en attente utilisateur — préfixes `ATTENTE-` conservés,
   renommage décrit dans `DEPOT.md` étape 0).
2. Publication du code sous GPLv3 sur GitHub (exigence d'éligibilité). Le dépôt git local est **encore sans
   aucun commit** au 2026‑10‑10 : le versionnage a été reporté par l'équipe, il reste à faire avant toute
   publication publique (`git add -A && git commit`, puis fork du compte du challenge).
3. Un unique fichier `<team>_final.parquet` à produire après décision D‑004.

## D‑009 — Limite de dépôt respectée sans exploration (adoptée)

5 soumissions/jour maximum, aucune soumission sondant les cibles cachées : la page Ranking
signale cette pratique comme déloyale. Le réglage se fait donc entièrement sur données locales.

## D‑010 — Environnement isolé et verrouillé (adoptée)

venv dédié CPython 3.13 via `uv`, paquets installés depuis le cache local, aucune installation
globale ; empreintes SHA‑256 des fichiers officiels enregistrées à chaque exécution.


## D‑039 — Journal du dépôt V7 et correction de la formule « à l'octet près » (2026‑10‑12)

**Fait.** Le fichier `lighthearted-sandwich_v7.parquet` a été **déposé le 2026‑10‑11 au soir**, après
renommage manuel depuis `Taxipredict_v7new/causal/soumission/lighthearted-sandwich_v7A.parquet`,
**depuis une autre machine**. **Périmètre confirmé par le déposant le 2026‑10‑12 : la version soumise
est celle de 344 841 lignes**, c'est-à-dire janvier + juillet 2026, conforme à `submitting.parquet`.
**La réponse finale de 670 790 lignes (quatre mois) n'est pas encore déposée** : c'est la seule
action restante avant l'échéance. Le doute consigné dans le README du paquet (« rien ne prouve que le
script de la finale accepte moins que 670 790 lignes ») ne se pose donc plus pour cette étape — il ne
se poserait que si l'on voulait déposer un fichier versionné sur les quatre mois.

**Revalidation du fichier soumis, faite le 2026‑10‑12** contre son propre gabarit
(`submitting.parquet`) : 344 841 lignes, identifiants identiques **et dans le même ordre**, aucune
valeur non finie, aucune valeur négative, cible en `int32`, médiane 978 s, maximum 15 701 s,
empreinte `b00028e4ca048716…`. Le validateur du projet (`src.validate_submission`) ne charge que le
gabarit des quatre mois : **pour un fichier de 344 841 lignes, comparer à `submitting.parquet`**.

**Empreintes des fichiers sources, vérifiées le 2026‑10‑12** (paquet `Taxipredict_v7new`, manifeste
régénéré le 2026‑10‑11 20:47) :

| fichier | lignes | SHA‑256 |
| --- | ---: | --- |
| `causal/soumission/lighthearted-sandwich_v7A.parquet` | 344 841 | `b00028e4ca0487169a59bd6f15a5cd28247179cb2fa2c6461314d7ab06007508` |
| `causal/soumission/lighthearted-sandwich_finalA.parquet` | 670 790 | `49f401e3872728cffa2c7973437c8557f0b256fcf74a5757475514dffc377ca2` |

**Équivalence avec les artefacts du projet, mesurée ce jour.** Sur les 670 790 lignes : mêmes
identifiants dans le même ordre et **toutes les valeurs prédites identiques à l'unité près** entre
`causal/soumission/lighthearted-sandwich_finalA.parquet` et `submission/ATTENTE-nom-equipe_causal_v1.parquet`
(`dd005031…`). Les octets diffèrent parce que la cible est écrite en `int32` dans le paquet (conforme
aux types arrow des gabarits) et en `float64` dans le projet.

**Correction de vocabulaire, à appliquer partout** : nous écrivions que les fichiers du paquet étaient
« inchangés **à l'octet près** » par rapport à ceux du projet. C'est faux au sens strict — seul le
contenu des prédictions est identique. Formule exacte : **« mêmes valeurs de prédiction sur toutes les
lignes ; octets différents selon le typage de la cible (`int32` contre `float64`) »**. Les empreintes
du projet lui‑même (`dd005031…`, `66223d9b…`, `d0ab0cb8…`) restent valables et revérifiées.

**Ce que le dépôt n'a pas encore mesuré** : aucun score officiel n'a été relevé à ce jour, donc le
facteur de transfert local → classement (**+5 à +7 %**, D‑036) reste une estimation déduite des
étiquettes d'arrivée 2026 et non un fait observé. Notre attente pour V7 est écrite à l'avance :
**≈ 632 – 645 s** sur janvier + juillet (584 – 596 s si les quatre mois sont comptés).

## D‑040 — La campagne V2 est publiée comme exploration ; rien n'est adopté (2026‑10‑12)

Le dossier `prc2026-v2/` a mesuré une variante conforme à nos règles de causalité — **V7A′**, moyenne
de quatre tirages de graines du booster gelé (mêmes données, mêmes 34 variables, mêmes 278 arbres) —
à **−0,13 %** sur janvier + juillet, meilleur sur les quatre mois tenus hors, intervalle apparié
[0,9974 ; 0,99997]. **Elle n'est pas déposée** : D‑029 exige −1 % sur chacun des quatre mois, « sans
exception de confort ». L'aménagement que la campagne V2 avait rédigé pour l'autoriser
(`prc2026-v2/docs/V2_JOURNAL.md`, D‑V2‑01) est **rapporté** ; la règle appliquée reste D‑029 à la lettre.

**Renoncements chiffrés, assumés par écrit** : −0,79 s (moyenne de quatre tirages) et −1,5 à −2,5 s
attendues d'un entraînement sur douze mois — deux gains inférieurs à l'incertitude de notre propre
score (± 7 s de facteur de transfert, ± 10 à ± 30 s de tirage sur la poche extrême). Aucune variante
ne sera déposée pour les comparer : le classement retient la meilleure soumission de l'équipe.

**Ce que V2 apporte au dossier**, sans changer le dépôt : la preuve de causalité rejouable sur le
modèle déposé (`maxdiff = 0,0 s`), dix‑sept pistes refusées avec leurs chiffres (dont six traitements
des cibles aberrantes montrant que **les anomalies instruisent l'estimateur au lieu de le polluer**),
la valeur mesurée d'un mois d'entraînement (+0,396 % pour un voisin de saison, +0,253 % pour un mois
moyen), et une réponse chiffrée à « pourquoi pas −200 s » : 259 vols sur 671 292 portent 53 % du carré
d'erreur, et la connaissance parfaite du niveau réalisé de chaque journée ne vaudrait que −0,2 %.

## D‑041 — Corrections documentaires : réserve interne et empreintes du paquet (2026‑10‑12)

1. `experiments/REGISTRY.md` affirmait « la réserve (nov+dec 2025) n'a **jamais** été ouverte », en
   contradiction avec **D‑023**, qui consigne une ouverture exécutée le 2026‑10‑10 06:17 après gel
   (marqueur `reports/RESERVE_OPENED.json`). La phrase est corrigée pour dire la vérité exacte : jamais
   utilisée pour entraîner, régler ou choisir une recette ; évaluée une seule fois, aucune décision n'en
   a été tirée.
2. `Taxipredict_v7new/README.md` portait les empreintes d'une écriture parquet antérieure
   (`bbd75da5…`, `d2be680d…`, `7c3587d6…`, `ab5d41eb…`). Le tableau est aligné sur
   `MANIFEST.sha256` (régénéré le 2026‑10‑11 20:47), qui est conforme aux fichiers sur disque.
3. Un contrôle rejouable a été ajouté côté exploration : `prc2026-v2/scripts/audit_reserve.py` vérifie
   qu'aucune métrique ne porte sur novembre/décembre, qu'aucun script n'utilise la réserve hors contrôle
   explicite et qu'aucun cache de ces mois ne subsiste. Verdict au 2026‑10‑12 : **CONFORME**. Un incident
   de traçabilité y est consigné : le 2026‑10‑12 à 12:39, une inspection de schéma a chargé le frame des
   départs de novembre (noms de colonnes et nombre de lignes seulement) et laissé un cache, supprimé
   depuis.

**Périmètre exact des écritures du 2026‑10‑12 dans ces deux dossiers** : trois lignes de documentation
— `DECISIONS.md` (D‑039 à D‑041), la phrase sur la réserve dans `experiments/REGISTRY.md`, le
tableau d'empreintes et une note dans `Taxipredict_v7new/README.md` — plus, en conséquence, la ligne
`./README.md` régénérée dans `Taxipredict_v7new/MANIFEST.sha256` (44/44 empreintes conformes après
mise à jour). **Aucun modèle, aucun fichier de soumission n'a été touché** : les empreintes des dix
fichiers de `submission/` et des modèles gelés ont été comparées avant/après, aucune différence.
