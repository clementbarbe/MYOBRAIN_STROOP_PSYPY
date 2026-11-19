#!/usr/bin/env python3
"""Display every key code from the actual button box and scanner trigger.

Run on the acquisition computer; this does not start or save an experiment.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.tasks_config import load_task_config
from config.input_keys import response_keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screen', type=int, default=0)
    parser.add_argument('--mode', choices=['pc', 'fmri'], default='fmri')
    parser.add_argument('--windowed', action='store_true')
    args = parser.parse_args()
    cfg = load_task_config()
    trigger = cfg.get('trigger_key', 't')
    mapping = response_keys(cfg, args.mode, trigger)
    from psychopy import visual, core
    from psychopy.hardware import keyboard

    win = visual.Window(size=(1920, 1080), fullscr=not args.windowed,
                        screen=args.screen, units='height', color='black', waitBlanking=True)
    clock = core.Clock()
    kb = keyboard.Keyboard(clock=clock)
    kb.clock = clock
    kb.clearEvents()
    stim = visual.TextStim(win, height=.028, wrapWidth=1.5, color='white')
    history = []
    last_trigger = None
    expected = ', '.join(f'{color}={key}' for color, key in mapping.items())
    print(f'Mapping attendu : {expected}. Trigger : {trigger!r}. Échap pour sortir.', flush=True)
    try:
        while True:
            # No keyList filter: reveal unexpected codes such as num_1 versus 1.
            for press in kb.getKeys(waitRelease=False):
                if press.name == 'escape':
                    return
                role = next((color for color, key in mapping.items() if key == press.name), 'non utilisée')
                if press.name == trigger:
                    interval = '' if last_trigger is None else f' · intervalle {press.rt - last_trigger:.4f} s'
                    last_trigger = press.rt
                    role = 'TRIGGER' + interval
                line = f'{press.name!r} → {role} (t={press.rt:.4f} s)'
                print(line, flush=True)
                history.append(line)
            stim.text = ('TEST BOÎTIER / TRIGGER\n\n'
                         'Appuyez sur chaque bouton et vérifiez la couleur reconnue.\n'
                         f'{expected}\nTrigger attendu : {trigger!r}\n\n'
                         + '\n'.join(history[-8:]) + '\n\nÉCHAP pour quitter')
            stim.draw()
            win.flip()
    finally:
        win.close()


if __name__ == '__main__':
    main()
