#!/usr/bin/env python3
"""Offline validation of the four exact pilot TSV schedules."""

import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.stroop_designs import DESIGNS, load_design, acquisition_timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--designs', nargs='+', choices=list(DESIGNS), default=list(DESIGNS))
    args = parser.parse_args()
    valid = True
    for variant in args.designs:
        try:
            rows = load_design(variant)
            end = rows[-1]['fixation_onset'] + rows[-1]['fixation_after_sec']
            print(f'{variant}: {len(rows)} essais, début {rows[0]["onset"]:.2f}s, fin {end:.2f}s')
            timing = acquisition_timing(rows)
            print(f'  Acquisition : {timing["n_volumes"]} volumes · {timing["acquisition_duration"]:.2f}s')
            print(f'  Conditions : {dict(Counter(row["condition"] for row in rows))}')
            print(f'  Couleurs : {dict(Counter(row["ink_color"] for row in rows))}')
        except (OSError, ValueError) as error:
            valid = False
            print(f'{variant}: ERREUR — {error}', file=sys.stderr)
    return 0 if valid else 1


if __name__ == '__main__':
    sys.exit(main())
