# Stroop IRMf — pilote à quatre runs

Lancer `python main.py`, saisir le sujet, choisir l'écran et le mode PC/fMRI,
puis utiliser **TRAINING** ou l'un des quatre boutons **RUN**. Le menu se rouvre
après chaque entraînement et chaque acquisition, avec les réglages conservés.
Les pauses et acquisitions REV_PE se font entre les runs, hors du programme.

Le pilote est décrit dans [design.md](design.md). Les quatre fichiers fournis
sont les références, lus dans leur ordre exact, sans nouvelle randomisation :

| Bouton | TSV lu | Essais C/I/N | Fin du planning | Acquisition à TR 1,23 s |
| --- | --- | --- | --- | --- |
| RUN 1 · E2_A | `run-01_E2_A_events.tsv` | 60/60/30 | 520 s | 423 volumes · 520,29 s |
| RUN 2 · E3_A | `run-02_E3_A_events.tsv` | 48/48/24 | 520 s | 423 volumes · 520,29 s |
| RUN 3 · E3_B | `run-03_E3_B_events.tsv` | 48/48/24 | 520 s | 423 volumes · 520,29 s |
| RUN 4 · E2_B | `run-04_E2_B_events.tsv` | 60/60/30 | 520 s | 423 volumes · 520,29 s |

Le choix du run est indépendant du numéro du sujet. Un même sujet peut effectuer
les quatre runs. Chaque acquisition, y compris partielle, est protégée contre
l'écrasement ; elle ne bloque pas les autres runs. `5` et `005` désignent le même
sujet (`sub-005`). L'entraînement a sa propre numérotation.

## Présentation et synchronisation

- Croix de fixation initiale pendant les 10 secondes définies dans le TSV.
- Chaque mot et sa fenêtre de réponse durent **2 secondes**, même en cas de
  réponse précoce. L'offset et l'onset suivants restent programmés sur l'horloge
  du run ; une réponse ne change jamais le planning.
- Les mots, encres, conditions, délais de réponse et fixations variables
  proviennent du TSV. Les paramètres RGB, police, taille et position restent
  communs aux quatre runs, dans `config/tasks_config/stroop.yaml`.
- Aucun indice de couleur, dessin de boîtier ou feedback pendant le RUN.
- La fixation finale de **15 secondes est déjà comprise dans le TSV**.
  La croix reste ensuite affichée 0,29 seconde pour terminer le dernier volume
  entier. Il n'y a pas de repos de 10 secondes ajouté à cette nouvelle version.
  Le marqueur de fin et le bilan interviennent après cette période.

Le TR utilisé pour calculer le nombre de volumes et le complément final est
`repetition_time_sec: 1.23` dans le YAML. Le menu calcule sa durée depuis les TSV
et ce TR. L'acquisition IRM doit couvrir les 423 volumes par run ; le script ne
pilote pas sa durée depuis la console du scanner.

**Le zéro correspond au premier volume fonctionnel conservé**, pas au début des
30 secondes de REV_PE. Valider les consignes avec `s` au moment approprié, puis
attendre le trigger `t` du run fonctionnel. Si des triggers de volumes préparatoires
supprimés arrivent pendant cette attente, renseigner leur nombre dans
`discard_initial_triggers` (défaut : 0). Ils sont ignorés avant le reset de l'horloge.
Les pulses suivants restent enregistrés pendant les stimuli et toutes les fixations.

Le chargement vérifie la congruence réelle, le mapping, les onsets/offsets, la
fenêtre de réponse, les colonnes temporelles redondantes et la durée totale.
Un planning incohérent est rejeté avant l'acquisition.

## Touches

Répondre à la couleur de l'encre en ignorant le sens du mot.

| Encre | Mode PC | Mode fMRI |
| --- | --- | --- |
| Rouge | Flèche droite | b |
| Bleu | Flèche bas | y |
| Vert | Flèche gauche | g |

Le mode PC est en plein écran, comme le mode fMRI. La flèche du milieu est
la flèche bas.

`s` valide les consignes et le bilan d'entraînement ; `t` est le trigger par défaut ;
`Échap` interrompt le run et sauvegarde les essais terminés.
La première réponse valide dans la fenêtre est retenue. Les pressions pendant
la fixation n'entrent pas dans les résultats des essais.

