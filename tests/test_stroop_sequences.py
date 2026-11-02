"""Exact preservation of the provided TSV stimuli and absolute timings."""

import csv
from collections import Counter

import pytest

from config.constants import PROJECT_ROOT
from config.stroop_designs import design_for_subject, load_design
from config.stroop_training import training_trials


@pytest.mark.parametrize('subject,variant', [(1, 'A'), (2, 'B'), (3, 'C'), (4, 'D'),
                                        (5, 'A'), (6, 'B'), (7, 'C'), (8, 'D'),
                                        (9, 'A'), ('005', 'A'), (100, 'D')])
def test_subject_cycle(subject, variant):
    assert design_for_subject(subject) == variant


@pytest.mark.parametrize('subject', [0, -1, '', 'x', '1.5', 1.5, True, None])
def test_invalid_subject(subject):
    with pytest.raises(ValueError):
        design_for_subject(subject)


@pytest.mark.parametrize('variant', list('ABCD'))
def test_fixed_schedule_matches_every_source_row(variant):
    trials = load_design(variant)
    with (PROJECT_ROOT / f'stroop_design_{variant}.tsv').open() as stream:
        source = list(csv.DictReader(stream, delimiter='\t'))
    assert len(trials) == 75
    for actual, original in zip(trials, source):
        for key in original:
            expected = original[key]
            if isinstance(actual[key], bool):
                assert actual[key] == (expected == 'True')
            elif isinstance(actual[key], (int, float)):
                assert actual[key] == float(expected)
            else:
                assert actual[key] == expected
    assert Counter(row['condition'] for row in trials) == {
        'neutral': 15, 'congruent': 30, 'incongruent': 30}
    assert trials[0]['onset'] == 10.0
    assert trials[-1]['fixation_onset'] + trials[-1]['fixation_after_sec'] == pytest.approx(422.88)


@pytest.mark.parametrize('column,value', [('variant', 'B'), ('correct_response', 'x'),
    ('onset', 'NaN'), ('duration', '-1'), ('fixation_after_sec', '20'),
    ('word', 'WRONG'), ('trial', '2'), ('condition', 'other')])
def test_corrupt_design_is_rejected(tmp_path, column, value):
    with (PROJECT_ROOT / 'stroop_design_A.tsv').open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        rows, fields = list(reader), reader.fieldnames
    rows[0][column] = value
    with (tmp_path / 'stroop_design_A.tsv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        load_design('A', tmp_path)


def test_missing_design_does_not_generate_another(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_design('A', tmp_path)


@pytest.mark.parametrize('variant', list('ABCD'))
def test_progressive_training_uses_balanced_patches_and_real_format_stroop(variant):
    trials = training_trials(variant)
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
    source = load_design(variant)
    for row in stroop:
        original = source[row['source_trial'] - 1]
        for field in ('word', 'ink_color', 'condition', 'duration', 'fixation_after_sec'):
            assert row[field] == original[field]
        assert not row['show_mapping'] and not row['show_feedback']
    assert 175 <= trials[-1]['fixation_onset'] + trials[-1]['fixation_after_sec'] <= 200


def test_successive_inclusions_are_balanced_in_groups_of_four():
    for start in (1, 5, 9, 101):
        assert Counter(design_for_subject(subject) for subject in range(start, start + 4)) == {
            'A': 1, 'B': 1, 'C': 1, 'D': 1}
