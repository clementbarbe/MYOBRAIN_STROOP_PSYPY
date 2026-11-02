"""Verify the simplified Qt menu without opening a display."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel, QCheckBox

from config.settings import ExperimentSettings
from gui.launcher import ExperimentMenu


@pytest.fixture(scope='module')
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def menu(application, tmp_path, monkeypatch):
    monkeypatch.setattr('gui.launcher.ExperimentSettings',
                        lambda **kwargs: ExperimentSettings(data_root=tmp_path, **kwargs))
    window = ExperimentMenu()
    yield window
    window.close()


def test_training_above_task_and_no_session_or_hardware_options(menu, application):
    menu.show()
    application.processEvents()
    buttons = menu.findChildren(QPushButton)
    assert [button.text() for button in buttons] == ['TRAINING', 'RUN']
    panel = menu.stroop_panel
    assert panel.training_button.geometry().bottom() < panel.task_button.geometry().top()
    assert not menu.findChildren(QCheckBox)
    labels = [label.text() for label in menu.findChildren(QLabel)]
    assert labels[:3] == ['Sujet :', 'Écran :', 'Mode :']
    assert len(labels) == 5  # the three fields, design and duration


@pytest.mark.parametrize('subject,variant', [(1, 'A'), (2, 'B'), (3, 'C'), (4, 'D'), (5, 'A')])
def test_displayed_design_follows_subject(menu, subject, variant):
    menu.spin_subject.setValue(subject)
    assert menu.stroop_panel.design_label.text() == f'Design : {variant}'


def test_subject_five_launches_its_only_acquisition(menu):
    menu.spin_subject.setValue(5)
    menu.stroop_panel.task_button.click()
    config = menu.get_config()
    assert config['training'] is False
    assert config['settings'].participant_id == '005'
    assert config['settings'].run == '01'
    assert config['settings'].mode == 'fmri'


def test_existing_subject_keeps_menu_open(menu, monkeypatch):
    settings = menu.validate()
    directory = settings.task_dir()
    directory.mkdir(parents=True)
    (directory / f'{settings.base_name("stroop", "A")}_events.tsv').touch()
    warnings = []
    monkeypatch.setattr('gui.launcher.QMessageBox.warning', lambda *args: warnings.append(args))
    menu.stroop_panel.task_button.click()
    assert menu.get_config() is None
    assert warnings


def test_training_still_available_after_acquisition(menu):
    settings = menu.validate()
    directory = settings.task_dir()
    directory.mkdir(parents=True)
    (directory / f'{settings.base_name("stroop", "A")}_events.tsv').touch()
    menu.stroop_panel.training_button.click()
    assert menu.get_config()['training'] is True


def test_menu_reopens_with_same_settings_and_can_launch_run(application, tmp_path):
    from PyQt6.QtCore import QTimer
    from gui.launcher import show_menu

    previous = ExperimentSettings(participant_id='005', mode='pc', fullscreen=False,
                                  data_root=tmp_path)
    for training in (True, False):
        seen = []

        def choose_action():
            windows = [widget for widget in application.topLevelWidgets()
                       if isinstance(widget, ExperimentMenu) and widget.isVisible()]
            if not windows:
                application.quit()
                return
            window = windows[0]
            seen.append((window.spin_subject.value(), window.spin_scr.value(),
                         window.combo_mode.currentText(), window.stroop_panel.design_label.text()))
            button = (window.stroop_panel.training_button if training
                      else window.stroop_panel.task_button)
            button.click()

        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(application.quit)
        timeout.start(1000)
        QTimer.singleShot(0, choose_action)
        try:
            config = show_menu(previous)
        finally:
            timeout.stop()
        assert seen == [(5, 0, 'PC', 'Design : A')]
        assert config is not None and config['training'] is training
        assert config['settings'].data_root == tmp_path
        previous = config['settings']
