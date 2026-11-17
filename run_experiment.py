#!/usr/bin/env python3
"""Launch Stroop with an explicit pilot run (1 to 4)."""

import argparse

from utils.console import init_console


def main():
    parser = argparse.ArgumentParser(description='Stroop IRMf — pilote E2_A / E3_A / E3_B / E2_B')
    parser.add_argument('--subject', '--pid', dest='subject', type=int, required=True,
                        help='Numéro du sujet')
    parser.add_argument('--run', type=int, choices=[1, 2, 3, 4],
                        help='1=E2_A, 2=E3_A, 3=E3_B, 4=E2_B')
    parser.add_argument('--training', action='store_true', help='Environ 3 minutes : boîtier, pastilles puis Stroop, sans trigger')
    parser.add_argument('--mode', default='fmri', choices=['pc', 'fmri'])
    parser.add_argument('--screen', type=int, default=0)
    parser.add_argument('--no-fullscreen', action='store_true')
    args = parser.parse_args()
    if args.run is None and not args.training:
        parser.error('--run est requis pour une acquisition')
    if args.subject < 1:
        parser.error('Le numéro d’inclusion doit être supérieur ou égal à 1')
    if args.screen < 0:
        parser.error('--screen doit être supérieur ou égal à 0')

    from config.settings import ExperimentSettings
    from config.stroop_designs import design_for_run
    settings = ExperimentSettings(
        participant_id=str(args.subject), run=f'{args.run or 1:02d}',
        mode=args.mode, fullscreen=not args.no_fullscreen,
        screen_index=args.screen,
    )
    try:
        variant = 'training' if args.training else design_for_run(args.run)
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
