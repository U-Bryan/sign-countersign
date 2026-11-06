"""Simulated protocol time, in integer milliseconds.

Protocol checks (TOTP windows, D2 timestamp windows, replay delays) read this clock,
so a 5-minute replay costs no real time. Wall-clock latency is measured separately
with time.perf_counter_ns().
"""
from __future__ import annotations

import threading
import time

BASE_START_MS = 1_794_000_000_000  # a fixed instant in 2026; trials are offset from it


def start_ms_for_seed(seed: int) -> int:
    """Different trials start at different points of the 30-second TOTP cycle."""
    return BASE_START_MS + (seed % 86_400) * 1000


class SimClock:
    def __init__(self, start_ms: int, real_time: bool = True, skew_ms: dict[str, int] | None = None):
        self._start_ms = int(start_ms)
        self._real_time = real_time
        self._t0 = time.perf_counter_ns()
        self._offset_ms = 0
        self._skew_ms = {k: int(v) for k, v in (skew_ms or {}).items()}
        self._lock = threading.Lock()

    def now_ms(self) -> int:
        with self._lock:
            elapsed = (time.perf_counter_ns() - self._t0) // 1_000_000 if self._real_time else 0
            return self._start_ms + elapsed + self._offset_ms

    def agent_now_ms(self, agent: str) -> int:
        return self.now_ms() + self._skew_ms.get(agent, 0)

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("the clock only moves forward")
        with self._lock:
            self._offset_ms += int(round(seconds * 1000))

    def set_skew(self, agent: str, skew_ms: int) -> None:
        with self._lock:
            self._skew_ms[agent] = int(skew_ms)

    @property
    def real_time(self) -> bool:
        return self._real_time
