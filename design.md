# Pilote Stroop — quatre runs de 8 min 40 s — version du 17 novembre 2026

Ordre : E2_A, E3_A, E3_B, E2_B. Deux plans indépendants par famille, issus d'une nouvelle optimisation. Cette version remplace les versions de dix minutes et de 8 min 30/8 min 45. Ne pas mélanger leurs horaires ou fichiers SPM.

| Famille | Durée de tâche, fixations incluses | C/I/N | Premier onset | Dernier offset | Volumes à TR 1,23 s | Acquisition couvrante |
|---|---|---|---|---|---|---|
| E2 | 520 s (8 min 40) | 60/60/30 | 10 s | 505 s | 423 | 520,29 s |
| E3 | 520 s (8 min 40) | 48/48/24 | 10 s | 505 s | 423 | 520,29 s |

Fixation initiale de 10 secondes et finale de 15 secondes dans chaque fichier. Les durées ne sont pas des multiples entiers du TR : conserver la croix après la fin planifiée jusqu'à la fin de l'acquisition, soit 0,29 s supplémentaires dans chaque run. Volumes indiqués hors éventuels volumes préparatoires non conservés ; le multiecho ne multiplie pas le nombre de points temporels.

## Présentation

Stimulus de 2 secondes et fenêtre de réponse de 2 secondes, même si la réponse est précoce. Fixation variable entre les essais. SOA moyen E2 : 3,309 s ; E3 : 4,143 s. Garder les consignes, taille, police, position et couleurs physiques identiques entre les runs. Le TSV définit des noms de couleurs, pas leur calibration RGB.

Mapping conservé : rouge → b, vert → g, bleu → y. Neutres : TABLE, ETAT, LIEU. Vérifier les codes réellement émis par votre boîtier.

Origine onset=0 : début du premier volume conservé et modélisé. Les 30 s de REV_PE sont hors de ce temps. Si vous démarrez sur un trigger antérieur à des volumes supprimés, corriger l'origine en conséquence. Enregistrer les onsets/offsets effectivement affichés (quantification par les images écran), réponses, RT, erreurs, omissions et triggers. Les TSV sont planifiés (`planned_not_acquired=1`), pas des résultats acquis. L'analyse définitive utilisera les logs réels.

## Pseudorandomisation et limites

40 % C, 40 % I, 20 % N. Couleurs/boutons exactement équilibrés dans chaque condition ; mots de couleur équilibrés dans C et I ; six associations incongruentes à fréquence égale. Mots neutres et couleurs neutres équilibrés séparément. Les neuf cellules mot neutre × couleur ont des fréquences différant d'au plus un essai (30 et 24 ne sont pas divisibles par neuf) : ce croisement est quasi équilibré, pas exactement équilibré.

Les neuf transitions de condition sont présentes ; les probabilités du prochain type restent proches de 40/40/20 (écart maximal fixé à 8,5 points). Les transitions de couleur sont proches de l'équiprobabilité et les répétitions de couleur autour de 1/3, également équilibrées autant que possible par type de transition de condition. Maximum cinq conditions identiques et quatre couleurs identiques de suite ; pas de dix essais alternant systématiquement deux conditions. Des fenêtres glissantes larges écartent les déséquilibres extrêmes, sans imposer de miniblocs fixes. Ne pas annoncer les contraintes au participant.

La séquence est fixée avant l'expérience, non adaptative aux réponses. Trois couleurs avec autant de C que de I impliquent que chaque mot de couleur est congruent dans 50 % de ses occurrences, contre 25 % pour chacune des autres couleurs. Cette contingence est équilibrée entre mots mais non supprimée. La tâche vise I−C ; elle n'isole pas une mesure pure d'adaptation au conflit. Les répétitions partielles mot/couleur/réponse ne sont pas toutes supprimées.

## Optimisation et validation

2 000 candidats admissibles par run sur 20 tirages temporels ; présélection des 25 meilleurs selon I−C puis sélection robuste dans neuf modèles. HRF double gamma, positive gamma(6,1), négative gamma(16,1)/6, tronquée à 32 s et intégrale unité ; boîtes 2 s ; TR=1,23 s ; constante et DCT passe-haut 128 s ; covariance AR(1) connue, rho central=0,3. Robustesse : forme positive 5/6/7 × rho 0,1/0,3/0,6. Sélection selon le minimum des neuf efficacités brutes, une heuristique qui privilégie le scénario le moins favorable. Pas de modèle des mouvements, erreurs ou physiologie. E=1/[c'(X'R^-1X)^-1c]. Ce sont des hypothèses, pas des paramètres de bruit mesurés dans vos données.

Les contrôles exécutés portent sur les effectifs, la congruence réelle des mots/couleurs, le mapping, les contraintes de répétition, le non-chevauchement, les durées, les bornes de fixation et la correspondance entre TSV et fichiers MAT. Les tableaux détaillés et graines sont fournis. La recherche finie ne prouve pas une optimalité globale et ne garantit pas l'effet BOLD. Aucun résultat du sujet n'a servi à sélectionner un ordre. L'optimisation a été relancée pour chaque durée, pas obtenue par simple troncature des anciens fichiers.

## SPM

Les fichiers *_conditions.mat contiennent names, onsets, durations dans l'ordre C,I,N. `prepare_spm_conditions.m` permet de les recréer. Une session par run. Ces fichiers servent à préparer le modèle ; utiliser les événements réellement présentés pour l'analyse. Pour exactement trois colonnes canoniques C,I,N, I−C=[-1,1,0] ; adapter à la matrice réelle et aux dérivées/nuisances. Ne pas appliquer ce vecteur aveuglément aux quatre sessions.

Analyser les quatre runs séparément pour évaluer le futur protocole à un run. Comparer amplitude, incertitude et stabilité dans des ROI indépendantes préspécifiées, avec RT/erreurs et I−N/C−N. La combinaison des runs reste complémentaire. Un pilote unique ne mesure pas la variance interindividuelle ni la différence attendue Becker/témoins.

## Durée totale

Quatre acquisitions fonctionnelles : 34 min 41,16 s. Quatre REV_PE de 30 s : total 36 min 41,16 s. Avec MPM 12 min : 48 min 41,16 s + durée T1. Exemple T1 5 min : 53 min 41,16 s, hors repérages, calibrations non incluses, transitions et pauses. Prévoir les pauses avant le REV_PE du run suivant.

## Utilisation et reproduction

Le programme de présentation n'est pas fourni : faire un essai technique d'import, synchronisation, mapping et affichage avant acquisition. Python >=3.10, numpy/pandas/scipy pour `python generate.py`. Les TSV livrés et leurs empreintes SHA-256 dans quality_control.json sont les séquences de référence. Le générateur réécrit TSV et métriques ; les fichiers MAT peuvent être recréés avec le script MATLAB.

Références : Wager & Nichols (2003), https://pubmed.ncbi.nlm.nih.gov/12595184/ ; Braem et al. (2019), https://pmc.ncbi.nlm.nih.gov/articles/PMC6699878/.
