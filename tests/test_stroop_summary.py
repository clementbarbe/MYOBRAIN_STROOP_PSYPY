"""Descriptive effects use correct RTs and condition-specific denominators."""

import pytest

from dataio.stroop_summary import summarize_stroop, format_stroop_summary


def trial(condition, rt=None, correct=1, response='b'):
    return {'condition': condition, 'RT': rt, 'correct': correct, 'response': response}


def test_error_and_omission_rts_are_excluded_from_mean_and_rates_use_each_condition():
    records = [
        trial('congruent', .4), trial('congruent', .6),
        trial('congruent', .01, correct=0), trial('congruent', response=None, correct=0),
        trial('incongruent', .7), trial('incongruent', .9),
        trial('incongruent', .1, correct=0), trial('neutral', .55),
    ]
    report = summarize_stroop(records)
    congruent = report['conditions']['congruent']
    assert congruent == {
        'n_trials': 4, 'correct': 2, 'incorrect': 1, 'omissions': 1,
        'accuracy_percent': 50.0, 'error_percent': 25.0, 'omission_percent': 25.0,
        'n_rt': 2, 'mean_rt_ms': 500.0,
    }
    effect = report['contrasts']['incongruent_minus_congruent']
    assert effect['mean_rt_ms'] == pytest.approx(300)
    assert effect['accuracy_percent'] == pytest.approx(100 * 2 / 3 - 50)
    assert effect['error_percent'] == pytest.approx(100 / 3 - 25)
    assert effect['omission_percent'] == -25.0
    assert report['contrasts']['incongruent_minus_neutral']['mean_rt_ms'] == pytest.approx(250)
    assert report['contrasts']['neutral_minus_congruent']['mean_rt_ms'] == pytest.approx(50)


@pytest.mark.parametrize('invalid_rt', [None, float('nan'), float('inf'), -0.5, True])
def test_invalid_correct_rt_does_not_pollute_mean(invalid_rt):
    report = summarize_stroop([trial('congruent', .5), trial('congruent', invalid_rt)])
    row = report['conditions']['congruent']
    assert row['correct'] == 2
    assert row['n_rt'] == 1 and row['mean_rt_ms'] == 500


def test_all_omissions_do_not_produce_zero_rt_or_zero_effect():
    report = summarize_stroop([trial('incongruent', correct=0, response=None)])
    assert report['conditions']['incongruent']['omissions'] == 1
    assert report['conditions']['incongruent']['mean_rt_ms'] is None
    assert report['contrasts']['incongruent_minus_congruent']['mean_rt_ms'] is None
    assert report['contrasts']['incongruent_minus_congruent']['accuracy_percent'] is None


def test_partial_run_is_labelled_and_shows_signed_rt_effect():
    records = [trial('congruent', .5), trial('incongruent', .8)]
    log = format_stroop_summary(records, '002', 'B', 75)
    assert 'sujet 002 | design B | 2/75 essais acquis' in log
    assert 'Incongruent - Congruent : TR +300.0 ms' in log
    assert 'TR : reponses correctes uniquement' in log
    assert 'Mauvaises' in log and 'Absentes' in log
    assert 'Neutre' in log and 'n/a' in log
