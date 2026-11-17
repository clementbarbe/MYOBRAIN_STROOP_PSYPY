#!/usr/bin/env python3
"""
Tâche Stroop en IRMf — interface de lancement.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.console import init_console
init_console()


def main():
    from gui.launcher import show_menu

    from core.experiment import Experiment

    settings = None
    while True:
        config = show_menu(settings)
        if config is None:
            return
        settings = config['settings']
        exp = Experiment(settings)
        try:
            saved = exp.run_stroop(training=config['training'])
            if saved:
                print(f"\n[OK] Data saved: {saved}")
        finally:
            exp.cleanup()


if __name__ == '__main__':
    main()
