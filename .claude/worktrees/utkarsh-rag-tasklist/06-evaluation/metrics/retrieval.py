"""Dependency-free exact retrieval quality metrics and aggregation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


def _validate_ranked_ids(ranked_ids: Sequence[str], k: int) -> tuple[str, ...]:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")
    ranked = tuple(ranked_ids)
    if len(set(ranked)) != len(ranked):
        raise ValueError("ranked IDs must not contain duplicates")
    return ranked


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    ranked = _validate_ranked_ids(ranked_ids, k)
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def mrr_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    ranked = _validate_ranked_ids(ranked_ids, k)
    relevant = set(relevant_ids)
    for rank, chunk_id in enumerate(ranked[:k], start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def _validated_gains(relevance_judgments: Mapping[str, float]) -> dict[str, float]:
    gains: dict[str, float] = {}
    for chunk_id, raw_gain in relevance_judgments.items():
        try:
            gain = float(raw_gain)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("relevance gain must be a finite non-negative number") from error
        if not math.isfinite(gain) or gain < 0:
            raise ValueError("relevance gain must be a finite non-negative number")
        gains[chunk_id] = gain
    return gains


def _dcg(gains: Sequence[float]) -> float:
    try:
        return sum(
            (2**gain - 1) / math.log2(rank + 1)
            for rank, gain in enumerate(gains, start=1)
        )
    except OverflowError as error:
        raise ValueError("relevance gain is too large for nDCG") from error


def ndcg_at_k(
    ranked_ids: Sequence[str], relevance_judgments: Mapping[str, float], k: int
) -> float:
    ranked = _validate_ranked_ids(ranked_ids, k)
    gains = _validated_gains(relevance_judgments)
    observed = _dcg([gains.get(chunk_id, 0.0) for chunk_id in ranked[:k]])
    ideal = _dcg(sorted(gains.values(), reverse=True)[:k])
    return observed / ideal if ideal else 0.0


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    query_locale: str
    evidence_locale: str
    ranked_ids: tuple[str, ...]
    relevance_judgments: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ranked_ids", tuple(self.ranked_ids))
        object.__setattr__(
            self, "relevance_judgments", dict(self.relevance_judgments)
        )


def _summarize(cases: Sequence[RetrievalEvaluationCase], k: int) -> dict[str, float | int]:
    if not cases:
        return {
            "count": 0,
            "recall_at_k": 0.0,
            "mrr_at_k": 0.0,
            "ndcg_at_k": 0.0,
        }
    values = [
        (
            recall_at_k(case.ranked_ids, set(case.relevance_judgments), k),
            mrr_at_k(case.ranked_ids, set(case.relevance_judgments), k),
            ndcg_at_k(case.ranked_ids, case.relevance_judgments, k),
        )
        for case in cases
    ]
    count = len(values)
    return {
        "count": count,
        "recall_at_k": sum(value[0] for value in values) / count,
        "mrr_at_k": sum(value[1] for value in values) / count,
        "ndcg_at_k": sum(value[2] for value in values) / count,
    }


def aggregate_retrieval_metrics(
    cases: Sequence[RetrievalEvaluationCase], *, k: int
) -> dict[str, object]:
    materialized = tuple(cases)
    _validate_ranked_ids((), k)
    monolingual = tuple(
        case for case in materialized if case.query_locale == case.evidence_locale
    )
    cross_lingual = tuple(
        case for case in materialized if case.query_locale != case.evidence_locale
    )
    locales = sorted({case.query_locale for case in materialized})
    return {
        "k": k,
        "overall": _summarize(materialized, k),
        "monolingual": _summarize(monolingual, k),
        "cross_lingual": _summarize(cross_lingual, k),
        "per_query_locale": {
            locale: _summarize(
                tuple(case for case in materialized if case.query_locale == locale), k
            )
            for locale in locales
        },
    }


aggregate_metrics = aggregate_retrieval_metrics


__all__ = [
    "RetrievalEvaluationCase",
    "aggregate_retrieval_metrics",
    "aggregate_metrics",
    "mrr_at_k",
    "ndcg_at_k",
    "recall_at_k",
]
