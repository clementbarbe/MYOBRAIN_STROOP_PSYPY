"""A mapping edit must not silently discard presses or collide with the trigger."""

from copy import deepcopy

import pytest

from config.input_keys import response_keys
from config.tasks_config import load_task_config


def test_numeric_keys_are_supported_when_quoted():
    cfg = load_task_config()
    cfg['response_keys_fmri'] = {'rouge': '1', 'bleu': '2', 'vert': '3'}
    assert response_keys(cfg, 'fmri', 't') == {'rouge': '1', 'bleu': '2', 'vert': '3'}


@pytest.mark.parametrize('mapping', [
    {'rouge': 'b', 'bleu': 'b', 'vert': 'g'},
    {'rouge': 't', 'bleu': 'y', 'vert': 'g'},
    {'rouge': 'escape', 'bleu': 'y', 'vert': 'g'},
    {'rouge': 's', 'bleu': 'y', 'vert': 'g'},
    {'rouge': 1, 'bleu': 2, 'vert': 3},
    {'rouge': '', 'bleu': 'y', 'vert': 'g'},
    {'rouge': 'B', 'bleu': 'y', 'vert': 'g'},
])
def test_bad_mapping_is_rejected(mapping):
    cfg = load_task_config()
    cfg['response_keys_fmri'] = mapping
    with pytest.raises(ValueError):
        response_keys(cfg, 'fmri', 't')
