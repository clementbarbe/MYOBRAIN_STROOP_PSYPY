"""
BaseTask — abstract base class for all fMRI tasks.

Lifecycle
---------
    __init__          resolve design, build stimuli, seed the RNG
    prepare()         build + validate the whole sequence   [before trigger]
    run()
        instructions
        wait_for_trigger()                                  [t = 0]
        rest / blocks / rest
        _finish()     save TSV, write sidecars, cleanup

Pre-generating the sequence removes every allocation and shuffle from
the scanning period, and lets the validation report be inspected before
the participant starts.

ESCAPE aborts cleanly at any point; the finally block always saves.
"""

from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from psychopy import visual
from psychopy.hardware import keyboard

from config.constants import (
    FIXATION_COLOR, INSTRUCTION_COLOR, DEFAULT_FONT,
    FIXATION_HEIGHT, INSTRUCTION_HEIGHT,
    TTL_START_EXP, TTL_END_EXP, TTL_REST_START, TTL_REST_END,
    TTL_INSTRUCTION, END_SCREEN_DURATION, QUIT_KEY,
)
from config.settings import ExperimentSettings
from config.scanners.base import ScannerConfig
from core.clock import ExperimentClock
from core.events import EventBus
from core.exceptions import AbortExperiment
from hardware.manager import HardwareManager
from dataio.logger import ExperimentLogger
from dataio.data_writer import DataWriter
from utils.console import SYM_PAUSE


