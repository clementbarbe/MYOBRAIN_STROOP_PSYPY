"""
BIDS events.json sidecar.

Documents every column of the events.tsv, so the file can be read
without consulting the code. Written automatically after each run.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# ── Columns common to every task ─────────────────────────────────────

_COMMON: dict[str, dict] = {
    'subject': {
        'Description': 'Participant identifier as entered in the launcher.',
    },
    'run': {
        'Description': (
            'Pilot acquisition: 01=E2_A, 02=E3_A, 03=E3_B, 04=E2_B. '
            'Practice recordings have independent numbering.'
        ),
    },
    'trial': {
        'Description': 'Trial index over the whole run, starting at 1.',
    },
    'task': {
        'Description': 'Task name.',
    },
    'onset': {
        'LongName': 'Stimulus onset',
        'Description': (
            'Time of the stimulus window flip, in seconds since the first '
            'retained functional-volume trigger (after configured discarded triggers). The clock is reset when '
            'that pulse is received, so this value is the time elapsed '
            'since the start of the functional acquisition. In practice, '
            'zero is the start of the training schedule (no scanner pulse). '
            'See the _scantrig.json sidecar for the measured TR and for '
            'a check that the first pulse was not a dummy scan.'
        ),
        'Units': 's',
    },
    'duration': {
        'Description': 'Measured stimulus display duration, from onset flip to offset flip.',
        'Units': 's',
    },
    'condition': {
        'Description': 'Experimental condition of the trial.',
    },
    'stimulus': {
        'Description': 'Compact identifier of the presented stimulus.',
    },
    'correct_response': {
        'Description': 'Key the participant should have pressed.',
    },
    'response': {
        'Description': (
            'First valid key press by keyboard timestamp in the response window. '
            'Exact timestamp ties retain keyboard arrival order. '
            'Later presses do not change the scored response. n/a if absent.'
        ),
    },
    'n_responses': {
        'Description': 'Number of valid key-down events in the response window, including repeats.',
    },
    'multiple_responses': {
        'Description': '1 if more than one valid key-down event was recorded; otherwise 0.',
    },
    'multiple_buttons': {
        'Description': '1 if at least two distinct response keys were pressed in the window; otherwise 0.',
    },
    'response_keys': {
        'Description': 'All accepted response keys in detection order (timestamp order within each poll), separated by |; n/a if absent.',
    },
    'response_RTs': {
        'Description': 'Latency of each event in response_keys, in seconds since stimulus onset, separated by |; n/a if absent.',
        'Units': 's',
    },
    'correct': {
        'Description': 'Response matched the required one.',
        'Levels': {'1': 'correct', '0': 'incorrect or no response'},
    },
    'RT': {
        'LongName': 'Reaction time',
        'Description': (
            'Time from stimulus onset to the key press, in seconds. '
            'n/a when no response was recorded, so omissions never '
            'contaminate an average. Measured against the experiment '
            'clock using the keyboard event timestamp. Only presses during '
            'the stimulus response window are accepted.'
        ),
        'Units': 's',
    },
    'block': {
        'Description': 'Block index within the run, starting at 1.',
    },
    'trial_in_block': {
        'Description': 'Trial index within its block, starting at 1.',
    },
    'block_idx': {'Description': 'Zero-based sequence index (legacy alias).'},
    'trial_idx': {'Description': 'Zero-based trial index within the sequence (legacy alias).'},
    'design_id': {
        'Description': 'Fixed pilot schedule: E2_A, E3_A, E3_B, E2_B, or training.',
    },
    'design_name': {
        'Description': 'Human-readable design name.',
    },
    'paradigm': {
        'Description': 'block or event.',
    },
    'scanner': {
        'Description': 'Scanner site profile used.',
    },
    'mode': {
        'Description': 'fmri or pc.',
    },
    'trigger_wall_time': {
        'Description': (
            'Wall-clock time of the first scanner trigger, for alignment '
            'with devices that have their own clock.'
        ),
    },
    'task_time': {
        'Description': (
            'Experiment clock at the moment the row was written.'
        ),
        'Units': 's',
    },
    'wall_time': {
        'Description': 'Wall-clock time the row was written.',
    },
    'responded': {
        'Description': 'A response was recorded.',
        'Levels': {'1': 'yes', '0': 'no'},
    },
    'is_error': {
        'Description': 'A response was given but it was wrong.',
        'Levels': {'1': 'commission error', '0': 'not an error'},
    },
    'is_miss': {
        'Description': 'No response was given.',
        'Levels': {'1': 'omission', '0': 'responded'},
    },
    'fixation_onset': {
        'Description': 'Fixation onset, seconds since the trigger.',
        'Units': 's',
    },
    'iti_onset': {
        'Description': 'Inter-trial interval onset, seconds since the trigger.',
        'Units': 's',
    },
    'fixation_duration': {'Description': 'Fixation duration.', 'Units': 's'},
    'stim_duration': {'Description': 'Stimulus duration.', 'Units': 's'},
    'iti_duration': {'Description': 'Inter-trial interval.', 'Units': 's'},
    'trial_type': {
        'Description': 'Alias of condition, kept for BIDS compatibility.',
    },
    'is_correct': {'Description': 'Alias of correct.'},
    'rt': {'Description': 'Alias of RT.', 'Units': 's'},
    'response_key': {'Description': 'Alias of response.'},
    'correct_key': {'Description': 'Alias of correct_response.'},
}

# ── Task-specific columns ────────────────────────────────────────────

_BY_TASK: dict[str, dict] = {
    'stroop': {
        'condition': {
            'Description': 'Relation between the word and its ink colour.',
            'Levels': {
                'congruent': 'colour word printed in the matching ink',
                'incongruent': 'colour word printed in a conflicting ink',
                'neutral': 'non-colour word printed in an ink',
                'color_mapping': 'training only: a coloured patch, no word',
            },
        },
        'stimulus': {
            'Description': (
                'WORD:ink (PATCH:ink for training patches), for example ROUGE:bleu for the word ROUGE '
                'printed in blue. The two parts are also available '
                'separately as word and ink_color.'
            ),
        },
        'word': {'Description': 'Word displayed on screen.'},
        'ink_color': {
            'Description': 'Ink colour, the dimension to report.',
            'Levels': {'rouge': 'red', 'bleu': 'blue', 'vert': 'green'},
        },
        'correct_color': {'Description': 'Colour name of the required response.'},
        'response_color': {'Description': 'Colour name of the key pressed.'},
        'variant': {'Description': 'Pilot design identifier, or training.'},
        'training': {'Description': '1 for practice, 0 for an acquisition run.'},
        'training_phase': {'Description': 'guided_mapping, memory_mapping, stroop, or acquisition.'},
        'stimulus_kind': {'Description': 'patch (training only) or word.'},
        'mapping_visible': {'Description': '1 when the response-box mapping is displayed (guided training only).'},
        'feedback_enabled': {'Description': '1 when correctness feedback follows this trial (mapping training only).'},
        'source_trial': {'Description': 'Original trial index from the subject design for Stroop familiarisation.'},
        'temporal_window': {'Description': 'Temporal window index from the source TSV.'},
        'is_long_null': {'Description': 'Long null interval flag from the source TSV.'},
        'previous_condition': {'Description': 'Previous trial condition, or START.'},
        'transition': {'Description': 'Previous condition -> current condition.'},
        'planned_onset': {'Description': 'Stimulus onset in the source schedule.', 'Units': 's'},
        'planned_duration': {'Description': 'Stimulus duration in the source schedule.', 'Units': 's'},
        'stimulus_offset': {'Description': 'Measured stimulus offset flip, since the retained-volume trigger.', 'Units': 's'},
        'response_window_sec': {'Description': 'Response window specified by the TSV; the word remains visible after a response.', 'Units': 's'},
        'response_deadline': {'Description': 'Actual closing time of the response window, since the trigger.', 'Units': 's'},
        'planned_response_deadline': {'Description': 'Response deadline in the reference TSV.', 'Units': 's'},
        'planned_stimulus_offset': {'Description': 'Stimulus offset in the reference TSV.', 'Units': 's'},
        'planned_not_acquired': {'Description': '0 for these acquired events; reference TSV files use 1.'},
        'source_design': {'Description': 'Full design identifier copied from the reference TSV.'},
        'source_seed': {'Description': 'Seed recorded in the optimized reference TSV; never used to regenerate it at runtime.'},
        'source_phase': {'Description': 'Phase index in the reference TSV.'},
        'source_block': {'Description': 'Block annotation in the reference TSV, independent of runtime sequence indexing.'},
        'stimulus_set': {'Description': 'Stimulus-set label from the reference TSV.'},
        'context': {'Description': 'Context label from the reference TSV.'},
        'run_duration_sec': {'Description': 'Planned task duration, including initial and final fixation; excludes volume padding.', 'Units': 's'},
        'blank_after_response': {'Description': '0: a response does not end the stimulus presentation early.', 'Units': 's'},
        'onset_error': {'Description': 'Actual onset minus planned onset.', 'Units': 's'},
        'planned_fixation_onset': {'Description': 'Fixation onset in the source schedule.', 'Units': 's'},
        'fixation_after_sec': {'Description': 'Fixation duration following this stimulus in the TSV.', 'Units': 's'},

    },

}


def write_events_sidecar(events_path: Path, task_name: str,
                         logger=None) -> Path | None:
    """
    Write the events.json next to an events.tsv.

    Only the columns actually present in the file are documented, and a
    warning is logged for any column with no description, so the sidecar
    cannot silently fall behind the code.

    Args:
        events_path: path to the *_events.tsv
        task_name:   task key used to pick the specific descriptions
        logger:      optional ExperimentLogger

    Returns:
        Path to the JSON written, or None on failure.
    """
    events_path = Path(events_path)
    try:
        with open(events_path, 'r', encoding='utf-8') as f:
            header = next(csv.reader(f, delimiter='\t'))
    except Exception as e:
        if logger:
            logger.warn(f"Cannot read header of {events_path.name}: {e}")
        return None

    known = dict(_COMMON)
    known.update(_BY_TASK.get(task_name, {}))

    payload, undocumented = {}, []
    for col in header:
        if col in known:
            payload[col] = known[col]
        else:
            payload[col] = {'Description': 'Not documented.'}
            undocumented.append(col)

    json_path = events_path.with_suffix('.json')
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        if logger:
            logger.ok(f"Events sidecar: {json_path.name}")
            if undocumented:
                logger.warn(f"Undocumented columns: {undocumented}")
        return json_path
    except Exception as e:
        if logger:
            logger.warn(f"Cannot write {json_path.name}: {e}")
        return None
