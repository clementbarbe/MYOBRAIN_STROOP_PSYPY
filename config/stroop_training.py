"""Practical three-minute familiarisation schedule and acquisition checks."""

from collections import Counter
from copy import deepcopy
import random

from config.stroop_designs import COLOR_WORDS, FMRI_KEYS, load_design

DISCOVERY_DURATION = 20.0
PHASE_INSTRUCTION_DURATION = 4.0
PHASES = ('guided_mapping', 'memory_mapping', 'stroop')
TRIALS_PER_MAPPING_PHASE = 18
STROOP_TRIALS = 9
TRAINING_TRIALS = TRIALS_PER_MAPPING_PHASE * 2 + STROOP_TRIALS


def training_trials(variant: str = 'A') -> list[dict]:
    """20 s discovery, two 54 s mapping stages, then real-format Stroop."""
    trials = []
    elapsed = DISCOVERY_DURATION
    rng = random.Random(731)
    for phase in PHASES:
        instruction_onset = elapsed
        elapsed += PHASE_INSTRUCTION_DURATION
        if phase == 'stroop':
            # Three examples of each condition, taken from the subject's design.
            # Keep each example's word, ink, stimulus duration and following fixation.
            selected = []
            used = Counter()
            for source in load_design(variant):
                if used[source['condition']] < 3:
                    selected.append(deepcopy(source))
                    used[source['condition']] += 1
                if len(selected) == STROOP_TRIALS:
                    break
            if len(selected) != STROOP_TRIALS:
                raise ValueError('Le design ne contient pas assez d’exemples Stroop.')
        else:
            inks = list(COLOR_WORDS) * (TRIALS_PER_MAPPING_PHASE // 3)
            rng.shuffle(inks)
            selected = [{
                'condition': 'color_mapping', 'word': '', 'ink_color': ink,
                'stimulus': f'PATCH:{ink}', 'correct_response': FMRI_KEYS[ink],
                'duration': 2.0, 'fixation_after_sec': 1.0, 'is_long_null': False,
            } for ink in inks]
        for source in selected:
            previous = trials[-1]['condition'] if trials else 'START'
            trial = dict(source)
            trial.update({
                'source_trial': source.get('trial'), 'trial': len(trials) + 1,
                'variant': 'training', 'temporal_window': PHASES.index(phase) + 1,
                'training_phase': phase, 'phase_instruction_onset': instruction_onset,
                'stimulus_kind': 'word' if phase == 'stroop' else 'patch',
                'show_mapping': phase == 'guided_mapping',
                'show_feedback': phase != 'stroop',
                'trial_type': source['condition'], 'onset': round(elapsed, 4),
                'fixation_onset': round(elapsed + source['duration'], 4),
                'previous_condition': previous,
                'transition': f'{previous}->{source["condition"]}',
            })
            trials.append(trial)
            elapsed = trial['fixation_onset'] + trial['fixation_after_sec']
    return trials


def assess_training(records: list[dict], discovery: list[dict],
                    color_to_key: dict, threshold: float = 0.8) -> dict:
    """Operational feedback only; this threshold is a practical setting."""
    phases = {}
    for phase in PHASES:
        rows = [row for row in records if row.get('training_phase') == phase]
        expected = STROOP_TRIALS if phase == 'stroop' else TRIALS_PER_MAPPING_PHASE
        correct = sum(row['correct'] for row in rows)
        by_color = {
            color: {
                'correct': sum(row['correct'] for row in rows if row['ink_color'] == color),
                'total': sum(row['ink_color'] == color for row in rows),
            } for color in COLOR_WORDS
        }
        accuracy = correct / len(rows) if rows else 0.0
        phases[phase] = {
            'n_trials': len(rows), 'expected_trials': expected, 'correct': correct,
            'omissions': sum(not row['responded'] for row in rows),
            'accuracy': accuracy, 'by_color': by_color,
            'passed': (len(rows) == expected and accuracy >= threshold
                       and all(value['correct'] > 0 for value in by_color.values())),
        }
    pressed = {row['key'] for row in discovery}
    checked = all(key in pressed for key in color_to_key.values())
    complete = len(records) == TRAINING_TRIALS
    return {
        'complete': complete, 'accuracy_threshold': threshold,
        'criterion': 'All active buttons checked; >= threshold and at least one correct '
                     'answer per ink in both memory mapping and Stroop stages.',
        'criterion_status': 'Practical pilot setting, not a literature-validated cutoff.',
        'active_buttons_checked': checked, 'discovery_presses': discovery,
        'phases': phases,
        'acquired': complete and checked and phases['memory_mapping']['passed']
                    and phases['stroop']['passed'],
    }
