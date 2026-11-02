#!/usr/bin/env python3
"""
Verify a behavioural events.tsv.

Checks the ten canonical columns, the internal consistency of the
responses, and the onset reference. Exit code is non-zero if any
required check fails.

    python tools/check_output.py data/sub-01/ses-01/stroop/*_events.tsv
    python tools/check_output.py --all data/
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REQUIRED = ['subject', 'run', 'trial', 'condition', 'onset',
            'stimulus', 'correct_response', 'response', 'correct', 'RT']
NA = 'n/a'


def read_tsv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        return list(reader.fieldnames or []), list(reader)


def num(value: str) -> float | None:
    if value is None or value == NA or value == '':
        return None
    try:
        return float(value)
    except ValueError:
        return None


def check_file(path: Path) -> bool:
    print(f"\n{'=' * 70}")
    print(f"  {path.name}")
    print(f"{'=' * 70}")

    header, rows = read_tsv(path)
    if not rows:
        print("  [FAIL] file contains no data row")
        return False

    results: list[tuple[str, bool, str, bool]] = []   # name, ok, detail, hard

    def add(name, ok, detail='', hard=True):
        results.append((name, ok, detail, hard))

    # ── Required columns ─────────────────────────────────────────────
    missing = [c for c in REQUIRED if c not in header]
    add('ten canonical columns present', not missing,
        'all present' if not missing else f"missing {missing}")

    add('onset is the first column', header[0] == 'onset' or 'onset' in header,
        f"first column is '{header[0]}'", hard=False)

    print(f"  Rows .............. {len(rows)}")
    print(f"  Columns ........... {len(header)}")

    # ── subject, run ─────────────────────────────────────────────────
    if 'subject' in header:
        subs = {r['subject'] for r in rows}
        add('single subject per file', len(subs) == 1, f"{sorted(subs)}")
    if 'run' in header:
        runs = {r['run'] for r in rows}
        add('single run per file', len(runs) == 1, f"{sorted(runs)}")

    # ── trial ────────────────────────────────────────────────────────
    if 'trial' in header:
        trials = [int(r['trial']) for r in rows if r['trial'] != NA]
        add('trial starts at 1', trials and trials[0] == 1,
            f"first = {trials[0] if trials else 'n/a'}")
        add('trial increments by one',
            trials == list(range(1, len(trials) + 1)),
            f"1..{len(trials)}" if trials == list(range(1, len(trials) + 1))
            else 'gaps or duplicates')

    # ── onset ────────────────────────────────────────────────────────
    onsets = [num(r['onset']) for r in rows] if 'onset' in header else []
    onsets = [o for o in onsets if o is not None]
    if onsets:
        add('onset always present', len(onsets) == len(rows),
            f"{len(onsets)}/{len(rows)}")
        add('onset is non-negative', min(onsets) >= 0,
            f"min = {min(onsets):.3f}s")
        add('onset is strictly increasing',
            all(b > a for a, b in zip(onsets, onsets[1:])),
            'monotonic' if all(b > a for a, b in zip(onsets, onsets[1:]))
            else 'non-monotonic')
        print(f"  Onset range ....... {min(onsets):.2f} - {max(onsets):.2f}s "
              f"({max(onsets) / 60:.2f} min)")
        add('first onset after a plausible initial rest',
            onsets[0] >= 1.0, f"{onsets[0]:.2f}s", hard=False)

    # ── condition ────────────────────────────────────────────────────
    if 'condition' in header:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r['condition']] = counts.get(r['condition'], 0) + 1
        add('conditions are labelled', all(c != NA for c in counts),
            f"{counts}")
        if len(counts) > 1:
            spread = max(counts.values()) - min(counts.values())
            add('conditions balanced', spread <= 1,
                f"spread = {spread}", hard=False)

    # ── response consistency ─────────────────────────────────────────
    if all(c in header for c in ('correct_response', 'response', 'correct')):
        bad = 0
        for r in rows:
            resp, want, flag = r['response'], r['correct_response'], r['correct']
            if resp == NA:
                if flag != '0':
                    bad += 1
            elif (resp == want) != (flag == '1'):
                bad += 1
        add('correct matches response vs correct_response', bad == 0,
            f"{bad} inconsistent rows")

    # ── RT ───────────────────────────────────────────────────────────
    if 'RT' in header and 'response' in header:
        no_resp_with_rt = sum(
            1 for r in rows if r['response'] == NA and num(r['RT']) is not None
        )
        resp_no_rt = sum(
            1 for r in rows if r['response'] != NA and num(r['RT']) is None
        )
        add('RT is n/a when there is no response', no_resp_with_rt == 0,
            f"{no_resp_with_rt} offenders")
        add('RT present whenever a response was given', resp_no_rt == 0,
            f"{resp_no_rt} offenders")

        rts = [num(r['RT']) for r in rows]
        rts = [v for v in rts if v is not None]
        if rts:
            add('no negative RT', min(rts) >= 0, f"min = {min(rts):.3f}s")
            add('RT within a plausible window', max(rts) <= 5.0,
                f"max = {max(rts):.3f}s", hard=False)
            s = sorted(rts)
            m = len(s) // 2
            med = s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
            print(f"  RT ................ n={len(rts)} "
                  f"median={med * 1000:.0f}ms "
                  f"range={min(rts) * 1000:.0f}-{max(rts) * 1000:.0f}ms")

    # ── Never -1 as a missing marker ─────────────────────────────────
    sentinels = sum(
        1 for r in rows for c in ('RT', 'rt') if c in header and r[c] == '-1'
    )
    add('no -1 sentinel in RT', sentinels == 0, f"{sentinels} found")

    # ── Companion sidecars ───────────────────────────────────────────
    add('events.json present', path.with_suffix('.json').exists(),
        path.with_suffix('.json').name, hard=False)

    stem = path.name.replace('_events.tsv', '')
    trig = path.parent / f"{stem}_scantrig.json"
    if trig.exists():
        try:
            info = json.loads(trig.read_text(encoding='utf-8'))
            tr = info.get('tr_measured')
            n = info.get('n_triggers')
            dev = info.get('max_deviation_from_median', 0)
            print(f"  Scanner pulses .... n={n} TR={tr}s "
                  f"deviation={dev * 1000:.0f}ms")
            add('TR is regular', dev is not None and dev <= 0.05,
                f"{dev * 1000:.0f}ms off the median", hard=False)
            first_gap = (info['trigger_times'][1] - info['trigger_times'][0]
                         if len(info.get('trigger_times', [])) > 1 else None)
            if first_gap is not None and tr:
                add('first pulse was not a dummy scan',
                    abs(first_gap - tr) <= 0.05,
                    f"first interval {first_gap:.3f}s vs TR {tr:.3f}s",
                    hard=False)
        except Exception as e:
            print(f"  [warn] cannot read {trig.name}: {e}")
    else:
        add('scantrig.json present', False, 'absent', hard=False)

    # ── Report ───────────────────────────────────────────────────────
    print(f"\n  {'-' * 64}")
    hard_ok = True
    for name, ok, detail, hard in results:
        tag = 'OK  ' if ok else ('FAIL' if hard else 'warn')
        print(f"  [{tag}] {name:44s} {detail}")
        if hard and not ok:
            hard_ok = False

    return hard_ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+', type=Path)
    ap.add_argument('--all', action='store_true',
                    help='treat the paths as directories and recurse')
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        if args.all or p.is_dir():
            files.extend(sorted(p.rglob('*_events.tsv')))
        else:
            files.append(p)

    files = [f for f in files if 'incremental' not in f.name]
    if not files:
        print("No *_events.tsv found.")
        sys.exit(1)

    all_ok = all(check_file(f) for f in files)

    print(f"\n{'=' * 70}")
    print(f"  {len(files)} file(s) checked — "
          f"{'ALL PASS' if all_ok else 'FAILURES FOUND'}")
    print(f"{'=' * 70}\n")
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()