"""Minimal Stroop launcher, for four independent pilot runs per subject."""

from __future__ import annotations

import sys
from dataclasses import replace

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QSpinBox, QComboBox, QMessageBox,
)

from config.settings import ExperimentSettings
from config.stroop_designs import design_for_run
from gui.styles import STYLESHEET
from gui.task_panels import StroopPanel


_application = None


class ExperimentMenu(QMainWindow):
    def __init__(self, initial_settings: ExperimentSettings | None = None):
        super().__init__()
        self.setWindowTitle('Stroop — IRMf')
        self.setStyleSheet(STYLESHEET)
        self.setMinimumWidth(300)
        self.final_config = None
        self.initial_settings = initial_settings
        self._build()
        if initial_settings is not None:
            self.spin_subject.setValue(int(initial_settings.participant_id))
            self.spin_scr.setValue(initial_settings.screen_index)
            self.combo_mode.setCurrentText('fMRI' if initial_settings.mode == 'fmri' else 'PC')

    def _build(self):
        central = QWidget()
        central.setObjectName('central')
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        grid = QGridLayout()
        grid.addWidget(QLabel('Sujet :'), 0, 0)
        self.spin_subject = QSpinBox()
        self.spin_subject.setRange(1, 999999)
        grid.addWidget(self.spin_subject, 0, 1)
        grid.addWidget(QLabel('Écran :'), 1, 0)
        self.spin_scr = QSpinBox()
        self.spin_scr.setRange(0, max(0, len(QApplication.screens()) - 1))
        grid.addWidget(self.spin_scr, 1, 1)
        grid.addWidget(QLabel('Mode :'), 2, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(['PC', 'fMRI'])
        self.combo_mode.setCurrentText('fMRI')
        grid.addWidget(self.combo_mode, 2, 1)
        root.addLayout(grid)
        self.stroop_panel = StroopPanel(self)
        root.addWidget(self.stroop_panel)

    def validate(self, run: int = 1) -> ExperimentSettings:
        mode = self.combo_mode.currentText().lower()
        values = dict(
            participant_id=str(self.spin_subject.value()), run=f'{run:02d}',
            mode=mode, fullscreen=True,
            screen_index=self.spin_scr.value(),
        )
        if self.initial_settings is not None:
            return replace(self.initial_settings, **values)
        return ExperimentSettings(**values)

    def run_experiment(self, training: bool = False, run: int = 1):
        settings = self.validate(run)
        design_id = 'training' if training else design_for_run(run)
        try:
            settings.run = settings.resolve_run('stroop', design_id)
        except (ValueError, FileExistsError) as error:
            QMessageBox.warning(self, 'Run déjà enregistré', str(error))
            return
        self.final_config = {'settings': settings, 'training': training}
        self.close()
        app = QApplication.instance()
        if app:
            app.quit()

    def get_config(self):
        return self.final_config


def show_menu(initial_settings: ExperimentSettings | None = None) -> dict | None:
    # Keep the QApplication alive while PsychoPy runs between menu visits.
    global _application
    _application = QApplication.instance() or QApplication(sys.argv)
    menu = ExperimentMenu(initial_settings)
    menu.show()
    _application.exec()
    return menu.get_config()
