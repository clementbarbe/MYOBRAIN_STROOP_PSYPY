"""Shared Stroop lifecycle: instructions, scanner clock, records and cleanup.

The Stroop subclass reads its entire fixed schedule before t=0. Scanner
pulses and Escape are monitored throughout presentation; acquired trials
are saved even when the run is interrupted.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from psychopy import visual
from psychopy.hardware import keyboard

from config.constants import (
    FIXATION_COLOR, INSTRUCTION_COLOR, DEFAULT_FONT,
    FIXATION_HEIGHT, INSTRUCTION_HEIGHT,
    TTL_START_EXP, TTL_END_EXP, END_SCREEN_DURATION, QUIT_KEY, ADVANCE_KEY,
)
from config.scanners.base import ScannerConfig
from config.settings import ExperimentSettings
from core.clock import ExperimentClock
from core.events import EventBus
from core.exceptions import AbortExperiment, TaskError
from dataio.data_writer import DataWriter
from dataio.logger import ExperimentLogger
from hardware.manager import HardwareManager


class BaseTask(ABC):
    """Display, acquisition and saving helpers for Stroop."""

    # ── Class-level configuration, overridden by subclasses ──────────
    TASK_NAME: str = 'base'

    #: Footer appended to every instruction screen. Defined once here
    #: so that changing ADVANCE_KEY updates every displayed text.
    ADVANCE_PROMPT: str = f"Appuyez sur {ADVANCE_KEY.upper()} pour continuer"

    # ═════════════════════════════════════════════════════════════════
    # CONSTRUCTION
    # ═════════════════════════════════════════════════════════════════

    def __init__(
        self,
        win: visual.Window,
        clock: ExperimentClock,
        hardware: HardwareManager,
        data_writer: DataWriter,
        logger: ExperimentLogger,
        event_bus: EventBus,
        settings: ExperimentSettings,
        scanner: ScannerConfig,
        task_config: dict,
        design_id: str = 'A',
    ):
        """
        Args:
            win:          PsychoPy window, owned by Experiment
            clock:        shared ExperimentClock, t = 0 at the trigger
            hardware:     HardwareManager facade
            data_writer:  DataWriter bound to a collision-free filename
            logger:       ExperimentLogger
            event_bus:    EventBus for optional plugins
            settings:     ExperimentSettings for this session
            scanner:      ScannerConfig for this site
            task_config:  dict loaded from the task YAML
            design_id:    which design of the YAML to run
        """
        # ── Injected dependencies ────────────────────────────────────
        self.win = win
        self.clock = clock
        self.hardware = hardware
        self.data_writer = data_writer
        self.logger = logger
        self.event_bus = event_bus
        self.settings = settings
        self.scanner = scanner
        self.task_config = task_config

        # ── Design ───────────────────────────────────────────────────
        self.design_id = design_id
        self.design = self._resolve_design(design_id)
        self.block_sequence = deepcopy(self.design.get('blocks', []))

        # ── State ────────────────────────────────────────────────────
        self._quit_key = QUIT_KEY
        self._prepared: list[list] | None = None
        self._global_trial_idx = 0

        # ── Scanner volume triggers ──────────────────────────────────
        # Every trigger pulse received after t = 0 is timestamped here,
        # so the TR can be verified offline and the onsets re-referenced
        # should the first pulse turn out to be a dummy scan.
        self.volume_triggers: list[float] = []
        self._monitor_volume_triggers: bool = False

        # ── Shared stimuli ───────────────────────────────────────────
        self._fixation = visual.TextStim(
            win, text='+', color=FIXATION_COLOR,
            height=FIXATION_HEIGHT, pos=(0, 0),
        )
        self._instruction_stim = visual.TextStim(
            win, text='', color=INSTRUCTION_COLOR,
            height=INSTRUCTION_HEIGHT, pos=(0, 0),
            wrapWidth=1.5, font=DEFAULT_FONT,
        )

        # ── Keyboard, sharing the experiment clock ───────────────────
        self._keyboard = keyboard.Keyboard(clock=clock.psychopy_clock)
        # PsychoPy can reuse the device opened by KeyboardTrigger and ignore
        # constructor arguments. Bind its clock explicitly so key.rt uses the
        # same origin as stimulus onsets after the scanner/training reset.
        self._keyboard.clock = clock.psychopy_clock

        # ── Task-specific setup ──────────────────────────────────────
        self._setup_stimuli()
        self._log_design_summary()

    # ═════════════════════════════════════════════════════════════════
    # ABSTRACT INTERFACE
    # ═════════════════════════════════════════════════════════════════

    @abstractmethod
    def _setup_stimuli(self) -> None:
        """Create the task-specific PsychoPy stimuli."""

    @abstractmethod
    def _get_instruction_text(self) -> str:
        """Full instruction screen, shown before the trigger."""

    @abstractmethod
    def run_trial(self, trial_data, block_idx: int, trial_idx: int,
                  block_def: dict, **kwargs) -> dict:
        """
        Execute one trial and return its record.

        The returned dict is written straight to the DataWriter, so it
        must contain every column needed for analysis. Start from
        self._base_record() to get the shared fields, then add the
        canonical analysis columns the task alone can define:
        onset, duration, condition, stimulus, correct_response,
        response, correct and RT.
        """

    def _print_task_stats(self) -> None:
        """Print a task-specific summary at the end of the session."""

    # ═════════════════════════════════════════════════════════════════
    # DESIGN RESOLUTION
    # ═════════════════════════════════════════════════════════════════

    def _resolve_design(self, design_id: str) -> dict:
        designs = self.task_config.get('designs', {})
        if design_id not in designs:
            raise TaskError(f'Design Stroop inconnu : {design_id}')
        design = deepcopy(designs[design_id])
        if len(design.get('blocks', [])) != 1:
            raise TaskError('La tâche Stroop nécessite une seule séquence planifiée.')
        return design

    def _log_design_summary(self) -> None:
        """One-line summary of what is about to run."""
        n_blocks = len(self.block_sequence)
        n_trials = sum(b.get('n_trials', 0) for b in self.block_sequence)
        self.logger.ok(
            f"TASK={self.TASK_NAME} DESIGN={self.design_id} "
            f"'{self.design.get('name', '')}' | "
            f"{n_blocks} blocks | {n_trials} trials | "
            f"run={self.settings.run}"
        )

    # ═════════════════════════════════════════════════════════════════
    # PREPARATION — everything happens before the trigger
    # ═════════════════════════════════════════════════════════════════

    @abstractmethod
    def prepare(self) -> None:
        """Read and validate the Stroop schedule before the scanner pulse."""

    def _wait_for_advance(self, redraw=None) -> None:
        """
        Block until the experimenter presses ADVANCE_KEY.

        Any other key is ignored, which prevents a participant leaning
        on a response button from skipping the instructions. The quit
        key and the volume triggers keep working, since both are
        handled inside get_keys().

        Pending events are discarded on entry, so a key still held from
        the previous screen cannot advance this one immediately.

        Args:
            redraw: callable redrawing the screen on every frame. Pass
                    None when the caller has already drawn the stimuli
                    and the screen only needs to be held.
        """
        self.flush_keyboard()

        while True:
            if redraw is not None:
                redraw()
            self.win.flip()

            if self.get_keys(key_list=[ADVANCE_KEY]):
                self.flush_keyboard()
                return

    def get_keys(self, key_list: list[str] | None = None):
        """
        Poll the keyboard without blocking.

        Two keys are always monitored, whatever key_list contains:

            the quit key      raises AbortExperiment
            the trigger key   appended to self.volume_triggers, so the
                              scanner TR can be verified offline

        Neither is ever returned to the caller, so a scanner pulse can
        never be mistaken for a participant response.

        Args:
            key_list: keys to return; [] to poll for side effects only,
                      None to return everything but the two special keys.

        Returns:
            List of KeyPress objects restricted to key_list.

        Raises:
            AbortExperiment: when the quit key is pressed.
        """
        trigger_key = self.scanner.trigger_key

        check = None
        if key_list is not None:
            check = list(key_list)
            for special in (self._quit_key, trigger_key):
                if special not in check:
                    check.append(special)

        keys = self._keyboard.getKeys(keyList=check, waitRelease=False)
        if not keys:
            return []

        out = []
        for k in keys:
            if k.name == self._quit_key:
                self.logger.warn(
                    f"Quit key pressed at t={self.clock.time:.3f}s"
                )
                raise AbortExperiment(
                    f"Quit key '{self._quit_key}' pressed "
                    f"at t={self.clock.time:.3f}s"
                )

            if k.name == trigger_key:
                # Timestamped with the experiment clock: same reference
                # as every onset, accurate to one refresh interval.
                if self._monitor_volume_triggers:
                    self.volume_triggers.append(round(k.rt, 4))
                continue

            out.append(k)

        if key_list is not None:
            return [k for k in out if k.name in key_list]
        return out

    def flush_keyboard(self) -> None:
        """Discard every pending keyboard event."""
        self._keyboard.clearEvents()

    # ═════════════════════════════════════════════════════════════════
    # DISPLAY HELPERS — frame-accurate, escape-aware
    # ═════════════════════════════════════════════════════════════════

    def show_text_and_wait(self, text: str) -> None:
        """
        Show a text screen and block until ADVANCE_KEY is pressed.

        Used for the instruction screen, before the trigger. The
        response keys are deliberately inert here: only the
        experimenter's key moves the session forward.
        """
        self._instruction_stim.text = text
        self._wait_for_advance(redraw=self._instruction_stim.draw)

    def wait_for_trigger(self) -> None:
        """
        Show a waiting screen, block until the trigger, reset the clock.

        On return, self.clock.time is 0 within one frame and every
        subsequent timestamp is expressed in seconds since this event.
        Volume-trigger logging starts here, so the TR can be checked
        offline against the recorded onsets.
        """
        trigger_key = self.scanner.trigger_key
        self._instruction_stim.text = (
            f"Attente du trigger [{trigger_key}]...\n\n"
            f"([{self._quit_key}] pour annuler)"
        )
        self._instruction_stim.draw()
        self.win.flip()
        self.logger.log(f"Waiting for trigger '{trigger_key}'...")

        while True:
            self._instruction_stim.draw()
            self.win.flip()

            keys = self._keyboard.getKeys(
                keyList=[trigger_key, self._quit_key], waitRelease=False
            )
            for k in (keys or []):
                if k.name == self._quit_key:
                    raise AbortExperiment(
                        "Quit key pressed while waiting for trigger"
                    )

                if k.name == trigger_key:
                    # ── t = 0 ────────────────────────────────────────
                    self.clock.reset()
                    self.flush_keyboard()

                    self._monitor_volume_triggers = True
                    self.volume_triggers = [0.0]      # this very pulse

                    self.logger.ok(
                        f"TRIGGER t=0 | {self.clock.trigger_wall_time} | "
                        f"task={self.TASK_NAME} design={self.design_id} "
                        f"run={self.settings.run}"
                    )
                    self.hardware.send_trigger(TTL_START_EXP)
                    self.hardware.send_eyetracker_message("START_EXP_t0.000")
                    self.event_bus.publish('trigger_received')
                    return

    # ═════════════════════════════════════════════════════════════════
    # REST
    # ═════════════════════════════════════════════════════════════════

    @abstractmethod
    def run_rest(self, label: str = '', duration: float | None = None) -> None:
        """Present the fixation intervals included in the Stroop schedule."""

    def run_block(self, block_idx: int, block_def: dict) -> None:
        if self._prepared is None:
            raise TaskError('La séquence Stroop n’a pas été préparée.')
        self.event_bus.publish('block_start', block_idx=block_idx, block_def=block_def)
        for trial_idx, trial_data in enumerate(self._prepared[block_idx]):
            record = self.run_trial(trial_data, block_idx, trial_idx, block_def)
            self._global_trial_idx += 1
            self.data_writer.write_trial(record)
            self.event_bus.publish('trial_end', record=record)
        self.event_bus.publish('block_end', block_idx=block_idx, block_def=block_def)

    def run(self) -> Path | None:
        """
        Execute the complete session.

        Returns:
            Path to the saved TSV, or None when nothing was acquired.
        """
        saved_path = None

        try:
            self.prepare()                       # may raise TaskError
            self.show_text_and_wait(self._get_instruction_text())
            self.wait_for_trigger()              # t = 0
            self.run_rest(label='initial')

            for block_idx, block_def in enumerate(self.block_sequence):
                self.run_block(block_idx, block_def)

            self.run_rest(label='final')
            self.logger.ok(f"Task {self.TASK_NAME} completed normally.")

        except TaskError as e:
            # The sequence could not be built: nothing was acquired.
            self.logger.err(f"TASK ERROR: {e}")
            print(f"\n  [TASK ERROR] {e}\n")
            self._show_error_screen(str(e))

        except AbortExperiment as e:
            self.logger.warn(f"ABORTED: {e}")
            print(f"\n  [ABORT] {e}\n")

        except (KeyboardInterrupt, SystemExit):
            self.logger.warn("Interrupted from the console.")
            print("\n  [INTERRUPTED]\n")

        except Exception as e:
            self.logger.err(f"CRITICAL: {e}")
            import traceback
            traceback.print_exc()

        finally:
            saved_path = self._finish()

        return saved_path

    def _show_error_screen(self, message: str) -> None:
        """Blocking red screen explaining that no data were acquired."""
        try:
            if not self.win or getattr(self.win, '_closed', False):
                return
            stim = visual.TextStim(
                self.win, color=(1, -0.6, -0.6), height=0.05,
                pos=(0, 0), wrapWidth=1.6, font=DEFAULT_FONT,
                text=(
                    "ERREUR DE TÂCHE\n\n"
                    f"{message}\n\n"
                    "Les essais déjà acquis sont sauvegardés.\n"
                    "Appuyez sur une touche pour quitter."
                ),
            )
            stim.draw()
            self.win.flip()
            self._keyboard.waitKeys(maxWait=60.0)
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════
    # SHUTDOWN — always reached through the finally block
    # ═════════════════════════════════════════════════════════════════

    def _finish(self) -> Path | None:
        """
        End-of-session cleanup.

        Each step is isolated, so one failure cannot prevent the others:
        end markers, eye-tracker transfer, final TSV save,
        sidecars, statistics, end screen.
        """
        t_end = self.clock.time
        self.logger.log(
            f"Session end | t={t_end:.1f}s ({t_end / 60:.1f} min) | "
            f"{self.data_writer.n_trials} trials recorded"
        )

        # ── End markers ──────────────────────────────────────────────
        try:
            self.hardware.send_trigger(TTL_END_EXP)
        except Exception:
            pass
        try:
            self.hardware.send_eyetracker_message(f"END_EXP_t{t_end:.3f}")
        except Exception:
            pass

        # ── Eye-tracker: stop and download before closing ────────────
        try:
            if self.hardware.has_eyetracker:
                self.hardware.stop_eyetracker()
                tracker = getattr(self.hardware, '_eyetracker', None)
                if tracker is not None:
                    tracker.transfer_data(
                        str(self.settings.task_dir(self.TASK_NAME))
                    )
        except Exception as e:
            self.logger.warn(f"Eye-tracker cleanup failed: {e}")

        # ── Final data save ──────────────────────────────────────────
        saved = None
        if self.settings.save_data:
            try:
                saved = self.data_writer.save_final()
            except Exception as e:
                self.logger.err(f"Final save failed: {e}")
        else:
            self.logger.warn("save_data is False — no final file written.")

        try:
            self.data_writer.close()
        except Exception:
            pass

        # ── BIDS events sidecar ──────────────────────────────────────
        if saved is not None:
            try:
                from dataio.events_sidecar import write_events_sidecar
                write_events_sidecar(saved, self.TASK_NAME, self.logger)
            except Exception as e:
                self.logger.warn(f"Events sidecar failed: {e}")

        # ── Volume-trigger report ────────────────────────────────────
        try:
            self._report_volume_triggers()
        except Exception as e:
            self.logger.warn(f"Trigger report failed: {e}")

        # ── Statistics ───────────────────────────────────────────────
        try:
            if self.data_writer.records:
                self._print_task_stats()
        except Exception as e:
            self.logger.warn(f"Statistics failed: {e}")

        # ── End screen ───────────────────────────────────────────────
        try:
            if self.win and not getattr(self.win, '_closed', False):
                self._show_end_screen()
        except Exception:
            pass

        self.event_bus.publish('task_end', saved_path=saved)
        return saved

    def _show_end_screen(self) -> None:
        self._instruction_stim.text = 'Fin de la tâche.\nMerci pour votre participation.'
        self._instruction_stim.draw()
        self.win.flip()
        self.clock.wait(END_SCREEN_DURATION)

    def _report_volume_triggers(self) -> None:
        """
        Summarise the scanner pulses and save them next to the data.

        The measured TR is the median interval between consecutive
        pulses. A stable value confirms that onset = 0 really is the
        start of the acquisition. A first interval much larger than the
        median means the first pulse followed one or more dummy scans,
        and every onset should be shifted accordingly during analysis.
        """
        trig = self.volume_triggers
        if len(trig) < 2:
            self.logger.warn(
                f"Only {len(trig)} scanner trigger(s) logged — "
                f"cannot verify the TR."
            )
            return

        gaps = [round(b - a, 4) for a, b in zip(trig, trig[1:])]
        ordered = sorted(gaps)
        mid = len(ordered) // 2
        tr = (ordered[mid] if len(ordered) % 2
              else (ordered[mid - 1] + ordered[mid]) / 2)

        deviation = max(abs(g - tr) for g in gaps)
        expected = round(self.clock.time / tr) if tr > 0 else 0
        missing = max(0, expected - len(trig))

        self.logger.ok(
            f"Scanner pulses: n={len(trig)} | TR={tr:.4f}s | "
            f"max deviation={deviation * 1000:.0f}ms | "
            f"expected~{expected} | missing~{missing}"
        )
        if deviation > 0.05:
            self.logger.warn(
                f"Irregular pulse intervals, up to "
                f"{deviation * 1000:.0f}ms off the median — "
                f"check the trigger cable."
            )
        if missing > 2:
            self.logger.warn(
                f"About {missing} pulses were not captured. Onsets remain "
                f"valid but the volume count is incomplete."
            )
        if abs(gaps[0] - tr) > 0.05:
            self.logger.warn(
                f"First interval is {gaps[0]:.3f}s against a TR of "
                f"{tr:.3f}s — the first pulse may follow a dummy scan. "
                f"Shift the onsets before modelling."
            )

        payload = {
            'subject': self.settings.participant_id,
            'run': self.settings.run,
            'task': self.TASK_NAME,
            'design_id': self.design_id,
            'trigger_key': self.scanner.trigger_key,
            'trigger_wall_time': self.clock.trigger_wall_time,
            'onset_reference': (
                'first scanner trigger; every onset in the events file is '
                'expressed in seconds since this pulse'
            ),
            'n_triggers': len(trig),
            'tr_measured': round(tr, 4),
            'tr_min': min(gaps),
            'tr_max': max(gaps),
            'max_deviation_from_median': round(deviation, 4),
            'first_interval': gaps[0],
            'n_triggers_expected': expected,
            'n_triggers_missing_estimate': missing,
            'session_duration': round(self.clock.time, 4),
            'trigger_times': trig,
        }

        stem = self.settings.base_name(self.TASK_NAME, self.design_id)
        path = self.settings.task_dir(self.TASK_NAME) / f"{stem}_scantrig.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        self.logger.ok(f"Trigger log: {path.name}")

    # ═════════════════════════════════════════════════════════════════
    # RECORD SKELETON
    # ═════════════════════════════════════════════════════════════════

    def _base_record(self, block_idx: int, trial_idx: int,
                     block_def: dict) -> dict:
        """
        Fields shared by every task.

        The canonical identifiers come first, with the names most
        analysis scripts expect:

            subject   participant identifier
            run       run number, two digits
            trial     1-based index over the whole run

        The subclass adds onset, duration, condition, stimulus,
        correct_response, response, correct and RT, which only it can
        define, then any extra column it needs.
        """
        return {
            # ── Canonical identifiers ────────────────────────────────
            'subject': self.settings.participant_id,
            'run': self.settings.run,
            'trial': self._global_trial_idx + 1,     # 1-based, run-wide
            'task': self.TASK_NAME,

            # ── Design provenance ────────────────────────────────────
            'design_id': self.design_id,
            'design_name': self.design.get('name', ''),
            'paradigm': self.design.get('paradigm', ''),
            'scanner': self.scanner.name,
            'mode': self.settings.mode,

            # ── Position inside the run ──────────────────────────────
            'block': block_idx + 1,                  # 1-based
            'trial_in_block': trial_idx + 1,         # 1-based
            'block_idx': block_idx,                  # 0-based, legacy
            'trial_idx': trial_idx,                  # 0-based, legacy

            # ── Absolute timing, for cross-device alignment ──────────
            'trigger_wall_time': self.clock.trigger_wall_time or '',
            'task_time': round(self.clock.time, 4),
            'wall_time': datetime.now().strftime('%H:%M:%S.%f'),
        }
