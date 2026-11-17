"""Load the four pilot schedules exactly as supplied, without PsychoPy."""

from __future__ import annotations

import csv
import math
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from config.constants import PROJECT_ROOT

DESIGNS = ('E2_A', 'E3_A', 'E3_B', 'E2_B')
COLOR_WORDS = {'rouge': 'ROUGE', 'bleu': 'BLEU', 'vert': 'VERT'}
FMRI_KEYS = {'rouge': 'b', 'bleu': 'y', 'vert': 'g'}


def inclusion_number(value: int | str) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise ValueError('Le numéro d’inclusion doit être un entier supérieur ou égal à 1.')
    return int(value)


def design_for_run(run: int | str) -> str:
    if isinstance(run, bool) or str(run) not in ('1', '2', '3', '4', '01', '02', '03', '04'):
        raise ValueError('Le run du pilote doit être compris entre 1 et 4.')
    return DESIGNS[int(run) - 1]


def run_for_design(design: str) -> int:
    if design not in DESIGNS:
        raise ValueError(f'Design Stroop inconnu : {design}')
    return DESIGNS.index(design) + 1


def design_path(design: str, directory: Path = PROJECT_ROOT) -> Path:
    return directory / f'run-{run_for_design(design):02d}_{design}_events.tsv'


def acquisition_timing(trials: list[dict], repetition_time_sec: float = 1.23) -> dict:
    """TSV already includes final rest; only pad to the next complete volume."""
    if not math.isfinite(repetition_time_sec) or repetition_time_sec <= 0:
        raise ValueError('Le TR doit être strictement positif et fini.')
    duration = Decimal(str(trials[0]['run_duration_sec']))
    tr = Decimal(str(repetition_time_sec))
    n_volumes = int((duration / tr).to_integral_value(rounding=ROUND_CEILING))
    acquisition_duration = n_volumes * tr
    return {
        'planned_duration': float(duration),
        'initial_fixation_duration': trials[0]['onset'],
        'final_fixation_onset': trials[-1]['fixation_onset'],
        'final_fixation_duration': trials[-1]['fixation_after_sec'],
        'repetition_time_sec': float(tr), 'n_volumes': n_volumes,
        'acquisition_duration': float(acquisition_duration),
        'padding_duration': float(acquisition_duration - duration),
    }


def load_design(design: str, directory: Path = PROJECT_ROOT) -> list[dict]:
    """Validate planned events and keep every supplied field and row order."""
    path = design_path(design, directory)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        required = {
            'trial', 'design', 'condition', 'trial_type', 'onset', 'duration',
            'response_window_sec', 'response_deadline', 'word', 'ink_color',
            'correct_response', 'stimulus', 'fixation_onset', 'fixation_after_sec',
            'planned_not_acquired', 'run_duration_sec', 'blank_after_response',
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path.name} : colonnes manquantes {sorted(missing)}')
        trials = list(reader)
    if not trials:
        raise ValueError(f'Design vide : {path.name}')
    previous_end = 0.0
    previous_condition = 'START'
    run_duration = None
    seed = None
    for index, trial in enumerate(trials, 1):
        def fail(message):
            raise ValueError(f'{path.name}, essai {index} : {message}')

        for key in ('trial', 'block', 'phase', 'planned_not_acquired', 'seed'):
            if key in trial:
                trial[key] = int(trial[key])
        for key in ('onset', 'duration', 'response_window_sec', 'response_deadline',
                    'fixation_onset', 'fixation_after_sec', 'run_duration_sec',
                    'blank_after_response', 'response_window', 'stimulus_offset',
                    'cycle_duration', 'fixation_after_stimulus'):
            if key in trial:
                trial[key] = float(trial[key])
                if not math.isfinite(trial[key]) or trial[key] < 0:
                    fail(f'{key} invalide')
        ink, word, condition = trial['ink_color'], trial['word'], trial['condition']
        valid_condition = (
            (condition == 'congruent' and word == COLOR_WORDS.get(ink))
            or (condition == 'incongruent' and word in COLOR_WORDS.values()
                and word != COLOR_WORDS.get(ink))
            or (condition == 'neutral' and word not in COLOR_WORDS.values())
        )
        if (trial['trial'] != index or trial['design'] != path.stem.removesuffix('_events')
                or ink not in COLOR_WORDS or not word or not valid_condition
                or trial['trial_type'] != condition
                or trial['stimulus'] != f'{word}:{ink}'
                or trial['correct_response'] != FMRI_KEYS[ink]):
            fail('stimulus, condition ou mapping incohérent')
        if trial['planned_not_acquired'] != 1:
            fail('le fichier doit contenir des événements planifiés, pas acquis')
        if (trial['duration'] <= 0 or trial['response_window_sec'] <= 0
                or trial['response_window_sec'] > trial['duration']):
            fail('fenêtre de réponse incompatible avec le stimulus')
        if trial['blank_after_response'] != 0:
            fail('la présentation doit conserver le mot après une réponse précoce')
        equalities = [
            (trial['fixation_onset'], trial['onset'] + trial['duration']),
            (trial['response_deadline'], trial['onset'] + trial['response_window_sec']),
        ]
        for alias, canonical in (('response_window', 'response_window_sec'),
                                 ('stimulus_offset', 'fixation_onset'),
                                 ('fixation_after_stimulus', 'fixation_after_sec')):
            if alias in trial:
                equalities.append((trial[alias], trial[canonical]))
        if 'cycle_duration' in trial:
            equalities.append((trial['cycle_duration'], trial['duration'] + trial['fixation_after_sec']))
        if index > 1:
            equalities.append((trial['onset'], previous_end))
        if (trial['onset'] < previous_end - 1e-6
                or any(not math.isclose(a, b, abs_tol=1e-6) for a, b in equalities)):
            fail('onset, offset, fixation ou fenêtre de réponse incohérent')
        if run_duration is None:
            run_duration, seed = trial['run_duration_sec'], trial.get('seed')
        if trial['run_duration_sec'] != run_duration or trial.get('seed') != seed:
            fail('métadonnées de run incohérentes')
        previous_end = trial['fixation_onset'] + trial['fixation_after_sec']
        # Runtime aliases; original TSV fields above retain their source values.
        trial.update(variant=design, temporal_window=trial.get('phase', 1),
                     is_long_null=False, previous_condition=previous_condition,
                     transition=f'{previous_condition}->{condition}')
        previous_condition = condition
    if not math.isclose(previous_end, run_duration, abs_tol=1e-6):
        raise ValueError(f'{path.name} : la dernière fixation ne termine pas à run_duration_sec')
    return trials