## Entraînement

L'entraînement reste indépendant des quatre acquisitions :

1. Découverte du boîtier pendant 20 s. Le dessin horizontal affiche les couleurs
   des réponses : **rouge, bleu, vert, gris**. Chaque pression fait clignoter
   le bouton correspondant. Seuls b/y/g répondent aux essais ; r reste inutilisé.
2. 18 pastilles avec rappel des associations et feedback (54 s).
3. 18 pastilles sans rappel, avec feedback de justesse uniquement (54 s).
4. Neuf exemples Stroop, trois par condition, tirés de E2_A. Les mots, couleurs,
   durée de 2 s et fixations sont ceux du format final, sans rappel ni feedback.

Une consigne de 4 s précède chaque série. La durée totale reste de l'ordre de
3 minutes, hors lecture des consignes initiales et du bilan final.

Le bilan exige par défaut au moins 80 % de réussite dans les séries sans rappel
et Stroop, au moins une réussite par couleur dans chacune, ainsi que la
vérification des trois boutons actifs. Il s'agit d'un critère pratique de pilotage,
configurable sous `training.accuracy_threshold`, et non d'un seuil validé par la
littérature. Le bilan ne verrouille pas les boutons RUN ; relancer l'entraînement
si des points sont à reprendre.

## Résultats

Les résultats se trouvent dans `data/sub-<numéro>/stroop/`, par exemple :
`sub-005_task-stroop_design-E3_A_run-02_events.tsv`.

- `*_events.tsv` et `*_events_incremental.tsv` : événements réellement présentés,
  réponses, RT, justesse, erreurs et omissions (`n/a` pour une réponse absente).
  `onset`, `stimulus_offset` et `duration` mesurent les flips d'écran ;
  `planned_onset`, `planned_stimulus_offset`, `planned_duration` et
  `planned_response_deadline` gardent les horaires de référence.
- `planned_not_acquired` vaut **0 dans les résultats**, contre **1 dans les TSV
  de référence**. Les champs `source_design`, `source_seed`, `source_phase`,
  `stimulus_set` et `context` gardent la provenance.
- `*_events.json` décrit chaque colonne.
- `*_design.json` enregistre le planning utilisé, l'empreinte SHA-256 du TSV,
  les touches, le TR, le nombre de volumes, les 15 s de fixation finale et le
  complément pour terminer le dernier volume.
- `*_scantrig.json` enregistre les pulses et le TR mesuré si au moins deux
  triggers ont été reçus.
- `*_training_report.json` conserve le bilan de l'entraînement et la vérification
  du boîtier.

En fin de RUN, un mini-bilan apparaît une fois dans la console et dans le fichier
`.log` du participant (`data/sub-<numéro>/logs/`). Il donne les réponses correctes,
incorrectes et absentes par condition, et les TR moyens sur réponses correctes.
Il affiche les écarts descriptifs I−C, I−N et N−C en millisecondes et en points
pour les taux de réussite, d'erreur et d'absence. Les résultats portent sur les
seuls essais acquis, avec leur nombre réel par rapport aux 150 ou 120 attendus.

## Installation et vérification

Utiliser un environnement Python compatible avec PsychoPy :

```bash
python -m pip install -r requirement.txt
python main.py
python run_experiment.py --subject 5 --run 1 --mode fmri
python run_experiment.py --subject 5 --run 2 --mode fmri
python run_experiment.py --subject 5 --training --mode pc
python tools/check_designs.py
python tools/check_outputs.py data/ --all
python -m pytest -q
```

Sans PsychoPy, les tests de logique et du menu Qt peuvent tourner avec :

```bash
STROOP_HEADLESS_TESTS=1 QT_QPA_PLATFORM=offscreen python -m pytest -q
```

L'horloge d'écran est alors simulée et les tests de l'horloge PsychoPy réelle
sont ignorés. Le menu utilise le vrai Qt. L'import, les touches du boîtier,
la synchronisation et le timing physique restent à vérifier sur le poste
avant acquisition, comme indiqué dans `design.md`.
