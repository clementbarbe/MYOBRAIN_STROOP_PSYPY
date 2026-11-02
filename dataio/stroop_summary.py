"""Descriptive end-of-run statistics for the acquired Stroop trials."""

from math import isfinite
from numbers import Real
from statistics import fmean

CONDITIONS = ('congruent', 'incongruent', 'neutral')
LABELS = {'congruent': 'Congruent', 'incongruent': 'Incongruent', 'neutral': 'Neutre'}
CONTRASTS = (('incongruent', 'congruent'), ('incongruent', 'neutral'),
             ('neutral', 'congruent'))


def summarize_stroop(records: list[dict]) -> dict:
    """Runtime records only; RT means include correct, responded trials only."""
    conditions = {}
    for condition in CONDITIONS:
        rows = [row for row in records if row['condition'] == condition]
        correct = 0
        incorrect = 0
        omissions = 0
        rts = []
        for row in rows:
            responded = row.get('response') not in (None, '', 'n/a')
            if not responded:
                omissions += 1
            elif not row['correct']:
                incorrect += 1
            else:
                correct += 1
                rt = row.get('RT')
                if isinstance(rt, Real) and not isinstance(rt, bool) and isfinite(rt) and rt >= 0:
                    rts.append(float(rt) * 1000)
        n = len(rows)
        conditions[condition] = {
            'n_trials': n, 'correct': correct, 'incorrect': incorrect, 'omissions': omissions,
            'accuracy_percent': 100 * correct / n if n else None,
            'error_percent': 100 * incorrect / n if n else None,
            'omission_percent': 100 * omissions / n if n else None,
            'n_rt': len(rts), 'mean_rt_ms': fmean(rts) if rts else None,
        }
    contrasts = {}
    for first, second in CONTRASTS:
        differences = {}
        for metric in ('mean_rt_ms', 'accuracy_percent', 'error_percent', 'omission_percent'):
            a, b = conditions[first][metric], conditions[second][metric]
            differences[metric] = a - b if a is not None and b is not None else None
        contrasts[f'{first}_minus_{second}'] = differences
    return {'n_trials': sum(row['n_trials'] for row in conditions.values()),
            'conditions': conditions, 'contrasts': contrasts}


def format_stroop_summary(records: list[dict], subject: str, design: str,
                         expected_trials: int) -> str:
    report = summarize_stroop(records)

    def number(value, signed=False):
        if value is None:
            return 'n/a'
        return f'{value:+.1f}' if signed else f'{value:.1f}'

    lines = [
        f'BILAN STROOP | sujet {subject} | design {design} | '
        f'{report["n_trials"]}/{expected_trials} essais acquis',
        'Condition    | Bonnes        | Mauvaises | Absentes | TR moyen (ms) [n]',
    ]
    for condition in CONDITIONS:
        row = report['conditions'][condition]
        accuracy = number(row['accuracy_percent'])
        lines.append(f'{LABELS[condition]:12} | {row["correct"]:2}/{row["n_trials"]:<2} ({accuracy} %)'
                     f' | {row["incorrect"]:9} | {row["omissions"]:8}'
                     f' | {number(row["mean_rt_ms"])} [{row["n_rt"]}]')
    lines.append('TR : reponses correctes uniquement ; absences comptees separement. '
                 'Ecarts descriptifs : premiere condition - seconde (pp = points de pourcentage).')
    for first, second in CONTRASTS:
        diff = report['contrasts'][f'{first}_minus_{second}']
        lines.append(f'{LABELS[first]} - {LABELS[second]} : '
                     f'TR {number(diff["mean_rt_ms"], True)} ms | '
                     f'bonnes {number(diff["accuracy_percent"], True)} pp | '
                     f'mauvaises {number(diff["error_percent"], True)} pp | '
                     f'absences {number(diff["omission_percent"], True)} pp')
    return '\n'.join(lines)
