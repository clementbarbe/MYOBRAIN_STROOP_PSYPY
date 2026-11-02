"""Lazy registration of the Stroop task."""

from tasks.registry import register_lazy, get_task, list_tasks

register_lazy('stroop', 'tasks.stroop', 'StroopTask')

__all__ = ['get_task', 'list_tasks']
