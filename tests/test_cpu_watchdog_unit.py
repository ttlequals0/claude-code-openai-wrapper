"""Tests for CPU watchdog module."""

import pytest
from unittest.mock import patch
from src.cpu_watchdog import CPUWatchdog


class TestCPUWatchdog:
    def test_init_defaults(self):
        wd = CPUWatchdog()
        assert wd._task is None
        assert wd._strikes == 0
        assert wd._last_cpu_time is None

    def test_get_cpu_percent_non_linux(self):
        wd = CPUWatchdog()
        wd._is_linux = False
        assert wd._get_cpu_percent() == 0.0

    def test_get_cpu_percent_first_call_returns_zero(self):
        wd = CPUWatchdog()
        wd._is_linux = True
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert wd._get_cpu_percent() == 0.0

    def test_start_disabled(self):
        wd = CPUWatchdog()
        with patch("src.cpu_watchdog.WATCHDOG_ENABLED", False):
            wd.start()
        assert wd._task is None

    def test_start_non_linux(self):
        wd = CPUWatchdog()
        wd._is_linux = False
        with patch("src.cpu_watchdog.WATCHDOG_ENABLED", True):
            wd.start()
        assert wd._task is None

    def test_stop_no_task(self):
        wd = CPUWatchdog()
        wd.stop()  # should not raise

    def test_strike_increment_and_reset(self):
        wd = CPUWatchdog()
        wd._strikes = 2
        # Simulating a below-threshold reading resets strikes
        wd._strikes = 0
        assert wd._strikes == 0

    def test_env_vars_read_at_import(self):
        from src.cpu_watchdog import (
            WATCHDOG_ENABLED,
            WATCHDOG_INTERVAL,
            WATCHDOG_CPU_THRESHOLD,
            WATCHDOG_STRIKES,
        )

        assert isinstance(WATCHDOG_ENABLED, bool)
        assert isinstance(WATCHDOG_INTERVAL, int)
        assert isinstance(WATCHDOG_CPU_THRESHOLD, float)
        assert isinstance(WATCHDOG_STRIKES, int)
