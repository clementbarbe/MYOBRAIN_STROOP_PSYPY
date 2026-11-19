"""Horizontal response-box diagram showing the required ink colours.

All geometry uses height units: buttons stay circular on wide screens.
The three active buttons use the same colours as the task stimuli.
"""

from psychopy import visual


class ButtonBoxView:
    def __init__(self, win, color_to_key: dict, ink_colors: dict):
        self.color_to_key = color_to_key
        self.key_to_index = {color_to_key[color]: index
                             for index, color in enumerate(('rouge', 'bleu', 'vert'))}
        self.unused_key = 'r' if 'r' not in self.key_to_index else None
        if self.unused_key is not None:
            self.key_to_index[self.unused_key] = 3
        self.flash_until = {}
        self.body = visual.Rect(win, units='height', width=1.12, height=0.22,
                                pos=(0, -0.15), fillColor=(0.77, 0.75, 0.69),
                                lineColor=(0.35, 0.35, 0.32), lineWidth=3)
        self.inset = visual.Rect(win, units='height', width=1.04, height=0.16,
                                 pos=(0, -0.15), fillColor=(0.84, 0.82, 0.76),
                                 lineColor=(0.50, 0.48, 0.43))
        self.cable = visual.Line(win, units='height', start=(-0.56, -0.15),
                                 end=(-0.78, -0.15), lineColor=(0, 0, 0), lineWidth=10)
        self.buttons = []
        self.halos = []
        self.labels = []
        response_colors = [ink_colors[color] for color in ('rouge', 'bleu', 'vert')]
        response_colors.append((0.2, 0.2, 0.2))  # unused fourth button
        for index, color in enumerate(response_colors):
            x = (index - 1.5) * 0.26
            self.buttons.append(visual.Circle(
                win, units='height', radius=0.041, edges=128, pos=(x, -0.15),
                fillColor=color, lineColor=(-0.3, -0.3, -0.3), lineWidth=2,
            ))
            self.halos.append(visual.Circle(
                win, units='height', radius=0.054, edges=128, pos=(x, -0.15),
                fillColor=None, lineColor='white', lineWidth=5,
            ))
            self.labels.append(visual.TextStim(
                win, units='height', pos=(x, -0.32), height=0.022,
                text='', color='white', wrapWidth=0.25,
            ))
        self.heading = visual.TextStim(win, units='height', pos=(0, 0.40),
                                       height=0.033, wrapWidth=1.5, text='', color='white')
        self.detail = visual.TextStim(win, units='height', pos=(0, 0.18),
                                      height=0.027, wrapWidth=1.5, text='', color='white')
        self.progress = visual.TextStim(win, units='height', pos=(0, -0.43),
                                        height=0.024, wrapWidth=1.5, text='', color='white')
        self.patch = visual.Circle(win, units='height', radius=0.075, edges=128,
                                   pos=(0, 0.13), fillColor='white', lineColor=None)

    def flash(self, key: str, now: float):
        if key in self.key_to_index:
            self.flash_until[self.key_to_index[key]] = now + 0.6

    def draw_box(self, now: float, checked: set | None = None):
        self.cable.draw()
        self.body.draw()
        self.inset.draw()
        for index, button in enumerate(self.buttons):
            button.draw()
            until = self.flash_until.get(index, 0.0)
            if now < until and int((until - now) * 10) % 2 == 1:
                self.halos[index].draw()
            if index < 3:
                color = ('rouge', 'bleu', 'vert')[index]
                key = self.color_to_key[color]
                tick = ' ✓' if checked is not None and key in checked else ''
                self.labels[index].text = f'Encre {color.upper()}\n{key.upper()}{tick}'
            else:
                self.labels[index].text = 'Non utilisé' + ('\nR' if self.unused_key else '')
            self.labels[index].draw()

    def draw_discovery(self, now: float, checked: set, remaining: float):
        self.heading.text = 'Découverte du boîtier'
        self.detail.text = ('Appuyez sur chacun des trois boutons de réponse.\n'
                            'Le bouton correspondant clignote à l’écran.')
        self.progress.text = f'{len(checked & set(self.color_to_key.values()))}/3 boutons vérifiés · {max(0, remaining):.0f} s'
        self.heading.draw()
        self.detail.draw()
        self.draw_box(now, checked)
        self.progress.draw()

    def draw_phase_instruction(self, phase: str):
        instructions = {
            'guided_mapping': ('1 · Association couleur–touche',
                               'Répondez à la couleur de la pastille.\n'
                               'Le rappel des associations reste affiché.\nUne correction suit chaque essai.'),
            'memory_mapping': ('2 · Vérification sans rappel',
                               'Même exercice, sans aide.\n'
                               'Retrouvez la bonne touche de mémoire.\nUne correction suit chaque essai.'),
            'stroop': ('3 · Familiarisation Stroop',
                       'Répondez à la COULEUR DE L’ENCRE.\nIgnorez le sens du mot.\n'
                       'Même présentation que la tâche, sans aide ni correction.'),
        }
        self.heading.text, self.detail.text = instructions[phase]
        self.heading.draw()
        self.detail.draw()
