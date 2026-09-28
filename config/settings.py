"""
Experiment settings — single dataclass for the session.

Filename scheme (BIDS-inspired):
    sub-<pid>_ses-<ses>_task-<task>_design-<id>_run-<nn>_events.tsv

The design ID is part of the name, so running several designs of the
same task in one session never overwrites anything.
The run number is resolved automatically (see resolve_run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config.constants import DATA_DIR


@dataclass
class ExperimentSettings:
    """Session-level configuration."""

    participant_id: str
    session: str = '01'
    run: str = ''                 # '' -> resolved automatically

    scanner_name: str = 'pc'
    mode: str = 'pc'              # 'fmri' | 'pc'
    fullscreen: bool = True
    screen_index: int = 0

    eyetracker_enabled: bool = False
    trigger_output_enabled: bool = False
    save_data: bool = True

    data_root: Path = field(default_factory=lambda: DATA_DIR)

    # ── Directories ──────────────────────────────────────────────────

    @property
    def subject_dir(self) -> Path:
        return (self.data_root
                / f'sub-{self.participant_id}'
                / f'ses-{self.session}')

    def task_dir(self, task_name: str) -> Path:
        return self.subject_dir / task_name

    def log_dir(self) -> Path:
        return self.subject_dir / 'logs'

    # ── Filenames ────────────────────────────────────────────────────

    def base_name(self, task_name: str, design_id: int | str,
                  run: str | None = None) -> str:
        """
        Return the BIDS-like stem, without suffix or extension.

            sub-01_ses-01_task-stroop_design-3_run-02
        """
        run_str = run if run is not None else (self.run or '01')
        return (
            f"sub-{self.participant_id}"
            f"_ses-{self.session}"
            f"_task-{task_name}"
            f"_design-{design_id}"
            f"_run-{run_str}"
        )

    def resolve_run(self, task_name: str, design_id: int | str,
                    max_runs: int = 99) -> str:
        """
        Find the first run number for which NO file already exists.

        Guarantees that a new acquisition never overwrites a previous one,
        even after a crash or an aborted run.
        """
        task_dir = self.task_dir(task_name)
        for n in range(1, max_runs + 1):
            run_str = f"{n:02d}"
            stem = self.base_name(task_name, design_id, run_str)
            existing = list(task_dir.glob(f"{stem}*")) if task_dir.exists() else []
            if not existing:
                return run_str
        raise RuntimeError(
            f"More than {max_runs} runs already exist for "
            f"{task_name} design {design_id}."
        )