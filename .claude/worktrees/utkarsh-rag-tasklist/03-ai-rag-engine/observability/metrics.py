"""Wall-clock latency tracking with explicit component attribution."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Mapping


@dataclass(frozen=True, slots=True)
class LatencySnapshot:
    total_ms: float
    components: Mapping[str, float]


class LatencyTracker:
    def __init__(self, *, clock: Callable[[], float] = perf_counter):
        self.clock = clock
        self._started: float | None = None
        self._components: dict[str, float] = {}

    def start(self) -> None:
        if self._started is not None:
            raise RuntimeError("latency tracker already started")
        self._started = self.clock()

    def record(self, name: str, elapsed_ms: float) -> None:
        if self._started is None:
            raise RuntimeError("latency tracker must be started before recording")
        if elapsed_ms < 0:
            raise ValueError("component latency must be non-negative")
        key = name if name.endswith("_ms") else f"{name}_ms"
        self._components[key] = float(elapsed_ms)

    def finish(self) -> LatencySnapshot:
        if self._started is None:
            raise RuntimeError("latency tracker must be started before finishing")
        total_ms = max(0.0, (self.clock() - self._started) * 1000)
        total_ms = max(total_ms, *self._components.values()) if self._components else total_ms
        return LatencySnapshot(total_ms, dict(self._components))


__all__ = ["LatencySnapshot", "LatencyTracker"]
