"""Tests for ExperimentClock."""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('STROOP_HEADLESS_TESTS') == '1',
    reason='These clock checks require the real PsychoPy installation.',
)


class TestExperimentClock:
    def test_time_starts_near_zero(self):
        from core.clock import ExperimentClock
        clock = ExperimentClock()
        clock.reset()
        assert clock.time < 0.1

    def test_reset_captures_wall_time(self):
        from core.clock import ExperimentClock
        clock = ExperimentClock()
        assert clock.trigger_wall_time is None
        clock.reset()
        assert clock.trigger_wall_time is not None
        assert len(clock.trigger_wall_time) > 10

    def test_time_increases(self):
        from core.clock import ExperimentClock
        import time
        clock = ExperimentClock()
        clock.reset()
        time.sleep(0.05)
        assert clock.time > 0.01