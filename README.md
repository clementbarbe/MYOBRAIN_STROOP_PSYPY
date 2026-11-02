# Stroop en IRMf

Lancer `python main.py`, saisir le numéro d’inclusion du sujet,
puis choisir **TRAINING** ou **RUN**. Le menu contient seulement le sujet,
l’écran, le mode PC/fMRI, le design associé, la durée et ces deux boutons.
Après l’entraînement, le menu se rouvre avec le sujet, l’écran et le mode conservés.

Le design est associé automatiquement au **numéro d’inclusion du sujet** :
**sujet 1 → A, 2 → B, 3 → C, 4 → D, 5 → A**, et ainsi de suite. Chaque groupe
successif de quatre inclusions reçoit donc une fois chacun des quatre designs.
Chaque participant effectue une seule acquisition (`run-01`). Une acquisition
existante, même partielle, est protégée contre l'écrasement. Les numéros `5` et
`005` identifient le même sujet (`sub-005`). Il n'y a pas de sélection de session,
de port parallèle ou d'eye-tracker. Le bouton **TRAINING** est placé au-dessus
de **RUN**.

La tâche lit directement `stroop_design_A.tsv` à `stroop_design_D.tsv`, sans
modifier leur ordre, leurs mots, leurs couleurs ou leurs timings. Chaque fichier
contient 75 essais : 30 congruents, 30 incongruents et 15 neutres. Le premier
stimulus apparaît à 10 s du trigger. Les onsets sont programmés depuis le même
zéro temporel pour éviter l'accumulation des retards.

Après la dernière fixation prévue dans le TSV, le RUN ajoute **10 secondes de
fixation seule**, sans mots ni indices de couleur. Les pulses scanner restent
suivis pendant cette période et le marqueur de fin est envoyé ensuite. Avec les
TSV actuels, cela porte la durée à **448,95 s (7 min 28,95 s)** depuis le trigger.
L'acquisition IRM doit rester active pendant cette période. Le menu affiche la
durée totale ; `final_rest_duration` dans `config/tasks_config/stroop.yaml`
permet de régler ce délai, également documenté dans `*_design.json`.

## Entraînement progressif et vérification des acquis

L'entraînement dure environ **3 minutes** : 3 min 10 à 3 min 18 avec les TSV
actuels, hors lecture des consignes initiales et du bilan. C'est un choix pratique
à piloter, sans prétention de durée ou de seuil validés par la littérature.

1. **Découverte du boîtier, 20 secondes** : une illustration horizontale affiche
   les couleurs de réponse de gauche à droite **rouge, bleu, vert, gris**. Chaque
   pression fait clignoter le bouton correspondant à l'écran. Seuls **b/y/g**
   servent à répondre ; le quatrième bouton (`r`), gris, réagit sur cet écran, mais est marqué
   « Non utilisé ». Les trois boutons actifs doivent être essayés.
2. **Association avec rappel, 18 essais / 54 secondes** : pastilles rouges,
   bleues et vertes, six de chaque couleur. Le schéma et les associations restent
   affichés. Chaque pastille dure 2 s, suivie de 1 s pour la correction.
3. **Même exercice sans rappel, 18 essais / 54 secondes** : plus de boîtier ni
   d'associations affichés. La correction indique uniquement « Correct »,
   « Incorrect » ou « Pas de réponse », sans donner la touche.
4. **Familiarisation Stroop, neuf essais** : trois exemples de chaque condition,
   tirés du design attribué au sujet. Les mots, encres, durées de stimulus
   (1,2 s), fixations et touches sont ceux du format final. Aucun rappel ni
   feedback n'est affiché, comme pendant l'acquisition. Une consigne de 4 s
   précède chacune des trois séries.

Le bilan final affiche les scores de chaque série. Le critère pratique par
défaut exige **au moins 80 % de réponses correctes dans chacune des deux
séries sans rappel**, au moins une réussite pour chaque couleur dans chacune,
et la vérification des trois boutons actifs pendant la découverte. Un
entraînement incomplet ou des omissions ne peuvent pas valider ces acquis.
Le seuil est modifiable dans `config/tasks_config/stroop.yaml`, sous
`training.accuracy_threshold`. Si le bilan signale des points à reprendre,
relancer l'entraînement avant l'acquisition ; le logiciel ne verrouille pas
le bouton de lancement de la tâche sur la base de ce résultat.

