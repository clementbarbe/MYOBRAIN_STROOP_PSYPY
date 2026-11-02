"""An incomplete training or one with unchecked colours cannot pass."""

from config.stroop_designs import FMRI_KEYS
from config.stroop_training import assess_training, training_trials


def completed_records():
    return [dict(trial, correct=1, responded=1) for trial in training_trials()]


def discovery():
    return [{'key': key, 'time': index, 'active': True}
            for index, key in enumerate(FMRI_KEYS.values())]


def test_complete_successful_training_passes():
    report = assess_training(completed_records(), discovery(), FMRI_KEYS)
    assert report['complete'] and report['active_buttons_checked'] and report['acquired']


def test_memory_errors_require_repeat_even_if_guided_phase_was_perfect():
    rows = completed_records()
    memory = [row for row in rows if row['training_phase'] == 'memory_mapping']
    for row in memory[:5]:
        row['correct'] = 0
    report = assess_training(rows, discovery(), FMRI_KEYS)
    assert report['phases']['guided_mapping']['passed']
    assert not report['phases']['memory_mapping']['passed']
    assert not report['acquired']


def test_perfect_patches_do_not_mask_misunderstood_stroop_instruction():
    rows = completed_records()
    for row in rows:
        if row['training_phase'] == 'stroop':
            row['correct'] = 0
    report = assess_training(rows, discovery(), FMRI_KEYS)
    assert report['phases']['memory_mapping']['passed']
    assert not report['phases']['stroop']['passed']
    assert not report['acquired']


def test_red_button_does_not_validate_an_unchecked_active_button():
    presses = discovery()[:2] + [{'key': 'r', 'time': 3, 'active': False}]
    report = assess_training(completed_records(), presses, FMRI_KEYS)
    assert not report['active_buttons_checked'] and not report['acquired']


def test_partial_training_does_not_pass():
    report = assess_training(completed_records()[:-1], discovery(), FMRI_KEYS)
    assert not report['complete'] and not report['acquired']


def test_omissions_count_as_errors_and_are_reported():
    rows = completed_records()
    for row in rows:
        row.update(correct=0, responded=0)
    report = assess_training(rows, discovery(), FMRI_KEYS)
    assert report['phases']['memory_mapping']['omissions'] == 18
    assert not report['acquired']
