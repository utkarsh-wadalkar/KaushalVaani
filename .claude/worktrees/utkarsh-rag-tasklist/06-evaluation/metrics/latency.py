"""Deterministic percentile aggregation for latency benchmark reports."""

from __future__ import annotations

import math
from collections.abc import Iterable


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight


def percentile_report(latencies_ms: Iterable[float]) -> dict[str, float | int]:
    values = tuple(sorted(float(value) for value in latencies_ms))
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("latencies must be finite and non-negative")
    return {
        "count": len(values),
        "p50": _percentile(values, 50),
        "p70": _percentile(values, 70),
        "p95": _percentile(values, 95),
        "p100": _percentile(values, 100),
    }


__all__ = ["percentile_report"]
