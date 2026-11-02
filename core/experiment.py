"""
Experiment orchestrator — uses screen_index from settings.
"""

from __future__ import annotations

import atexit
import signal
import sys
from pathlib import Path

from psychopy import visual, monitors

from config.settings import ExperimentSettings
from config.scanners import get_scanner
from config.scanners.base import ScannerConfig
from config.tasks_config import load_task_config
from config.stroop_designs import design_for_subject
from config.constants import BG_COLOR
from core.clock import ExperimentClock
from core.events import EventBus
from core.exceptions import ConfigError
from hardware.manager import HardwareManager
from dataio.logger import ExperimentLogger
from dataio.data_writer import DataWriter
from tasks.registry import get_task


class Experiment:
    _active_instance = None

    def __init__(self, settings: ExperimentSettings):
        self.settings = settings
        self.scanner: ScannerConfig = get_scanner(settings.scanner_name)
        self.event_bus = EventBus()

        self.logger = ExperimentLogger(settings)
        self.clock = ExperimentClock()
        self.win = self._create_window()
        self.hardware = HardwareManager(
            scanner=self.scanner,
            logger=self.logger,
            enabled=False,
        )

        Experiment._active_instance = self
        atexit.register(Experiment._atexit_cleanup)
        self._install_signal_handlers()

        self.logger.ok(
            f"Experiment | scanner={self.scanner.name} | "
            f"mode={settings.mode} | screen={settings.screen_index}"
        )

    def _create_window(self) -> visual.Window:
        mon = monitors.Monitor(
            name=self.scanner.name,
            width=self.scanner.screen_width_cm,
            distance=self.scanner.viewing_distance_cm,
        )
        mon.setSizePix(list(self.scanner.resolution))

        # Use screen_index from settings (GUI selection)
        screen_idx = self.settings.screen_index

        win = visual.Window(
            size=self.scanner.resolution,
            fullscr=self.settings.fullscreen,
            monitor=mon,
            screen=screen_idx,
            color=BG_COLOR,
            colorSpace='rgb',
            units='norm',
            allowGUI=False,
            waitBlanking=True,
        )

        if self.scanner.flip_horizontal or self.scanner.flip_vertical:
            fh = -1.0 if self.scanner.flip_horizontal else 1.0
            fv = -1.0 if self.scanner.flip_vertical else 1.0
            win.viewScale = [fh, fv]

        return win

    def run_stroop(self, training: bool = False) -> Path | None:
        """Derive the design from the inclusion number; one acquisition per subject."""
        design_id = 'training' if training else design_for_subject(self.settings.participant_id)
        self.settings.run = self.settings.resolve_run('stroop', design_id)
        task_config = load_task_config('stroop')
        task_cls = get_task('stroop')
        if task_cls is None:
            raise ConfigError('Impossible de charger la tâche Stroop.')
        from dataio.subject_handler import ensure_directories
        ensure_directories(self.settings, 'stroop')
        stem = self.settings.base_name('stroop', design_id)
        self.logger.ok(f'Output stem: {stem}')
        data_writer = DataWriter(
            output_dir=self.settings.task_dir('stroop'), filename=stem, logger=self.logger,
        )
        try:
            task = task_cls(
                win=self.win, clock=self.clock, hardware=self.hardware,
                data_writer=data_writer, logger=self.logger, event_bus=self.event_bus,
                settings=self.settings, scanner=self.scanner, task_config=task_config,
                design_id=design_id,
            )
            return task.run()
        finally:
            data_writer.close()

    def cleanup(self) -> None:
        try: self.hardware.close()
        except Exception: pass
        try:
            if self.win and not getattr(self.win, '_closed', True):
                self.win.close()
        except Exception: pass
        try:
            self.logger.ok("Cleanup complete.")
            self.logger.close()
        except Exception: pass
        Experiment._active_instance = None

    @staticmethod
    def _atexit_cleanup():
        inst = Experiment._active_instance
        if inst is not None:
            try: inst.hardware.emergency_shutdown(data_dir=inst.settings.subject_dir)
            except Exception: pass
            try:
                if inst.win and not getattr(inst.win, '_closed', True):
                    inst.win.close()
            except Exception: pass

    def _install_signal_handlers(self):
        def handler(signum, frame):
            self.hardware.emergency_shutdown(data_dir=self.settings.subject_dir)
            try:
                if self.win and not getattr(self.win, '_closed', True):
                    self.win.close()
            except Exception: pass
            sys.exit(1)
        try:
            signal.signal(signal.SIGINT, handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, handler)
        except Exception: pass