# Fiche pratique — pilote Stroop

Le contrôle logiciel et les matrices GLM sont favorables au pilote. Le test du
boîtier et du trigger doit être fait sur le poste utilisé pour l’acquisition.
Le logiciel attend des codes clavier USB : réponses b/y/g et trigger t.

## 1. Vérifier le boîtier et le trigger

Depuis la racine du projet, avec l’environnement PsychoPy du poste IRM :

```bash
python tools/check_buttons.py --screen 1 --mode fmri
```

Adapter `--screen 1` à l’écran réellement utilisé (0 pour le premier écran).
L’écran de test affiche toutes les touches reçues, même celles qui ne sont pas
prévues dans le mapping. Appuyer sur chacun des trois boutons et vérifier :

| Réponse attendue | Code actuel |
| --- | --- |
| Rouge | b |
| Bleu | y |
| Vert | g |

Faire arriver un trigger du scanner : il doit apparaître comme `t`, et les
intervalles entre triggers doivent correspondre au TR de 1,23 s. Un `t` pressé
manuellement au clavier vérifie le code, mais pas la connexion du scanner.
Vérifier aussi que le texte est lisible sur l’écran vu par le participant.
`Échap` quitte le diagnostic ; il ne crée pas de données d’expérience.

## 2. Modifier les boutons en un seul endroit

Ouvrir **config/tasks_config/stroop.yaml** et modifier cette ligne :

```yaml
response_keys_fmri: {rouge: b, bleu: y, vert: g}
```

Par exemple, si le diagnostic montre que les boutons choisis émettent 1, 2, 3 :

```yaml
response_keys_fmri: {rouge: "1", bleu: "2", vert: "3"}
```

Utiliser exactement les noms indiqués par le diagnostic (le pavé numérique peut
avoir des noms distincts). Garder trois touches différentes, en minuscules.
Le programme rejette les doublons et les conflits avec `t`, `s` ou `escape`.
Ne pas attribuer le trigger à une couleur.

Le trigger est au même endroit :

```yaml
trigger_key: "t"
```

Après une modification, **enregistrer le YAML et relancer le script**, puis
refaire le diagnostic. Ne pas modifier les TSV pour changer les touches : ils
restent les références planifiées et les logs utilisent le mapping réellement
configuré. L’entraînement et les consignes reprennent automatiquement ce mapping.

En PC, la ligne indépendante reste :

```yaml
response_keys_pc: {rouge: left, bleu: down, vert: right}
```

## 3. Vérifier l’acquisition avec l’équipe IRM

- TR prévu : **1,23 seconde** ; **423 volumes fonctionnels conservés** par run.
  Durée couvrante : **520,29 s (8 min 40,29 s)**, hors éventuels volumes jetés.
- Le zéro doit être le trigger du **premier volume conservé et modélisé**.
  Les 30 s de REV_PE sont hors de ce temps. Si le scanner émet des triggers de
  volumes préparatoires après la validation des consignes, renseigner uniquement
  leur nombre dans `discard_initial_triggers` ; valeur actuelle : 0.
- Les 15 s de fixation finale sont déjà dans le planning. Laisser l’acquisition
  aller jusqu’à la fin des 423 volumes, avec la croix maintenue jusqu’à 520,29 s.

## 4. Lancer

```bash
python main.py
```

Choisir le sujet, le bon écran et **fMRI**. Faire **TRAINING**, puis lancer les
quatre runs dans cet ordre, avec les pauses prévues entre les acquisitions :

1. RUN 1 · E2_A — 150 essais.
2. RUN 2 · E3_A — 120 essais.
3. RUN 3 · E3_B — 120 essais.
4. RUN 4 · E2_B — 150 essais.

`s` valide les consignes. Après cette validation, le run attend le trigger `t`.
Le menu revient à la fin. Chaque run déjà enregistré est protégé : choisir un
nouveau numéro de sujet pour un nouvel enregistrement plutôt que d’effacer les
résultats existants par inadvertance.

En fin de run, vérifier la sauvegarde des événements et le rapport des triggers
si le scanner a émis plusieurs pulses. Les données sont dans
`data/sub-<numéro>/stroop/` et le mini-bilan dans la console et les logs.

## Audit déjà réalisé

Les quatre TSV ont été chargés et validés. L’audit numérique GLM donne des
matrices de rang complet sous les hypothèses décrites dans le
[rapport d’audit](analysis/glm_audit_2026-11-19_neutral_pool12/RAPPORT.md).
La dernière suite de tests logiciels compte **147 succès et 3 tests nécessitant
PsychoPy réel ignorés**. Cela ne remplace pas le test matériel ci-dessus.
