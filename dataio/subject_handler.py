"""Create the directories used by a Stroop acquisition."""

from pathlib import Path

from config.settings import ExperimentSettings


def ensure_directories(settings: ExperimentSettings, task_name: str = 'stroop') -> Path:
    task_dir = settings.task_dir(task_name)
    task_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir().mkdir(parents=True, exist_ok=True)
    return task_dir
