"""Opt-in PsychoPy import shim for logic tests on hosts without PsychoPy.

This does not simulate a display, keyboard, or physical scanner.
Enable with STROOP_HEADLESS_TESTS=1; runtime code never imports it.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock


def install():
    psychopy = ModuleType('psychopy')
    psychopy.__path__ = []
    psychopy.visual = MagicMock()
    psychopy.monitors = MagicMock()
    psychopy.core = MagicMock()
    hardware = ModuleType('psychopy.hardware')
    hardware.__path__ = []
    hardware.keyboard = MagicMock()
    psychopy.hardware = hardware
    sys.modules.update({
        'psychopy': psychopy,
        'psychopy.hardware': hardware,
        'psychopy.hardware.keyboard': hardware.keyboard,
    })
