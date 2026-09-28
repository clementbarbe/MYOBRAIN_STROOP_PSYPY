"""Output filenames must be unique and predictable."""

from __future__ import annotations

import pytest

from config.settings import ExperimentSettings


@pytest.fixture
def settings(tmp_path):
    return ExperimentSettings(participant_id='01', session='01',
                              data_root=tmp_path)


def test_design_id_in_name(settings):
    n1 = settings.base_name('stroop', 1)
    n3 = settings.base_name('stroop', 3)
    assert 'design-1' in n1 and 'design-3' in n3
    assert n1 != n3


def test_first_run_is_01(settings):
    assert settings.resolve_run('stroop', 1) == '01'


def test_run_increments(settings):
    d = settings.task_dir('stroop')
    d.mkdir(parents=True)
    (d / f"{settings.base_name('stroop', 1, '01')}_events.tsv").touch()
    assert settings.resolve_run('stroop', 1) == '02'


def test_designs_have_independent_run_counters(settings):
    d = settings.task_dir('stroop')
    d.mkdir(parents=True)
    (d / f"{settings.base_name('stroop', 1, '01')}_events.tsv").touch()
    assert settings.resolve_run('stroop', 1) == '02'
    assert settings.resolve_run('stroop', 3) == '01'


def test_tasks_have_independent_run_counters(settings):
    d = settings.task_dir('stroop')
    d.mkdir(parents=True)
    (d / f"{settings.base_name('stroop', 1, '01')}_events.tsv").touch()
    assert settings.resolve_run('nback', 1) == '01'


def test_existing_run_is_never_reused(settings):
    d = settings.task_dir('stroop')
    d.mkdir(parents=True)
    for n in ('01', '02', '03'):
        (d / f"{settings.base_name('stroop', 2, n)}_events.tsv").touch()
    assert settings.resolve_run('stroop', 2) == '04'