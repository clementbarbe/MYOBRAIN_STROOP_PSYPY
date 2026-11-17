"""Only the Stroop task and its current schedules are available."""

import pytest

from tasks.registry import get_task, list_tasks
from config.tasks_config import load_task_config


def test_only_stroop_registered():
    assert list_tasks() == ['stroop']
    assert get_task('stroop') is not None
    assert get_task('nonexistent_task') is None


def test_stroop_configuration():
    cfg = load_task_config('stroop')
    assert set(cfg['designs']) == {'E2_A', 'E3_A', 'E3_B', 'E2_B', 'training'}
    assert cfg['response_keys_fmri'] == {'rouge': 'b', 'bleu': 'y', 'vert': 'g'}


def test_invalid_config_does_not_fall_back(tmp_path):
    (tmp_path / 'stroop.yaml').write_text('designs: [broken', encoding='utf-8')
    with pytest.raises(Exception):
        load_task_config('stroop', tmp_path)
