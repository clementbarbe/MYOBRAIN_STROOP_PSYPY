#!/usr/bin/env python3
"""Launch Stroop with the design assigned by subject inclusion number."""

import argparse

from utils.console import init_console


def main():
    parser = argparse.ArgumentParser(description='Stroop IRMf — design associé au numéro d’inclusion')
    parser.add_argument('--subject', '--pid', dest='subject', type=int, required=True,
                        help='Numéro d’inclusion : sujet 1=A, 2=B, 3=C, 4=D, 5=A…')
    parser.add_argument('--training', action='store_true', help='Environ 3 minutes : boîtier, pastilles puis Stroop, sans trigger')
    parser.add_argument('--mode', default='fmri', choices=['pc', 'fmri'])
    parser.add_argument('--screen', type=int, default=0)
    parser.add_argument('--no-fullscreen', action='store_true')
    args = parser.parse_args()
    if args.subject < 1:
        parser.error('Le numéro d’inclusion doit être supérieur ou égal à 1')
    if args.screen < 0:
        parser.error('--screen doit être supérieur ou égal à 0')

    from config.settings import ExperimentSettings
    from config.stroop_designs import design_for_subject
    settings = ExperimentSettings(
        participant_id=str(args.subject),
        mode=args.mode, fullscreen=(not args.no_fullscreen and args.mode == 'fmri'),
        screen_index=args.screen,
    )
    try:
        variant = 'training' if args.training else design_for_subject(args.subject)
        settings.run = settings.resolve_run('stroop', variant)
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))

    init_console()
    from core.experiment import Experiment
    experiment = Experiment(settings)
    try:
        saved = experiment.run_stroop(training=args.training)
        if saved:
            print(f'\n[OK] {saved}')
    finally:
        experiment.cleanup()


if __name__ == '__main__':
    main()
