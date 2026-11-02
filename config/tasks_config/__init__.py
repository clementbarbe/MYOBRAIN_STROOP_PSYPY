"""Strict loading of the Stroop settings; invalid files must stop a run."""

from pathlib import Path


def load_task_config(task_name: str = 'stroop', config_dir: Path | None = None) -> dict:
    if task_name != 'stroop':
        raise ValueError(f'Tâche inconnue : {task_name}')
    import yaml

    path = (config_dir or Path(__file__).parent) / 'stroop.yaml'
    with path.open(encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or not config.get('designs'):
        raise ValueError(f'Configuration Stroop invalide : {path}')
    return config
