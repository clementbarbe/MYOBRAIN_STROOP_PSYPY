"""One acquisition per inclusion number; independent training recordings."""

import pytest

from config.settings import ExperimentSettings
from config.stroop_designs import design_for_subject


@pytest.fixture
def settings(tmp_path):
    return ExperimentSettings(participant_id='1', data_root=tmp_path)


def touch_output(settings, variant, run='01', suffix='events.tsv'):
    directory = settings.task_dir('stroop')
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f'{settings.base_name("stroop", variant, run)}_{suffix}').touch()


def test_inclusion_five_gets_design_a_and_single_run(settings):
    settings.participant_id = '005'
    assert settings.resolve_run('stroop', 'A') == '01'
    assert settings.base_name('stroop', 'A') == 'sub-005_task-stroop_design-A_run-01'
    assert settings.subject_dir == settings.data_root / 'sub-005'


@pytest.mark.parametrize('suffix', ['events.tsv', 'events_incremental.tsv', 'design.json'])
def test_existing_acquisition_is_rejected(settings, suffix):
    touch_output(settings, 'A', suffix=suffix)
    with pytest.raises(FileExistsError):
        settings.resolve_run('stroop', 'A')


def test_even_an_old_other_variant_or_run_blocks_another_acquisition(settings):
    touch_output(settings, 'B', '05')
    with pytest.raises(FileExistsError):
        settings.resolve_run('stroop', 'A')


def test_training_does_not_block_task(settings):
    touch_output(settings, 'training')
    assert settings.resolve_run('stroop', 'A') == '01'
    assert settings.resolve_run('stroop', 'training') == '02'


def test_task_does_not_block_training(settings):
    touch_output(settings, 'A')
    assert settings.resolve_run('stroop', 'training') == '01'


def test_subject_design_mismatch_is_rejected(settings):
    with pytest.raises(ValueError):
        settings.resolve_run('stroop', 'D')


@pytest.mark.parametrize('subject', [1, 2, 3, 4, 5, 8, 9, 99, 100, 9999])
def test_design_uses_subject_while_acquisition_run_stays_one(settings, subject):
    settings.participant_id = str(subject)
    settings.run = '99'
    assert settings.resolve_run('stroop', design_for_subject(subject)) == '01'


def test_leading_zeros_identify_same_subject(tmp_path):
    first = ExperimentSettings(participant_id='5', data_root=tmp_path)
    padded = ExperimentSettings(participant_id='005', data_root=tmp_path)
    assert first.participant_id == padded.participant_id == '005'
    touch_output(first, 'A')
    with pytest.raises(FileExistsError):
        padded.resolve_run('stroop', 'A')