Le schéma montre directement les couleurs à indiquer :
**rouge → `b`**, **bleu → `y`**, **vert → `g`**. Les couleurs affichées
correspondent à celles des stimuli. En mode PC, les flèches remplacent ces trois
touches et activent les mêmes positions de l'illustration.

L'entraînement utilise les touches du mode choisi et démarre sans trigger après
les consignes. Il est enregistré sous `design-training`, avec une numérotation
indépendante des acquisitions. Les réponses, omissions et phases sont inscrites
dans les événements ; la vérification du boîtier et le bilan sont sauvegardés
séparément.

## Touches

Indiquer la **couleur de l'encre**, en ignorant le sens du mot.

| Couleur | Mode PC | Mode IRMf |
| --- | --- | --- |
| Rouge | Flèche gauche | b |
| Bleu | Flèche bas | y |
| Vert | Flèche droite | g |

- `s` : valider les consignes.
- `t` : démarrer la tâche au premier trigger du profil scanner par défaut.
- `Échap` : interrompre et sauvegarder les essais déjà acquis.

La première réponse pendant l'affichage du stimulus est enregistrée. Les
pressions pendant la fixation sont ignorées. Pendant le run d'acquisition,
**aucun indice de couleur, schéma de boîtier ou feedback** n'apparaît : seulement
les mots et la fixation. Les touches restent indiquées dans les consignes avant
le trigger. Les pastilles et les boutons de l'entraînement utilisent des unités
identiques sur les deux axes pour rester ronds quel que soit le format d'écran.

## Installation et ligne de commande

Utiliser un environnement Python compatible avec PsychoPy, puis installer les
dépendances avec `python -m pip install -r requirement.txt`.

```bash
python main.py
python run_experiment.py --subject 5 --mode fmri
python run_experiment.py --subject 5 --mode pc --training
```

Les profils d'écran et de matériel sont dans `config/scanners/` ; le profil
par défaut reste `pc` (trigger clavier `t`, sans sortie TTL). Les touches, les
couleurs et les paramètres visuels Stroop sont dans
`config/tasks_config/stroop.yaml`. Les TSV récents peuvent omettre l’ancienne
annotation `is_long_null` ; ils sont lus sans modifier leurs stimuli ni timings.

## Résultats et vérification

À la fin du RUN, un mini-bilan apparaît une seule fois dans la console et dans
le fichier `.log` du participant (`data/sub-<numéro>/logs/`). Pour chaque condition,
il indique les réponses correctes, incorrectes et absentes, le pourcentage de
réussite et le temps de réaction moyen en millisecondes, calculé uniquement sur
les réponses correctes avec un TR valide. Il affiche les écarts descriptifs
incongruent − congruent, incongruent − neutre et neutre − congruent, pour le TR
et les taux de réussite, d'erreur et d'absence (en points de pourcentage).
Une condition sans réponse correcte donne `n/a` pour le TR, jamais zéro.
Le bilan utilise uniquement les essais acquis et indique leur nombre par
rapport aux 75 attendus, y compris après une interruption.

Les résultats sont enregistrés dans `data/sub-<numéro>/stroop/` :

- `*_events.tsv` : essais, réponses, exactitude et temps de réaction ; `n/a` en
  cas d'omission. `onset` et `duration` mesurent les changements d'affichage.
  `planned_onset`, `planned_duration` et `onset_error` permettent de les comparer
  au TSV source.
- `*_events_incremental.tsv` : sauvegarde au fil de l'acquisition.
- `*_events.json` : description des colonnes.
- `*_design.json` : planning complet, touches et empreinte SHA-256 du TSV source.
- `*_training_report.json` : pressions de découverte, résultats par phase et par
  couleur, omissions et critère pratique de vérification des acquis.
- `*_scantrig.json` : pulses reçus et estimation du TR, si au moins deux pulses
  ont été reçus.

```bash
python tools/check_designs.py
python tools/check_outputs.py data/ --all
python -m pytest -q
```

Sur une machine dépourvue de PsychoPy, les tests de logique peuvent utiliser
`STROOP_HEADLESS_TESTS=1 QT_QPA_PLATFORM=offscreen python -m pytest -q`.
Ils emploient alors une simulation des imports PsychoPy et une horloge virtuelle ;
les tests de l'horloge PsychoPy réelle sont ignorés. Les tests Qt utilisent le vrai
menu. La précision physique de l'affichage et les triggers nécessitent une
vérification sur le poste d'acquisition.
