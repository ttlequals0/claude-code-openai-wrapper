"""CPU watchdog for detecting and recovering from epoll busy-loops."""

import asyncio
import logging
import os
import signal
import sys
import time

logger = logging.getLogger(__name__)

# Configurable via environment variables
WATCHDOG_ENABLED = os.getenv("WATCHDOG_ENABLED", "false").lower() == "true"
WATCHDOG_INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "30"))
WATCHDOG_CPU_THRESHOLD = float(os.getenv("WATCHDOG_CPU_THRESHOLD", "80"))
WATCHDOG_STRIKES = int(os.getenv("WATCHDOG_STRIKES", "3"))


class CPUWatchdog:
    def __init__(self):
        self._task = None
        self._strikes = 0
        self._last_cpu_time = None
        self._last_wall_time = None
        self._is_linux = sys.platform.startswith("linux")

    def _get_cpu_percent(self):
        """Read CPU usage from /proc/self/stat. Returns 0-100 float."""
        if not self._is_linux:
            return 0.0
        try:
            with open("/proc/self/stat") as f:
                fields = f.read().split()
            # fields[13] = utime, fields[14] = stime (in clock ticks)
            cpu_time = int(fields[13]) + int(fields[14])
            wall_time = time.monotonic()
            ticks_per_sec = os.sysconf("SC_CLK_TCK")

            if self._last_cpu_time is not None:
                cpu_delta = (cpu_time - self._last_cpu_time) / ticks_per_sec
                wall_delta = wall_time - self._last_wall_time
                if wall_delta > 0:
                    percent = (cpu_delta / wall_delta) * 100.0
                else:
                    percent = 0.0
            else:
                percent = 0.0

            self._last_cpu_time = cpu_time
            self._last_wall_time = wall_time
            return percent
        except (FileNotFoundError, IndexError, ValueError, OSError):
            return 0.0

    async def _loop(self):
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL)
            try:
                cpu = self._get_cpu_percent()
                if cpu > WATCHDOG_CPU_THRESHOLD:
                    self._strikes += 1
                    logger.warning(
                        f"CPU watchdog: {cpu:.1f}% > {WATCHDOG_CPU_THRESHOLD}% "
                        f"(strike {self._strikes}/{WATCHDOG_STRIKES})"
                    )
                    if self._strikes >= WATCHDOG_STRIKES:
                        logger.error(
                            f"CPU watchdog: {WATCHDOG_STRIKES} consecutive strikes, "
                            f"sending SIGTERM for clean restart"
                        )
                        os.kill(os.getpid(), signal.SIGTERM)
                        return
                else:
                    if self._strikes > 0:
                        logger.info(f"CPU watchdog: {cpu:.1f}% -- strikes reset")
                    self._strikes = 0
            except Exception as e:
                logger.debug(f"CPU watchdog check failed: {e}")

    def start(self):
        if not WATCHDOG_ENABLED:
            logger.info("CPU watchdog disabled (set WATCHDOG_ENABLED=true to enable)")
            return
        if not self._is_linux:
            logger.info("CPU watchdog skipped (Linux-only, use in Docker)")
            return
        logger.info(
            f"CPU watchdog started: interval={WATCHDOG_INTERVAL}s, "
            f"threshold={WATCHDOG_CPU_THRESHOLD}%, strikes={WATCHDOG_STRIKES}"
        )
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("CPU watchdog stopped")


cpu_watchdog = CPUWatchdog()
