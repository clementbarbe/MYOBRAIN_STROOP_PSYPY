"""Read the fixed Stroop schedules without requiring PsychoPy."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from config.constants import PROJECT_ROOT

VARIANTS = 'ABCD'
COLOR_WORDS = {'rouge': 'ROUGE', 'bleu': 'BLEU', 'vert': 'VERT'}
FMRI_KEYS = {'rouge': 'b', 'bleu': 'y', 'vert': 'g'}


def inclusion_number(value: int | str) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise ValueError('Le numéro d’inclusion doit être un entier supérieur ou égal à 1.')
    return int(value)


def design_for_subject(subject: int | str) -> str:
    return VARIANTS[(inclusion_number(subject) - 1) % len(VARIANTS)]


def load_design(variant: str, directory: Path = PROJECT_ROOT) -> list[dict]:
    """Validate the TSV; never shuffle or regenerate its trials."""
    if len(variant) != 1 or variant not in VARIANTS:
        raise ValueError(f'Design Stroop inconnu : {variant}')
    path = directory / f'stroop_design_{variant}.tsv'
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        required = {
            'trial', 'variant', 'temporal_window', 'condition', 'trial_type',
            'onset', 'duration', 'word', 'ink_color', 'stimulus',
            'correct_response', 'fixation_after_sec', 'fixation_onset',
            'previous_condition', 'transition',
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'Colonnes manquantes dans {path.name}')
        trials = list(reader)
    if not trials:
        raise ValueError(f'Design vide : {path.name}')
    previous_end = 0.0
    previous_condition = 'START'
    for index, trial in enumerate(trials, 1):
        for key in ('trial', 'temporal_window'):
            trial[key] = int(trial[key])
        for key in ('onset', 'duration', 'fixation_after_sec', 'fixation_onset'):
            trial[key] = float(trial[key])
            if not math.isfinite(trial[key]) or trial[key] < 0:
                raise ValueError(f'{path.name}, essai {index} : {key} invalide')
        # Newer source schedules omit the old long-null annotation.
        trial.setdefault('is_long_null', 'False')
        if trial['is_long_null'] not in ('True', 'False'):
            raise ValueError(f'{path.name}, essai {index} : is_long_null invalide')
        trial['is_long_null'] = trial['is_long_null'] == 'True'
        ink, word, condition = trial['ink_color'], trial['word'], trial['condition']
        valid_condition = (
            (condition == 'congruent' and word == COLOR_WORDS.get(ink))
            or (condition == 'incongruent' and word in COLOR_WORDS.values()
                and word != COLOR_WORDS.get(ink))
            or (condition == 'neutral' and word not in COLOR_WORDS.values())
        )
        if (trial['trial'] != index or trial['variant'] != variant
                or ink not in COLOR_WORDS or not word or not valid_condition
                or trial['trial_type'] != condition
                or trial['stimulus'] != f'{word}:{ink}'
                or trial['correct_response'] != FMRI_KEYS[ink]
                or trial['duration'] <= 0 or trial['temporal_window'] < 1
                or trial['previous_condition'] != previous_condition
                or trial['transition'] != f'{previous_condition}->{condition}'):
            raise ValueError(f'{path.name}, essai {index} : stimulus incohérent')
        if (trial['onset'] < previous_end - 1e-6
                or not math.isclose(trial['fixation_onset'],
                                    trial['onset'] + trial['duration'], abs_tol=1e-6)
                or (index > 1 and not math.isclose(
                    trial['onset'], previous_end, abs_tol=1e-6))):
            raise ValueError(f'{path.name}, essai {index} : timing incohérent')
        previous_end = trial['fixation_onset'] + trial['fixation_after_sec']
        previous_condition = condition
    return trials

