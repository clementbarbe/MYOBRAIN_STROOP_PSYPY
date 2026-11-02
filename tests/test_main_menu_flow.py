"""Training releases PsychoPy resources before returning to the launcher."""

from unittest.mock import MagicMock

from config.settings import ExperimentSettings
import main


def test_training_then_run_reopens_menu_with_settings_and_cleans_up(monkeypatch, tmp_path):
    settings = ExperimentSettings(participant_id='5', data_root=tmp_path)
    choices = iter(({'settings': settings, 'training': True},
                    {'settings': settings, 'training': False}))
    events = []

    def show_menu(previous):
        events.append(('menu', previous))
        return next(choices)

    class Experiment:
        def __init__(self, selected):
            assert selected is settings
        def run_stroop(self, training):
            events.append(('execute', training))
        def cleanup(self):
            events.append(('cleanup', None))

    monkeypatch.setattr('gui.launcher.show_menu', show_menu)
    monkeypatch.setattr('core.experiment.Experiment', Experiment)
    main.main()
    assert events == [('menu', None), ('execute', True), ('cleanup', None),
                      ('menu', settings), ('execute', False), ('cleanup', None)]


def test_closing_reopened_menu_ends_after_training(monkeypatch, tmp_path):
    settings = ExperimentSettings(participant_id='5', data_root=tmp_path)
    show_menu = MagicMock(side_effect=[{'settings': settings, 'training': True}, None])
    experiment = MagicMock()
    experiment.run_stroop.return_value = None  # also cover interrupted training
    constructor = MagicMock(return_value=experiment)
    monkeypatch.setattr('gui.launcher.show_menu', show_menu)
    monkeypatch.setattr('core.experiment.Experiment', constructor)
    main.main()
    assert show_menu.call_count == 2
    constructor.assert_called_once_with(settings)
    experiment.cleanup.assert_called_once()
