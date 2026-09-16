"""Relevance floor applied before any generation call."""

from __future__ import annotations

from retrieval.reranker import RetrievalCandidate


class NoRelevantContextError(ValueError):
    code = "NO_RELEVANT_CONTEXT"


def filter_relevant(
    candidates: tuple[RetrievalCandidate, ...] | list[RetrievalCandidate], *, floor: float
) -> tuple[RetrievalCandidate, ...]:
    if floor < -1 or floor > 1:
        raise ValueError("relevance floor must be between -1 and 1")
    selected = tuple(candidate for candidate in candidates if candidate.score >= floor)
    if not selected:
        raise NoRelevantContextError("no retrieved context passed the relevance floor")
    return selected
