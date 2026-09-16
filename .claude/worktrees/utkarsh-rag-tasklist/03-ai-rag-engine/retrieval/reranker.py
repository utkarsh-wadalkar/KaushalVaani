"""Small injected reranking contracts and deterministic local fixtures."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _immutable_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise ValueError("candidate metadata must be a mapping")
    return _freeze(values)


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    chunk_id: str
    text: str
    score: float
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.chunk_id, str) or not self.chunk_id:
            raise ValueError("candidate chunk_id must be a non-empty string")
        if not isinstance(self.text, str):
            raise ValueError("candidate text must be a string")
        try:
            score = float(self.score)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("candidate score must be finite") from error
        if not math.isfinite(score):
            raise ValueError("candidate score must be finite")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "metadata", _immutable_mapping(self.metadata))


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate]
    ) -> Sequence[RetrievalCandidate]: ...


class DeterministicFixtureReranker:
    """Non-production ID-priority reranker for deterministic tests/benchmarks."""

    label = "deterministic non-production fixture reranker"

    def __init__(self, preferred_ids: Mapping[str, Sequence[str]] | None = None) -> None:
        self._preferred_ids = {
            query: tuple(chunk_ids)
            for query, chunk_ids in (preferred_ids or {}).items()
        }

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate]
    ) -> tuple[RetrievalCandidate, ...]:
        original = tuple(candidates)
        priority = {
            chunk_id: position
            for position, chunk_id in enumerate(self._preferred_ids.get(query, ()))
        }
        original_position = {
            candidate.chunk_id: position for position, candidate in enumerate(original)
        }
        return tuple(
            sorted(
                original,
                key=lambda candidate: (
                    priority.get(candidate.chunk_id, len(priority)),
                    original_position[candidate.chunk_id],
                ),
            )
        )


__all__ = ["DeterministicFixtureReranker", "Reranker", "RetrievalCandidate"]
