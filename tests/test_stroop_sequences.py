"""
Offline verification of every Stroop design.

Runs the real generation code with mocked PsychoPy objects, so the
balance and ordering guarantees can be checked without a display.

    pytest tests/test_stroop_sequences.py -v
"""

from __future__ import annotations

import random
from collections import Counter
from unittest.mock import MagicMock

import pytest

from config.tasks_config import load_task_config
from tasks.utils.pools import max_run_length

DESIGNS = [1, 2, 3, 4]
N_REPEATS = 30          # different seeds per design


def build_task(design_id: int, seed: int):
    """Instantiate StroopTask with every PsychoPy dependency mocked."""
    from tasks.stroop import StroopTask

    task = StroopTask.__new__(StroopTask)          # bypass __init__
    task.task_config = load_task_config('stroop')
    task.design_id = design_id
    task.design = task.task_config['designs'][design_id]
    task.block_sequence = [dict(b) for b in task.design['blocks']]
    task._rng = random.Random(seed)
    task.seed = seed
    task.logger = MagicMock()
    task.settings = MagicMock(mode='pc')
    task.win = MagicMock()

    cfg = task.task_config
    task._color_rgb = cfg['colors']
    task._ink_colors = list(cfg['colors'].keys())
    task._color_words = cfg['color_words']
    task._neutral_words = list(cfg['neutral_words'])
    task._inc_pairs = [(p['word'], p['ink']) for p in cfg['incongruent_pairs']]
    return task


def flatten(blocks):
    return [t for b in blocks for t in b]


# ═════════════════════════════════════════════════════════════════════
# Structure
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_trial_count_matches_design(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        blocks = task.build_all_trials()
        expected = sum(b['n_trials'] for b in task.block_sequence)
        assert len(flatten(blocks)) == expected, \
            f"design {design_id} seed {seed}"


@pytest.mark.parametrize('design_id', DESIGNS)
def test_block_sizes_match_design(design_id):
    task = build_task(design_id, 0)
    blocks = task.build_all_trials()
    for b, bdef in zip(blocks, task.block_sequence):
        assert len(b) == bdef['n_trials']


# ═════════════════════════════════════════════════════════════════════
# Balance
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_trial_types_balanced(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        c = Counter(t[2] for t in flatten(task.build_all_trials()))
        assert max(c.values()) - min(c.values()) <= 1, \
            f"design {design_id} seed {seed}: {dict(c)}"


@pytest.mark.parametrize('design_id', DESIGNS)
def test_ink_colors_balanced(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        c = Counter(t[1] for t in flatten(task.build_all_trials()))
        assert len(c) == 3
        assert max(c.values()) - min(c.values()) <= 1, \
            f"design {design_id} seed {seed}: {dict(c)}"


@pytest.mark.parametrize('design_id', DESIGNS)
def test_incongruent_pairs_balanced(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        inc = [t for t in flatten(task.build_all_trials())
               if t[2] == 'incongruent']
        c = Counter((t[0], t[1]) for t in inc)
        assert len(c) == 6, f"only {len(c)} pairs used"
        assert max(c.values()) - min(c.values()) <= 1, dict(c)


@pytest.mark.parametrize('design_id', DESIGNS)
def test_neutral_words_balanced(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        neu = [t for t in flatten(task.build_all_trials())
               if t[2] == 'neutral']
        c = Counter(t[0] for t in neu)
        assert max(c.values()) - min(c.values()) <= 1, dict(c)


# ═════════════════════════════════════════════════════════════════════
# Semantic correctness
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_condition_definitions(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        colour_words = set(task._color_words.values())
        for word, ink, ttype, _ in flatten(task.build_all_trials()):
            if ttype == 'congruent':
                assert word == task._color_words[ink]
            elif ttype == 'incongruent':
                assert word in colour_words
                assert word != task._color_words[ink]
            else:
                assert word not in colour_words


# ═════════════════════════════════════════════════════════════════════
# Ordering constraints
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_no_more_than_two_same_ink(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        for i, b in enumerate(task.build_all_trials()):
            run = max_run_length([t[1] for t in b])
            assert run <= 2, f"design {design_id} seed {seed} block {i}: {run}"


@pytest.mark.parametrize('design_id', DESIGNS)
def test_no_more_than_two_same_word(design_id):
    for seed in range(N_REPEATS):
        task = build_task(design_id, seed)
        for i, b in enumerate(task.build_all_trials()):
            run = max_run_length([t[0] for t in b])
            assert run <= 2, f"design {design_id} seed {seed} block {i}: {run}"


def test_event_design_never_repeats_type():
    for seed in range(N_REPEATS):
        task = build_task(4, seed)
        types = [t[2] for t in flatten(task.build_all_trials())]
        assert max_run_length(types) == 1, f"seed {seed}"


# ═════════════════════════════════════════════════════════════════════
# Timing
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_duration_under_six_thirty(design_id):
    task = build_task(design_id, 0)
    d = task.design
    trials = flatten(task.build_all_trials())

    per_trial = sum(t[3] for t in trials) \
        + len(trials) * (d['fixation_duration'] + d['stim_duration'])
    n_rest = len(task.block_sequence) + 1
    total = per_trial + n_rest * d['rest_duration'] \
        + len(task.block_sequence) * (d.get('instruction_duration', 0)
                                      + d.get('pre_block_fixation', 0))

    assert total <= 390, f"design {design_id}: {total:.0f}s > 390s"
    print(f"  design {design_id}: {total:.0f}s ({total / 60:.2f} min)")


def test_event_iti_distribution():
    task = build_task(4, 0)
    itis = [t[3] for t in flatten(task.build_all_trials())]
    d = task.design
    assert min(itis) >= d['iti_min']
    assert max(itis) <= d['iti_max']
    mean = sum(itis) / len(itis)
    target = (d['iti_min'] + d['iti_max']) / 2
    assert abs(mean - target) < 0.05, f"mean ITI {mean:.3f} vs {target}"


# ═════════════════════════════════════════════════════════════════════
# Reproducibility
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('design_id', DESIGNS)
def test_same_seed_same_sequence(design_id):
    a = flatten(build_task(design_id, 12345).build_all_trials())
    b = flatten(build_task(design_id, 12345).build_all_trials())
    assert a == b


@pytest.mark.parametrize('design_id', DESIGNS)
def test_different_seed_different_sequence(design_id):
    a = flatten(build_task(design_id, 1).build_all_trials())
    b = flatten(build_task(design_id, 2).build_all_trials())
    assert a != b