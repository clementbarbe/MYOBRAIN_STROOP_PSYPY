"""Design, duration and the two Stroop launch buttons."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from config.stroop_designs import design_for_subject, load_design
from config.tasks_config import load_task_config


class StroopPanel(QWidget):
    def __init__(self, menu):
        super().__init__()
        self.menu = menu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.design_label = QLabel()
        layout.addWidget(self.design_label)
        self.duration_label = QLabel()
        layout.addWidget(self.duration_label)
        self.update_design()
        self.training_button = QPushButton('TRAINING')
        self.training_button.clicked.connect(lambda: self.menu.run_experiment(training=True))
        layout.addWidget(self.training_button)
        self.task_button = QPushButton('RUN')
        self.task_button.setObjectName('run')
        self.task_button.clicked.connect(lambda: self.menu.run_experiment(training=False))
        layout.addWidget(self.task_button)

    def update_design(self, *_):
        variant = design_for_subject(self.menu.spin_subject.value())
        self.design_label.setText(f'Design : {variant}')
        try:
            trials = load_design(variant)
            seconds = trials[-1]['fixation_onset'] + trials[-1]['fixation_after_sec']
            seconds += float(load_task_config().get('final_rest_duration', 10.0))
            self.duration_label.setText(f'Durée : {int(seconds // 60)} min {seconds % 60:05.2f} s')
        except (OSError, ValueError) as error:
            self.duration_label.setText(f'Design à vérifier : {error}')
