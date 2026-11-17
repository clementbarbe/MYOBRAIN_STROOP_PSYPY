"""Direct launch of training and the four fixed pilot runs."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from config.stroop_designs import DESIGNS, load_design, acquisition_timing
from config.tasks_config import load_task_config


class StroopPanel(QWidget):
    def __init__(self, menu):
        super().__init__()
        self.menu = menu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Pilote : 4 runs'))
        self.training_button = QPushButton('TRAINING')
        self.training_button.clicked.connect(lambda: menu.run_experiment(training=True))
        layout.addWidget(self.training_button)
        self.run_buttons = {}
        tr = float(load_task_config()['repetition_time_sec'])
        for run, design in enumerate(DESIGNS, 1):
            trials = load_design(design)
            seconds = acquisition_timing(trials, tr)['acquisition_duration']
            duration = f'{int(seconds // 60)} min {seconds % 60:05.2f} s'
            button = QPushButton(f'RUN {run} · {design} · {duration}')
            button.setObjectName('run')
            button.clicked.connect(lambda _, r=run: menu.run_experiment(run=r))
            self.run_buttons[run] = button
            layout.addWidget(button)