class BaseTask(ABC):
    """Abstract base for all experimental tasks."""

    TASK_NAME: str = 'base'
    PREGENERATE_TRIALS: bool = False   # True -> build_all_trials() is used

    def __init__(self, win, clock, hardware, data_writer, logger,
                 event_bus, settings, scanner, task_config,
                 design_id: int = 1, seed: int | None = None, **kwargs):

        self.win = win
        self.clock: ExperimentClock = clock
        self.hardware: HardwareManager = hardware
        self.data_writer: DataWriter = data_writer
        self.logger: ExperimentLogger = logger
        self.event_bus: EventBus = event_bus
        self.settings: ExperimentSettings = settings
        self.scanner: ScannerConfig = scanner
        self.task_config = task_config

        self.design_id = design_id
        self.design = self._resolve_design(design_id, kwargs)
        self.block_sequence = deepcopy(self.design.get('blocks', []))

        # ── Reproducibility ──────────────────────────────────────────
        self.seed = seed if seed is not None else random.randrange(2 ** 31)
        self._rng = random.Random(self.seed)

        self._quit_key = QUIT_KEY
        self._audio = None
        self._prepared: list[list] | None = None
        self._validation = None

        self._fixation = visual.TextStim(
            win, text='+', color=FIXATION_COLOR,
            height=FIXATION_HEIGHT, pos=(0, 0))
        self._instruction_stim = visual.TextStim(
            win, text='', color=INSTRUCTION_COLOR,
            height=INSTRUCTION_HEIGHT, pos=(0, 0),
            wrapWidth=1.5, font=DEFAULT_FONT)

        self._keyboard = keyboard.Keyboard(clock=clock.psychopy_clock)
        self._response_keys = dict(scanner.response_keys)
        self._global_trial_idx = 0

        self._setup_stimuli()
        self._log_design_summary()

    # ═════════════════════════════════════════════════════════════════
    # ABSTRACT
    # ═════════════════════════════════════════════════════════════════

    @abstractmethod
    def _setup_stimuli(self) -> None: ...

    @abstractmethod
    def _get_instruction_text(self) -> str: ...

    @abstractmethod
    def _get_block_instruction(self, block_idx: int,
                               block_def: dict) -> str | None: ...

    @abstractmethod
    def run_trial(self, trial_data, block_idx: int, trial_idx: int,
                  block_def: dict, **kwargs) -> dict: ...

    def generate_trials(self, block_def: dict) -> list:
        """On-the-fly generation, for tasks with PREGENERATE_TRIALS = False."""
        raise NotImplementedError

    def build_all_trials(self) -> list[list]:
        """Whole-run generation, for tasks with PREGENERATE_TRIALS = True."""
        raise NotImplementedError

    def validate_sequence(self, blocks: list[list]):
        """Return a ValidationReport, or None to skip validation."""
        return None

    def _print_task_stats(self) -> None: ...

    # ═════════════════════════════════════════════════════════════════
    # PREPARATION — runs before the trigger
    # ═════════════════════════════════════════════════════════════════

    def prepare(self) -> None:
        """Build and validate the complete sequence, then write the sidecar."""
        if not self.PREGENERATE_TRIALS:
            return

        self.logger.log(f"Building sequence (seed={self.seed})...")
        self._prepared = self.build_all_trials()

        n = sum(len(b) for b in self._prepared)
        expected = sum(b['n_trials'] for b in self.block_sequence)
        if n != expected:
            raise ValueError(
                f"Generated {n} trials but the design expects {expected}."
            )

        self._validation = self.validate_sequence(self._prepared)
        if self._validation is not None:
            self._validation.log(self.logger)
            if not self._validation.all_passed:
                for c in self._validation.failures:
                    self.logger.err(f"  CONSTRAINT VIOLATED -> {c.name}")

        self._write_design_sidecar()

    def _write_design_sidecar(self) -> None:
        """Save design, seed and validation report next to the data."""
        try:
            path = (self.settings.task_dir(self.TASK_NAME)
                    / f"{self.settings.base_name(self.TASK_NAME, self.design_id)}"
                      f"_design.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'participant': self.settings.participant_id,
                'session': self.settings.session,
                'run': self.settings.run,
                'task': self.TASK_NAME,
                'design_id': self.design_id,
                'design_name': self.design.get('name', ''),
                'paradigm': self.design.get('paradigm', ''),
                'seed': self.seed,
                'generated_at': datetime.now().isoformat(timespec='seconds'),
                'timing': {
                    k: self.design.get(k) for k in (
                        'fixation_duration', 'stim_duration', 'iti_duration',
                        'iti_min', 'iti_max', 'rest_duration',
                        'instruction_duration', 'pre_block_fixation')
                    if self.design.get(k) is not None
                },
                'blocks': self.block_sequence,
                'validation': (self._validation.to_dict()
                               if self._validation else None),
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self.logger.ok(f"Design sidecar: {path.name}")
        except Exception as e:
            self.logger.warn(f"Sidecar write failed: {e}")

    # ═════════════════════════════════════════════════════════════════
    # AUDIO (lazy)
    # ═════════════════════════════════════════════════════════════════

    @property
    def audio(self):
        if self._audio is None:
            from hardware.audio import AudioManager
            self._audio = AudioManager()
            self.logger.log("AudioManager initialised (lazy).")
        return self._audio

    # ═════════════════════════════════════════════════════════════════
    # DESIGN
    # ═════════════════════════════════════════════════════════════════

    def _resolve_design(self, design_id: int, overrides: dict) -> dict:
        designs = self.task_config.get('designs', {})
        if design_id not in designs:
            raise ValueError(
                f"Design {design_id} not found. Available: {sorted(designs)}")
        d = deepcopy(designs[design_id])
        if 'n_miniblocks' in d and 'miniblock_template' in d:
            tpl = d.pop('miniblock_template')
            d['blocks'] = [deepcopy(tpl) for _ in range(d.pop('n_miniblocks'))]
        for k, v in overrides.items():
            if v is not None and k in d:
                d[k] = v
        if 'block_sequence' in overrides and overrides['block_sequence']:
            d['blocks'] = overrides['block_sequence']
        return d

    def _log_design_summary(self) -> None:
        n = len(self.block_sequence)
        t = sum(b.get('n_trials', 0) for b in self.block_sequence)
        self.logger.ok(
            f"TASK={self.TASK_NAME} DESIGN={self.design_id} "
            f"'{self.design.get('name', '')}' | {n} blocks | {t} trials | "
            f"run={self.settings.run} | seed={self.seed}")

    # ═════════════════════════════════════════════════════════════════
    # KEYBOARD
    # ═════════════════════════════════════════════════════════════════

    def get_keys(self, key_list: list[str] | None = None):
        check = None
        if key_list is not None:
            check = list(key_list)
            if self._quit_key not in check:
                check.append(self._quit_key)
        keys = self._keyboard.getKeys(keyList=check, waitRelease=False)
        if not keys:
            return []
        for k in keys:
            if k.name == self._quit_key:
                raise AbortExperiment(
                    f"Escape pressed at t={self.clock.time:.3f}s")
        return [k for k in keys if k.name in key_list] if key_list else keys

    def flush_keyboard(self) -> None:
        self._keyboard.clearEvents()

    # ═════════════════════════════════════════════════════════════════
    # DISPLAY
    # ═════════════════════════════════════════════════════════════════

    def show_fixation(self, duration: float) -> None:
        self._fixation.draw()
        self.win.flip()
        deadline = self.clock.time + duration
        while self.clock.time < deadline:
            self._fixation.draw()
            self.win.flip()
            self.get_keys(key_list=[])

    def show_text_and_wait(self, text: str) -> None:
        self._instruction_stim.text = text
        while True:
            self._instruction_stim.draw()
            self.win.flip()
            keys = self._keyboard.getKeys(waitRelease=False)
            if keys:
                if any(k.name == self._quit_key for k in keys):
                    raise AbortExperiment("Escape during instructions")
                break
        self.flush_keyboard()

    def show_timed_text(self, text: str, duration: float, stim=None) -> None:
        target = stim or self._instruction_stim
        target.text = text
        target.draw()
        self.win.flip()
        deadline = self.clock.time + duration
        while self.clock.time < deadline:
            target.draw()
            self.win.flip()
            self.get_keys(key_list=[])

    # ═════════════════════════════════════════════════════════════════
    # TRIGGER
    # ═════════════════════════════════════════════════════════════════

    def wait_for_trigger(self) -> None:
        tk = self.scanner.trigger_key
        self._instruction_stim.text = f"Attente trigger [{tk}]..."
        while True:
            self._instruction_stim.draw()
            self.win.flip()
            keys = self._keyboard.getKeys(keyList=[tk, self._quit_key],
                                          waitRelease=False)
            for k in (keys or []):
                if k.name == self._quit_key:
                    raise AbortExperiment("Escape during trigger wait")
                if k.name == tk:
                    self.clock.reset()
                    self.flush_keyboard()
                    self.logger.ok(
                        f"TRIGGER t=0 | {self.clock.trigger_wall_time}")
                    self.hardware.send_trigger(TTL_START_EXP)
                    self.hardware.send_eyetracker_message("START_EXP_t0.000")
                    self.event_bus.publish('trigger_received')
                    return

    # ═════════════════════════════════════════════════════════════════
    # REST / BLOCK
    # ═════════════════════════════════════════════════════════════════

    def run_rest(self, label: str = '', duration: float | None = None) -> None:
        dur = (duration if duration is not None
               else self.design.get('rest_duration', 10.0))
        t = self.clock.time
        print(f"  {SYM_PAUSE} Rest {dur:.1f}s | t={t:.1f}s | {label}")
        self.hardware.send_trigger(TTL_REST_START)
        self.hardware.send_eyetracker_message(f"REST_START_{label}_t{t:.3f}")
        self.show_fixation(dur)
        self.hardware.send_trigger(TTL_REST_END)
        self.hardware.send_eyetracker_message(
            f"REST_END_{label}_t{self.clock.time:.3f}")

    def run_block(self, block_idx: int, block_def: dict) -> None:
        self.logger.log(f"Block {block_idx} START t={self.clock.time:.3f}s")
        self.event_bus.publish('block_start', block_idx=block_idx,
                               block_def=block_def)

        instr = self._get_block_instruction(block_idx, block_def)
        dur = self.design.get('instruction_duration', 3.0)
        if instr and dur > 0:
            self.hardware.send_trigger(TTL_INSTRUCTION)
            self.show_timed_text(instr, dur)

        pre = self.design.get('pre_block_fixation', 0.0)
        if pre > 0:
            self.show_fixation(pre)

        trials = (self._prepared[block_idx] if self._prepared is not None
                  else self.generate_trials(block_def))

        for idx, data in enumerate(trials):
            rec = self.run_trial(data, block_idx=block_idx, trial_idx=idx,
                                 block_def=block_def)
            rec['trial_idx_global'] = self._global_trial_idx
            self._global_trial_idx += 1
            self.data_writer.write_trial(rec)
            self.event_bus.publish('trial_end', record=rec)

        self.event_bus.publish('block_end', block_idx=block_idx,
                               block_def=block_def)
        self.logger.log(f"Block {block_idx} END")

    # ═════════════════════════════════════════════════════════════════
    # RUN
    # ═════════════════════════════════════════════════════════════════

    def run(self) -> Path | None:
        saved = None
        try:
            self.prepare()                     # before anything is shown
            self.show_text_and_wait(self._get_instruction_text())
            self.wait_for_trigger()
            self.run_rest(label='initial')

            n = len(self.block_sequence)
            for i, bdef in enumerate(self.block_sequence):
                self.run_block(i, bdef)
                if i < n - 1:
                    self._run_inter_block(i)

            self.run_rest(label='final')
            self.logger.ok(f"Task {self.TASK_NAME} completed.")

        except AbortExperiment as e:
            self.logger.warn(f"ABORT: {e}")
        except (KeyboardInterrupt, SystemExit):
            self.logger.warn("Interrupted.")
        except Exception as e:
            self.logger.err(f"CRITICAL: {e}")
            import traceback
            traceback.print_exc()
        finally:
            saved = self._finish()
        return saved

    def _run_inter_block(self, i: int) -> None:
        p = self.design.get('paradigm', 'block')
        lo = self.design.get('inter_block_min', 0.0)
        hi = self.design.get('inter_block_max', 0.0)
        if p == 'hybrid' and hi > 0:
            self.run_rest(label=f'jitter_{i}',
                          duration=self._rng.uniform(lo, hi))
        else:
            self.run_rest(label=f'after_block_{i}')

    def _finish(self) -> Path | None:
        t = self.clock.time
        self.logger.log(f"Session end t={t:.1f}s ({t / 60:.1f} min)")

        for fn in (lambda: self.hardware.send_trigger(TTL_END_EXP),
                   lambda: self.hardware.send_eyetracker_message(
                       f"END_EXP_t{t:.3f}")):
            try:
                fn()
            except Exception:
                pass

        try:
            if self.hardware.has_eyetracker:
                self.hardware.stop_eyetracker()
                if self.hardware._eyetracker is not None:
                    self.hardware._eyetracker.transfer_data(
                        str(self.settings.task_dir(self.TASK_NAME)))
        except Exception as e:
            self.logger.warn(f"ET cleanup: {e}")

        if self._audio is not None:
            try:
                self._audio.close()
            except Exception:
                pass

        saved = None
        if self.settings.save_data:
            try:
                saved = self.data_writer.save_final()
            except Exception as e:
                self.logger.err(f"Save failed: {e}")
        try:
            self.data_writer.close()
        except Exception:
            pass

        try:
            if self.data_writer.records:
                self._print_task_stats()
        except Exception as e:
            self.logger.warn(f"Stats failed: {e}")

        try:
            if self.win and not getattr(self.win, '_closed', False):
                self._instruction_stim.text = "Fin de la session.\nMerci."
                self._instruction_stim.draw()
                self.win.flip()
                self.clock.wait(END_SCREEN_DURATION)
        except Exception:
            pass

        self.event_bus.publish('task_end', saved_path=saved)
        return saved

    # ═════════════════════════════════════════════════════════════════
    # RECORD SKELETON
    # ═════════════════════════════════════════════════════════════════

    def _base_record(self, block_idx: int, trial_idx: int,
                     block_def: dict) -> dict:
        return {
            'participant': self.settings.participant_id,
            'session': self.settings.session,
            'run': self.settings.run,
            'task': self.TASK_NAME,
            'design_id': self.design_id,
            'design_name': self.design.get('name', ''),
            'paradigm': self.design.get('paradigm', ''),
            'scanner': self.scanner.name,
            'mode': self.settings.mode,
            'seed': self.seed,
            'trigger_wall_time': self.clock.trigger_wall_time or '',
            'block_idx': block_idx,
            'trial_idx': trial_idx,
            'task_time': round(self.clock.time, 4),
            'wall_time': datetime.now().strftime('%H:%M:%S.%f'),
        }