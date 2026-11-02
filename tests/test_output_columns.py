"""
The ten canonical columns must be present and consistent.

    pytest tests/test_output_columns.py -v
"""

from __future__ import annotations

import csv
from unittest.mock import MagicMock

import pytest

from dataio.data_writer import DataWriter, NA

REQUIRED = ['subject', 'run', 'trial', 'condition', 'onset',
            'stimulus', 'correct_response', 'response', 'correct', 'RT']


@pytest.fixture
def stroop_record():
    """A record shaped like the one Stroop actually writes."""
    return {
        'subject': '001', 'run': '01',
        'trial': 1, 'task': 'stroop',
        'design_id': 'A', 'design_name': 'Stroop A',
        'paradigm': 'event', 'scanner': 'pc', 'mode': 'pc',
        'block': 1, 'trial_in_block': 1, 'block_idx': 0, 'trial_idx': 0,
        'trigger_wall_time': '2026-01-01_10:00:00.000000',
        'task_time': 7.6, 'wall_time': '10:00:07.600',
        'onset': 7.014, 'duration': 1.2,
        'condition': 'neutral', 'stimulus': 'CAUSE:bleu',
        'correct_response': 'down', 'response': 'down',
        'correct': 1, 'RT': 0.6231,
        'word': 'CAUSE', 'ink_color': 'bleu',
        'responded': 1, 'is_error': 0, 'is_miss': 0,
    }


# ── Presence and order ───────────────────────────────────────────────

def test_all_required_columns_present(tmp_path, stroop_record):
    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(stroop_record)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        header = next(csv.reader(f, delimiter='\t'))

    missing = [c for c in REQUIRED if c not in header]
    assert not missing, f"missing: {missing}"


def test_canonical_columns_come_first(tmp_path, stroop_record):
    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(stroop_record)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        header = next(csv.reader(f, delimiter='\t'))

    assert header[:10] == REQUIRED


def test_values_round_trip(tmp_path, stroop_record):
    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(stroop_record)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        row = next(csv.DictReader(f, delimiter='\t'))

    assert row['subject'] == '001'
    assert row['run'] == '01'
    assert row['trial'] == '1'
    assert row['condition'] == 'neutral'
    assert float(row['onset']) == pytest.approx(7.014)
    assert row['stimulus'] == 'CAUSE:bleu'
    assert row['correct_response'] == 'down'
    assert row['response'] == 'down'
    assert row['correct'] == '1'
    assert float(row['RT']) == pytest.approx(0.6231)


# ── Missing values ───────────────────────────────────────────────────

def test_omission_writes_na_not_minus_one(tmp_path, stroop_record):
    rec = dict(stroop_record)
    rec.update({'response': None, 'RT': None, 'correct': 0,
                'responded': 0, 'is_miss': 1})

    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(rec)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        row = next(csv.DictReader(f, delimiter='\t'))

    assert row['RT'] == NA
    assert row['response'] == NA
    assert row['correct'] == '0'
    assert '-1' not in (row['RT'], row['response'])


# ── Internal consistency ─────────────────────────────────────────────

def test_correct_flag_agrees_with_responses(tmp_path, stroop_record):
    rows = []
    for resp, want, flag in [('down', 'down', 1),
                             ('left', 'down', 0),
                             (None, 'down', 0)]:
        r = dict(stroop_record)
        r.update({'response': resp, 'correct_response': want, 'correct': flag,
                  'RT': 0.5 if resp else None})
        rows.append(r)

    w = DataWriter(tmp_path, 'test', MagicMock())
    for i, r in enumerate(rows, 1):
        r['trial'] = i
        w.write_trial(r)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            if row['response'] == NA:
                assert row['correct'] == '0'
                assert row['RT'] == NA
            else:
                expected = '1' if row['response'] == row['correct_response'] else '0'
                assert row['correct'] == expected


def test_trial_increments_across_rows(tmp_path, stroop_record):
    w = DataWriter(tmp_path, 'test', MagicMock())
    for i in range(1, 21):
        r = dict(stroop_record)
        r['trial'] = i
        r['onset'] = 7.0 + 2.0 * (i - 1)
        w.write_trial(r)
    out = w.save_final()

    with open(out, encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))

    assert [int(r['trial']) for r in rows] == list(range(1, 21))
    onsets = [float(r['onset']) for r in rows]
    assert all(b > a for a, b in zip(onsets, onsets[1:]))


# ── Sidecar ──────────────────────────────────────────────────────────

def test_events_sidecar_documents_every_column(tmp_path, stroop_record):
    import json
    from dataio.events_sidecar import write_events_sidecar

    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(stroop_record)
    out = w.save_final()

    js = write_events_sidecar(out, 'stroop', MagicMock())
    assert js is not None

    payload = json.loads(js.read_text(encoding='utf-8'))
    with open(out, encoding='utf-8') as f:
        header = next(csv.reader(f, delimiter='\t'))

    assert set(payload) == set(header)
    for col in REQUIRED:
        assert 'Description' in payload[col]
        assert payload[col]['Description'] != 'Not documented.'


def test_onset_documentation_mentions_the_trigger(tmp_path, stroop_record):
    import json
    from dataio.events_sidecar import write_events_sidecar

    w = DataWriter(tmp_path, 'test', MagicMock())
    w.write_trial(stroop_record)
    out = w.save_final()
    js = write_events_sidecar(out, 'stroop', MagicMock())

    desc = json.loads(js.read_text(encoding='utf-8'))['onset']
    assert desc['Units'] == 's'
    assert 'trigger' in desc['Description'].lower()