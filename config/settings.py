"""Pilot settings: four independent acquisitions per subject, separate practice recordings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config.constants import DATA_DIR
from config.stroop_designs import inclusion_number, run_for_design


@dataclass
class ExperimentSettings:
    participant_id: str
    run: str = '01'
    scanner_name: str = 'pc'
    mode: str = 'pc'
    fullscreen: bool = True
    screen_index: int = 0
    save_data: bool = True
    data_root: Path = field(default_factory=lambda: DATA_DIR)

    def __post_init__(self):
        # Normalize leading zeros so CLI and menu identify the same subject.
        self.participant_id = f'{inclusion_number(self.participant_id):03d}'

    @property
    def subject_dir(self) -> Path:
        return self.data_root / f'sub-{self.participant_id}'

    def task_dir(self, task_name: str = 'stroop') -> Path:
        return self.subject_dir / task_name

    def log_dir(self) -> Path:
        return self.subject_dir / 'logs'

    def base_name(self, task_name: str, design_id: int | str,
                  run: str | None = None) -> str:
        run_str = f'{int(run if run is not None else self.run):02d}'
        return (f'sub-{self.participant_id}'
                f'_task-{task_name}_design-{design_id}_run-{run_str}')

    def resolve_run(self, task_name: str, design_id: str, max_runs: int = 9999) -> str:
        directory = self.task_dir(task_name)
        if design_id == 'training':
            # Practice has its own numbering and never consumes an acquisition run.
            for number in range(1, max_runs + 1):
                run = f'{number:02d}'
                stem = self.base_name(task_name, design_id, run)
                if not any(directory.glob(f'{stem}_*')):
                    return run
            raise ValueError('Trop d’entraînements déjà enregistrés.')
        run = f'{run_for_design(design_id):02d}'
        if any('_design-training_' not in path.name
               for path in directory.glob(f'*_run-{run}_*')):
            raise FileExistsError(
                f'Le run {run} du sujet {self.participant_id} existe déjà. '
                'Les données existantes sont conservées.'
            )
        return run
