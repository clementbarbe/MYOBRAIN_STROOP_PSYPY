"""Execute the task logic on a virtual display clock (no hardware timing claim)."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import json

import pytest

from config.scanners.base import ScannerConfig
from config.settings import ExperimentSettings
from config.tasks_config import load_task_config
from core.events import EventBus
from core.exceptions import AbortExperiment
from dataio.data_writer import DataWriter
from tasks.stroop import StroopTask


class VirtualClock:
    def __init__(self):
        self.time = 0.0
        self.psychopy_clock = SimpleNamespace(getTime=lambda: self.time)
        self.trigger_wall_time = 'virtual clock'

    def reset(self):
        self.time = 0.0

    def wait(self, duration):
        self.time += duration


class VirtualWindow:
    _closed = False

    def __init__(self, clock):
        self.clock = clock

    def flip(self):
        self.clock.time += 1 / 60


@pytest.fixture
def task_factory(tmp_path):
    writers = []

    def build(variant='A', mode='pc'):
        clock = VirtualClock()
        settings = ExperimentSettings(participant_id='001', run='01', mode=mode, data_root=tmp_path)
        if variant in 'ABCD':
            settings.participant_id = f'{"ABCD".index(variant) + 1:03d}'
        writer = DataWriter(settings.task_dir(), settings.base_name('stroop', variant), MagicMock())
        writers.append(writer)
        task = StroopTask(
            win=VirtualWindow(clock), clock=clock, hardware=MagicMock(),
            data_writer=writer, logger=MagicMock(), event_bus=EventBus(),
            settings=settings, scanner=ScannerConfig(),
            task_config=load_task_config(), design_id=variant,
        )
        task._word_stim = MagicMock()
        task._fixation = MagicMock()
        task._feedback = MagicMock()
        task.prepare()
        task.get_keys = lambda key_list=None: []
        return task

    yield build
    for writer in writers:
        writer.close()


@pytest.mark.parametrize('variant', list('ABCD'))
def test_all_trials_follow_absolute_deadlines(task_factory, variant):
    task = task_factory(variant)
    task.run_block(0, task.block_sequence[0])
    task.run_rest('final')
    rows = task.data_writer.records
    assert len(rows) == 75
    for row, planned in zip(rows, task._schedule):
        assert abs(row['onset'] - planned['onset']) < 2 / 60
        assert abs(row['duration'] - planned['duration']) < 2 / 60
        assert row['stimulus'] == planned['stimulus']
        assert row['condition'] == planned['condition']
        assert row['response'] is None and row['RT'] is None
        assert row['correct'] == 0
    last = task._schedule[-1]
    schedule_end = last['fixation_onset'] + last['fixation_after_sec']
    assert abs(task.clock.time - (schedule_end + 10.0)) < 2 / 60
    sidecar = next(task.settings.task_dir().glob('*_design.json'))
    timing = json.loads(sidecar.read_text())
    assert timing['schedule_duration'] == pytest.approx(schedule_end)
    assert timing['final_rest_duration'] == 10.0
    assert timing['duration'] == pytest.approx(schedule_end + 10.0)
    assert task.data_writer.save_final().exists()


@pytest.mark.parametrize('mode', ['pc', 'fmri'])
def test_response_uses_ink_and_keyboard_timestamp(task_factory, mode):
    task = task_factory(mode=mode)
    trial = task._schedule[0]
    expected = task._color_to_key[trial['ink_color']]
    sent = False

    def keys(key_list=None):
        nonlocal sent
        timestamp = trial['onset'] + 0.3
        if key_list and not sent and task.clock.time >= timestamp:
            sent = True
            return [SimpleNamespace(name=expected, rt=timestamp)]
        return []

    task.get_keys = keys
    row = task.run_trial(trial, 0, 0, task.block_sequence[0])
    assert row['response'] == expected
    assert row['correct'] == 1
    assert row['RT'] == pytest.approx(0.3, abs=2 / 60)
    assert task.clock.time < trial['onset'] + trial['duration'] + 2 / 60


def test_training_skips_scanner_and_provides_feedback(task_factory):
    task = task_factory('training')
    task.clock.time = 25.0
    task.wait_for_trigger()
    assert task.clock.time == 0
    task.run_block(0, task.block_sequence[0])
    task.run_rest('final')
    assert len(task.data_writer.records) == 45
    assert task._feedback.text
    assert abs(task.clock.time - task._run_end) < 2 / 60
    last = task._schedule[-1]
    assert task._run_end == pytest.approx(last['fixation_onset'] + last['fixation_after_sec'])
    sidecar = next(task.settings.task_dir().glob('*_design.json'))
    assert json.loads(sidecar.read_text())['source_file'] is None


def test_escape_is_polled_after_a_response(task_factory):
    task = task_factory()
    trial = task._schedule[0]
    response_given = False

    def keys(key_list=None):
        nonlocal response_given
        if response_given:
            raise AbortExperiment('Escape after response')
        if key_list and task.clock.time > trial['onset'] + 0.2:
            response_given = True
            return [SimpleNamespace(name=task._color_to_key[trial['ink_color']], rt=task.clock.time)]
        return []

    task.get_keys = keys
    with pytest.raises(AbortExperiment):
        task.run_trial(trial, 0, 0, task.block_sequence[0])


def test_full_training_lifecycle_saves_complete_output(task_factory):
    task = task_factory('training')
    task.show_text_and_wait = lambda text: None
    saved = task.run()
    assert saved is not None and saved.exists()
    assert len(task.data_writer.records) == 45
    metadata = json.loads(saved.with_suffix('.json').read_text())
    assert all(info['Description'] != 'Not documented.' for info in metadata.values())


def test_keyboard_pulses_cannot_become_responses(task_factory):
    task = task_factory()
    task._monitor_volume_triggers = True
    task._keyboard.getKeys.return_value = [
        SimpleNamespace(name='t', rt=0.5), SimpleNamespace(name='left', rt=0.6),
    ]
    keys = StroopTask.get_keys(task, key_list=['left'])
    assert [key.name for key in keys] == ['left']
    assert task.volume_triggers == [0.5]


def test_response_from_last_displayed_frame_is_recorded(task_factory):
    task = task_factory()
    trial = task._schedule[0]
    sent = False

    def keys(key_list=None):
        nonlocal sent
        if key_list and not sent and task.clock.time >= trial['fixation_onset']:
            sent = True
            return [SimpleNamespace(name=task._color_to_key[trial['ink_color']],
                                    rt=trial['fixation_onset'] - 0.001)]
        return []

    task.get_keys = keys
    row = task.run_trial(trial, 0, 0, task.block_sequence[0])
    assert row['correct'] == 1
    assert row['RT'] is not None


@pytest.mark.parametrize('mode', ['pc', 'fmri'])
@pytest.mark.parametrize('training', [False, True])
def test_reused_trigger_keyboard_uses_task_clock(task_factory, monkeypatch, mode, training):
    # PsychoPy may return an existing keyboard device and ignore the clock
    # constructor argument. Its previous clock started before the task.
    class ReusedKeyboard:
        def __init__(self):
            self.clock = SimpleNamespace(getTime=lambda: task.clock.time + 60.0)
            self.sent = False

        def clearEvents(self):
            pass

        def getKeys(self, keyList=None, waitRelease=False):
            trial = task._schedule[0]
            key = task._color_to_key[trial['ink_color']]
            if (not self.sent and key in (keyList or [])
                    and task.clock.time >= trial['onset'] + 0.3):
                self.sent = True
                return [SimpleNamespace(name=key, rt=self.clock.getTime())]
            return []

    device = ReusedKeyboard()
    monkeypatch.setattr('tasks.base.keyboard', SimpleNamespace(Keyboard=lambda **kwargs: device))
    task = task_factory('training' if training else 'A', mode=mode)
    task.get_keys = StroopTask.get_keys.__get__(task, StroopTask)
    if training:
        task.wait_for_trigger()
    trial = task._schedule[0]
    record = task.run_trial(trial, 0, 0, task.block_sequence[0])
    assert record['response'] == task._color_to_key[trial['ink_color']]
    assert record['correct'] == 1
    assert 0.25 <= record['RT'] <= 0.35


def test_discovery_tracks_all_buttons_but_only_three_are_active(task_factory):
    task = task_factory('training', mode='fmri')
    sent = False

    def keys(key_list=None):
        nonlocal sent
        if not sent:
            sent = True
            return [SimpleNamespace(name=name, rt=task.clock.time) for name in 'bygr']
        return []

    task.get_keys = keys
    task.run_rest('initial')
    assert [row['key'] for row in task._discovery_presses] == list('bygr')
    assert [row['active'] for row in task._discovery_presses] == [True, True, True, False]
    assert set(task._training_view.flash_until) == {0, 1, 2, 3}
    assert abs(task.clock.time - 20.0) < 2 / 60


def test_acquisition_never_draws_color_hints(task_factory):
    task = task_factory()
    assert task._training_view is None
    view = MagicMock()
    task._training_view = view
    task.run_trial(task._schedule[0], 0, 0, task.block_sequence[0])
    task.run_rest('final')
    assert not view.mock_calls


def test_memory_stage_does_not_display_box_or_mapping(task_factory):
    task = task_factory('training')
    task._training_view.draw_box = MagicMock()
    trial = task._schedule[18]
    record = task.run_trial(trial, 0, 18, task.block_sequence[0])
    task._training_view.draw_box.assert_not_called()
    assert record['mapping_visible'] == 0 and record['feedback_enabled'] == 1
    assert record['stimulus_kind'] == 'patch' and record['word'] == ''


def test_stroop_familiarisation_has_no_hints_or_feedback(task_factory):
    task = task_factory('training')
    task._training_view.draw_box = MagicMock()
    trial = task._schedule[36]
    record = task.run_trial(trial, 0, 36, task.block_sequence[0])
    task._training_view.draw_box.assert_not_called()
    task._feedback.draw.assert_not_called()
    assert record['mapping_visible'] == record['feedback_enabled'] == 0
    assert record['stimulus_kind'] == 'word' and record['planned_duration'] == 1.2


def test_full_training_records_acquisition_report(task_factory):
    task = task_factory('training')
    task.show_text_and_wait = lambda text: None
    saved = task.run()
    report_path = saved.with_name(saved.name.replace('_events.tsv', '_training_report.json'))
    report = json.loads(report_path.read_text())
    assert report['complete'] and not report['acquired']  # no simulated participant responses
    assert report['phases']['memory_mapping']['n_trials'] == 18
    assert report['phases']['stroop']['n_trials'] == 9


def test_run_logs_condition_summary_once_after_acquisition(task_factory):
    task = task_factory()
    task.show_text_and_wait = lambda text: None
    task.wait_for_trigger = lambda: task.clock.reset()
    saved = task.run()
    assert saved.exists() and len(task.data_writer.records) == 75
    lines = [call.args[0] for call in task.logger.log.call_args_list]
    summaries = [line for line in lines if line.startswith('BILAN STROOP')]
    assert len(summaries) == 1 and '75/75 essais acquis' in summaries[0]
    assert any(line.startswith('Incongruent - Congruent : TR n/a') for line in lines)
