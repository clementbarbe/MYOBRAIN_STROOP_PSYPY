"""
Subject / session management and output-path resolution.

The run number is resolved by scanning the task directory, so a new
acquisition can never overwrite an existing one — even after a crash
or an aborted run.
"""

from __future__ import annotations

from pathlib import Path

from config.settings import ExperimentSettings


def ensure_directories(settings: ExperimentSettings,
                       task_name: str) -> Path:
    """Create subject/session/task directory tree. Return the task dir."""
    task_dir = settings.task_dir(task_name)
    task_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir().mkdir(parents=True, exist_ok=True)
    return task_dir


def list_existing_runs(settings: ExperimentSettings, task_name: str,
                       design_id: int | str) -> list[Path]:
    """
    Return the event files already present for this task/design.

    Args:
        settings: session configuration
        task_name: e.g. 'stroop'
        design_id: design identifier used in the filename

    Returns:
        Sorted list of matching *_events.tsv paths (may be empty).
    """
    task_dir = settings.task_dir(task_name)
    if not task_dir.exists():
        return []
    pattern = (
        f"sub-{settings.participant_id}"
        f"_ses-{settings.session}"
        f"_task-{task_name}"
        f"_design-{design_id}"
        f"_run-*_events.tsv"
    )
    return sorted(task_dir.glob(pattern))


def safe_path(path: Path) -> Path:
    """
    Return *path* if free, otherwise append _dup01, _dup02 ...

    Last-resort guard: ExperimentSettings.resolve_run() should already
    prevent collisions, but this protects against races or manual edits.
    """
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 100):
        candidate = path.with_name(f"{stem}_dup{i:02d}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot find a free filename for {path}")


# ── Backward compatibility ───────────────────────────────────────────
# Older code may still import check_existing_data / next_run_number.

def check_existing_data(settings: ExperimentSettings,
                        task_name: str) -> list[Path]:
    """Deprecated. Return all event files for a task, any design."""
    task_dir = settings.task_dir(task_name)
    if not task_dir.exists():
        return []
    return sorted(task_dir.glob('*_events.tsv'))


def next_run_number(settings: ExperimentSettings, task_name: str,
                    design_id: int | str = 1) -> str:
    """Deprecated. Use ExperimentSettings.resolve_run() instead."""
    return settings.resolve_run(task_name, design_id)