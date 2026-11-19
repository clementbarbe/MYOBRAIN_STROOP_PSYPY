"""Preserve every supplied pilot event, with no runtime resampling."""

import csv
import json
from collections import Counter

import pytest

from config.stroop_designs import (DESIGNS, design_for_run, run_for_design, design_path,
                                   load_design, acquisition_timing)
from config.stroop_training import training_trials


@pytest.mark.parametrize('run,design', list(enumerate(DESIGNS, 1)))
def test_run_order(run, design):
    assert design_for_run(run) == design
    assert design_for_run(f'{run:02d}') == design
    assert run_for_design(design) == run


@pytest.mark.parametrize('run', [0, -1, 5, '', 'x', 1.5, True, None])
def test_invalid_run(run):
    with pytest.raises(ValueError):
        design_for_run(run)


@pytest.mark.parametrize('design', DESIGNS)
def test_fixed_schedule_matches_every_source_row(design):
    trials = load_design(design)
    with design_path(design).open() as stream:
        source = list(csv.DictReader(stream, delimiter='\t'))
    n = 150 if design.startswith('E2') else 120
    assert len(trials) == n
    for actual, original in zip(trials, source):
        for key, expected in original.items():
            if isinstance(actual[key], (int, float)):
                assert actual[key] == float(expected)
            else:
                assert actual[key] == expected
    assert Counter(row['condition'] for row in trials) == {
        'neutral': n // 5, 'congruent': 2 * n // 5, 'incongruent': 2 * n // 5}
    assert trials[0]['onset'] == 10.0
    assert all(row['duration'] == row['response_window_sec'] == 2.0 for row in trials)
    assert trials[-1]['fixation_after_sec'] == 15.0
    timing = acquisition_timing(trials)
    assert timing['planned_duration'] == 520.0
    assert timing['acquisition_duration'] == 520.29
    assert timing['n_volumes'] == 423 and timing['padding_duration'] == .29


@pytest.mark.parametrize('column,value', [
    ('design', 'run-02_E3_A'), ('correct_response', 'x'), ('onset', 'NaN'),
    ('duration', '-1'), ('fixation_after_sec', '20'), ('word', 'WRONG'),
    ('trial', '2'), ('condition', 'other'), ('response_deadline', '15'),
    ('response_window', '1.2'), ('stimulus_offset', '13'), ('cycle_duration', '50'),
    ('run_duration_sec', '600'), ('planned_not_acquired', '0'), ('blank_after_response', '1'),
])
def test_corrupt_design_is_rejected(tmp_path, column, value):
    with design_path('E2_A').open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        rows, fields = list(reader), reader.fieldnames
    rows[0][column] = value
    with design_path('E2_A', tmp_path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        load_design('E2_A', tmp_path)


def test_missing_design_does_not_generate_another(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_design('E2_A', tmp_path)


@pytest.mark.parametrize('design', DESIGNS)
def test_progressive_training_uses_balanced_patches_and_real_format_stroop(design):
    trials = training_trials(design)
    assert len(trials) == 45
    for phase in ('guided_mapping', 'memory_mapping'):
        rows = [row for row in trials if row['training_phase'] == phase]
        assert len(rows) == 18
        assert Counter(row['ink_color'] for row in rows) == {'rouge': 6, 'bleu': 6, 'vert': 6}
        assert all(row['word'] == '' and row['stimulus_kind'] == 'patch' for row in rows)
        assert all(row['show_feedback'] for row in rows)
        assert all(row['show_mapping'] == (phase == 'guided_mapping') for row in rows)
    stroop = [row for row in trials if row['training_phase'] == 'stroop']
    assert Counter(row['condition'] for row in stroop) == {'neutral': 3, 'congruent': 3, 'incongruent': 3}
    source = load_design(design)
    for row in stroop:
        original = source[row['source_trial'] - 1]
        for field in ('word', 'ink_color', 'condition', 'duration', 'fixation_after_sec', 'response_window_sec'):
            assert row[field] == original[field]
        assert row['response_deadline'] == pytest.approx(row['onset'] + 2.0)
        assert not row['show_mapping'] and not row['show_feedback']


def test_padding_does_not_add_an_extra_volume_to_an_exact_tr_boundary():
    rows = load_design('E2_A')
    for row in rows:
        row['run_duration_sec'] = 492.0  # 400 * 1.23
    timing = acquisition_timing(rows)
    assert timing['n_volumes'] == 400 and timing['padding_duration'] == 0


@pytest.mark.parametrize('design', DESIGNS)
def test_neutral_expansion_preserves_every_other_source_cell(design):
    path = design_path(design)
    versions = path.parent / 'design_versions'
    manifest = json.loads((versions / '2026-11-19_neutral_expansion.json').read_text())
    previous = versions / '2026-11-19_before_neutral_expansion' / path.name
    with path.open() as stream, previous.open() as old_stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
        old_rows = list(csv.DictReader(old_stream, delimiter='\t'))
    assert len(rows) == len(old_rows)
    for row, old in zip(rows, old_rows):
        for field in row:
            if old['condition'] != 'neutral' or field not in ('word', 'stimulus'):
                assert row[field] == old[field]
    neutral = [row for row in rows if row['condition'] == 'neutral']
    counts = Counter(row['word'] for row in neutral)
    assert set(counts) == set(manifest['neutral_words']) and len(counts) == 12
    assert max(counts.values()) - min(counts.values()) <= 1
    assert set(Counter(row['ink_color'] for row in neutral).values()) == {len(neutral) // 3}
    assert max(Counter((row['word'], row['ink_color']) for row in neutral).values()) == 1
    assert all(a['word'] != b['word'] for a, b in zip(neutral, neutral[1:]))
