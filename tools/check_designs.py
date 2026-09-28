#!/usr/bin/env python3
"""
Offline audit of every Stroop design.

Prints, for each design and over many seeds:
    - measured duration
    - trial-type / ink / pair / word counts
    - worst-case run lengths
    - pass/fail of every constraint

    python tools/check_designs.py
    python tools/check_designs.py --task stroop --repeats 200
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.tasks_config import load_task_config      # noqa: E402
from tasks.utils.pools import max_run_length          # noqa: E402


def build(task_name: str, design_id: int, seed: int):
    if task_name != 'stroop':
        raise SystemExit(f"Audit not implemented for '{task_name}'.")
    from tasks.stroop import StroopTask

    t = StroopTask.__new__(StroopTask)
    t.task_config = load_task_config('stroop')
    t.design_id = design_id
    t.design = t.task_config['designs'][design_id]
    t.block_sequence = [dict(b) for b in t.design['blocks']]
    t._rng = random.Random(seed)
    t.seed = seed
    t.logger = MagicMock()
    t.settings = MagicMock(mode='pc')
    t.win = MagicMock()

    c = t.task_config
    t._color_rgb = c['colors']
    t._ink_colors = list(c['colors'].keys())
    t._color_words = c['color_words']
    t._neutral_words = list(c['neutral_words'])
    t._inc_pairs = [(p['word'], p['ink']) for p in c['incongruent_pairs']]
    return t


def duration(task, blocks) -> float:
    d = task.design
    flat = [x for b in blocks for x in b]
    per_trial = sum(x[3] for x in flat) + len(flat) * (
        d['fixation_duration'] + d['stim_duration'])
    n_rest = len(task.block_sequence) + 1
    return (per_trial + n_rest * d['rest_duration']
            + len(task.block_sequence) * (d.get('instruction_duration', 0)
                                          + d.get('pre_block_fixation', 0)))


def spread(counter: Counter) -> int:
    return max(counter.values()) - min(counter.values()) if counter else 0


def audit(task_name: str, design_id: int, repeats: int) -> bool:
    worst = {'ink': 0, 'word': 0, 'type': 0,
             'spread_type': 0, 'spread_ink': 0,
             'spread_pair': 0, 'spread_neutral': 0}
    ok = True

    for seed in range(repeats):
        t = build(task_name, design_id, seed)
        blocks = t.build_all_trials()
        flat = [x for b in blocks for x in b]

        worst['spread_type'] = max(
            worst['spread_type'], spread(Counter(x[2] for x in flat)))
        worst['spread_ink'] = max(
            worst['spread_ink'], spread(Counter(x[1] for x in flat)))

        inc = Counter((x[0], x[1]) for x in flat if x[2] == 'incongruent')
        worst['spread_pair'] = max(worst['spread_pair'], spread(inc))
        if inc and len(inc) != 6:
            ok = False

        neu = Counter(x[0] for x in flat if x[2] == 'neutral')
        worst['spread_neutral'] = max(worst['spread_neutral'], spread(neu))

        for b in blocks:
            worst['ink'] = max(worst['ink'],
                               max_run_length([x[1] for x in b]))
            worst['word'] = max(worst['word'],
                                max_run_length([x[0] for x in b]))
        worst['type'] = max(worst['type'],
                            max_run_length([x[2] for x in flat]))

    t = build(task_name, design_id, 0)
    blocks = t.build_all_trials()
    flat = [x for b in blocks for x in b]
    secs = duration(t, blocks)
    is_event = t.design.get('paradigm') == 'event'

    print(f"\n{'=' * 66}")
    print(f"  DESIGN {design_id} — {t.design.get('name', '')}")
    print(f"{'=' * 66}")
    print(f"  Blocks ............ {len(blocks)}")
    print(f"  Trials ............ {len(flat)}")
    print(f"  Duration .......... {secs:.0f}s  ({secs / 60:.2f} min)")
    print(f"  Types ............. {dict(Counter(x[2] for x in flat))}")
    print(f"  Ink colours ....... {dict(Counter(x[1] for x in flat))}")

    print(f"\n  Worst case over {repeats} seeds")
    print(f"  {'-' * 60}")

    checks = [
        ('trial types balanced',    worst['spread_type'] <= 1,
         f"spread {worst['spread_type']}"),
        ('ink colours balanced',    worst['spread_ink'] <= 1,
         f"spread {worst['spread_ink']}"),
        ('incongruent pairs balanced', worst['spread_pair'] <= 1,
         f"spread {worst['spread_pair']}"),
        ('neutral words balanced',  worst['spread_neutral'] <= 1,
         f"spread {worst['spread_neutral']}"),
        ('max 2 same ink in a row', worst['ink'] <= 2,
         f"run {worst['ink']}"),
        ('max 2 same word in a row', worst['word'] <= 2,
         f"run {worst['word']}"),
        ('duration <= 6min30',      secs <= 390,
         f"{secs:.0f}s"),
    ]
    if is_event:
        checks.append(('never 2 same type in a row', worst['type'] == 1,
                       f"run {worst['type']}"))

    for name, passed, detail in checks:
        ok &= passed
        print(f"  [{'OK ' if passed else 'FAIL'}] {name:32s} {detail}")

    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', default='stroop')
    ap.add_argument('--repeats', type=int, default=100)
    ap.add_argument('--designs', type=int, nargs='+', default=[1, 2, 3, 4])
    args = ap.parse_args()

    all_ok = all(audit(args.task, d, args.repeats) for d in args.designs)

    print(f"\n{'=' * 66}")
    print("  ALL DESIGNS PASS" if all_ok else "  SOME CHECKS FAILED")
    print(f"{'=' * 66}\n")
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()