"""Grounding classifier metrics with per-language false-rate reporting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def _summary(rows: list[tuple[bool, bool, str]]) -> dict[str, float | int]:
    tp = sum(predicted and expected for predicted, expected, _ in rows)
    tn = sum(not predicted and not expected for predicted, expected, _ in rows)
    fp = sum(predicted and not expected for predicted, expected, _ in rows)
    fn = sum(not predicted and expected for predicted, expected, _ in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_rate = fp / (fp + tn) if fp + tn else 0.0
    return {
        "count": len(rows),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_rate": false_rate,
    }


def grounding_metrics(
    rows: Iterable[tuple[bool, bool, str]],
) -> dict[str, object]:
    materialized = [(bool(predicted), bool(expected), language) for predicted, expected, language in rows]
    by_language: dict[str, list[tuple[bool, bool, str]]] = defaultdict(list)
    for row in materialized:
        by_language[row[2]].append(row)
    return {
        "overall": _summary(materialized),
        "per_language": {language: _summary(items) for language, items in sorted(by_language.items())},
    }


__all__ = ["grounding_metrics"]
