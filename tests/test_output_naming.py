"""The four acquisitions share a subject, but cannot overwrite each other."""

import pytest

from config.settings import ExperimentSettings
from config.stroop_designs import DESIGNS, run_for_design


@pytest.fixture
def settings(tmp_path):
    return ExperimentSettings(participant_id='1', data_root=tmp_path)


def touch_output(settings, design, run='01', suffix='events.tsv'):
    directory = settings.task_dir('stroop')
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f'{settings.base_name("stroop", design, run)}_{suffix}').touch()


@pytest.mark.parametrize('design', DESIGNS)
def test_run_does_not_depend_on_subject_number(settings, design):
    settings.participant_id = '005'
    run = f'{run_for_design(design):02d}'
    assert settings.resolve_run('stroop', design) == run
    assert f'design-{design}_run-{run}' in settings.base_name('stroop', design, run)


@pytest.mark.parametrize('suffix', ['events.tsv', 'events_incremental.tsv', 'design.json'])
def test_existing_acquisition_is_rejected(settings, suffix):
    touch_output(settings, 'E2_A', suffix=suffix)
    with pytest.raises(FileExistsError):
        settings.resolve_run('stroop', 'E2_A')


def test_four_runs_can_all_be_recorded_for_same_subject(settings):
    for design in DESIGNS:
        run = settings.resolve_run('stroop', design)
        touch_output(settings, design, run)
    for design in DESIGNS:
        with pytest.raises(FileExistsError):
            settings.resolve_run('stroop', design)


def test_training_does_not_block_pilot_runs(settings):
    touch_output(settings, 'training')
    assert settings.resolve_run('stroop', 'E2_A') == '01'
    assert settings.resolve_run('stroop', 'training') == '02'


def test_run_does_not_block_training(settings):
    touch_output(settings, 'E2_A')
    assert settings.resolve_run('stroop', 'training') == '01'


def test_leading_zeros_identify_same_subject(tmp_path):
    first = ExperimentSettings(participant_id='5', data_root=tmp_path)
    padded = ExperimentSettings(participant_id='005', data_root=tmp_path)
    assert first.participant_id == padded.participant_id == '005'
    touch_output(first, 'E2_A')
    with pytest.raises(FileExistsError):
        padded.resolve_run('stroop', 'E2_A')
