"""Four pilot launch buttons, with independent collision checks and state reuse."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton, QCheckBox

from config.settings import ExperimentSettings
from config.stroop_designs import DESIGNS
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


def test_training_and_four_ordered_run_buttons(menu, application):
    menu.show()
    application.processEvents()
    buttons = menu.findChildren(QPushButton)
    assert buttons[0].text() == 'TRAINING'
    assert len(buttons) == 5
    for index, design in enumerate(DESIGNS, 1):
        assert buttons[index].text().startswith(f'RUN {index} · {design}')
        assert '8 min 40.29 s' in buttons[index].text()
        assert buttons[index - 1].geometry().bottom() < buttons[index].geometry().top()
    assert not menu.findChildren(QCheckBox)


@pytest.mark.parametrize('run', [1, 2, 3, 4])
def test_subject_can_launch_each_pilot_run(menu, run):
    menu.spin_subject.setValue(5)
    menu.stroop_panel.run_buttons[run].click()
    config = menu.get_config()
    assert config['training'] is False
    assert config['settings'].participant_id == '005'
    assert config['settings'].run == f'{run:02d}'


def test_existing_run_blocks_only_that_run(menu, monkeypatch):
    settings = menu.validate()
    directory = settings.task_dir()
    directory.mkdir(parents=True)
    (directory / f'{settings.base_name("stroop", "E2_A")}_events.tsv').touch()
    warnings = []
    monkeypatch.setattr('gui.launcher.QMessageBox.warning', lambda *args: warnings.append(args))
    menu.stroop_panel.run_buttons[1].click()
    assert menu.get_config() is None and warnings
    menu.stroop_panel.run_buttons[2].click()
    assert menu.get_config()['settings'].run == '02'


def test_training_available_after_acquisition(menu):
    settings = menu.validate()
    directory = settings.task_dir()
    directory.mkdir(parents=True)
    (directory / f'{settings.base_name("stroop", "E2_A")}_events.tsv').touch()
    menu.stroop_panel.training_button.click()
    assert menu.get_config()['training'] is True


def test_menu_reopens_for_training_and_all_four_runs(application, tmp_path):
    from PyQt6.QtCore import QTimer
    from gui.launcher import show_menu

    previous = ExperimentSettings(participant_id='005', mode='pc', fullscreen=False,
                                  data_root=tmp_path)
    for run in (None, 1, 2, 3, 4):
        seen = []

        def choose_action():
            windows = [widget for widget in application.topLevelWidgets()
                       if isinstance(widget, ExperimentMenu) and widget.isVisible()]
            if not windows:
                application.quit()
                return
            window = windows[0]
            seen.append((window.spin_subject.value(), window.spin_scr.value(),
                         window.combo_mode.currentText()))
            button = (window.stroop_panel.training_button if run is None
                      else window.stroop_panel.run_buttons[run])
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
        assert seen == [(5, 0, 'PC')]
        assert config is not None and config['training'] is (run is None)
        assert config['settings'].data_root == tmp_path
        if run:
            assert config['settings'].run == f'{run:02d}'
        previous = config['settings']
