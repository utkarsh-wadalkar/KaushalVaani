"""Validated internal Query/Answer models owned by the RAG boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

SUPPORTED_LOCALES = (
    "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "pa-IN", "od-IN",
)


@dataclass(frozen=True, slots=True)
class Query:
    request_id: str
    query: str
    language: str
    top_k: int = 5
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if self.language not in SUPPORTED_LOCALES:
            raise ValueError("language is unsupported")
        if isinstance(self.top_k, bool) or not 1 <= self.top_k <= 20:
            raise ValueError("top_k must be an integer in 1..20")


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    text: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class Latency:
    total_ms: float
    retrieval_total_ms: float
    embedding_ms: float | None = None
    retrieval_ms: float | None = None
    reranking_ms: float | None = None
    generation_ms: float | None = None
    generation_ttft_ms: float | None = None
    grounding_ms: float | None = None

    def __post_init__(self) -> None:
        values = (self.total_ms, self.retrieval_total_ms, self.embedding_ms,
                  self.retrieval_ms, self.reranking_ms, self.generation_ms,
                  self.generation_ttft_ms, self.grounding_ms)
        if any(
            value is not None and (not math.isfinite(value) or value < 0)
            for value in values
        ):
            raise ValueError("latency values must be finite and non-negative")
        if any(
            value is not None and value > self.total_ms
            for value in values[1:]
        ):
            raise ValueError("latency components cannot exceed total_ms")

    def to_dict(self, *, total_ms: float | None = None) -> dict[str, float | None]:
        return {
            "total_ms": self.total_ms if total_ms is None else total_ms,
            "retrieval_total_ms": self.retrieval_total_ms,
            "embedding_ms": self.embedding_ms,
            "retrieval_ms": self.retrieval_ms,
            "reranking_ms": self.reranking_ms,
            "generation_ms": self.generation_ms,
            "generation_ttft_ms": self.generation_ttft_ms,
            "grounding_ms": self.grounding_ms,
        }


@dataclass(frozen=True, slots=True)
class SerializedAnswer:
    payload: dict[str, Any]
    total_ms: float
    serialization_ms: float
    stage_timings: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class Answer:
    request_id: str
    answer: str
    language: str
    grounded: bool
    sources: tuple[Source, ...]
    latency: Latency
    _request_started_at: float | None = field(default=None, repr=False, compare=False)
    _deadline_ms: float | None = field(default=None, repr=False, compare=False)
    _stage_timings: Mapping[str, float] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not self.answer.strip():
            raise ValueError("answer must be non-empty")
        if self.language not in SUPPORTED_LOCALES:
            raise ValueError("language is unsupported")
        if self._request_started_at is not None and not math.isfinite(self._request_started_at):
            raise ValueError("request start time must be finite")
        if self._deadline_ms is not None and (
            not math.isfinite(self._deadline_ms) or self._deadline_ms <= 0
        ):
            raise ValueError("deadline_ms must be finite and positive")
        timings = {str(name): float(value) for name, value in self._stage_timings.items()}
        if any(not math.isfinite(value) or value < 0 for value in timings.values()):
            raise ValueError("stage timings must be finite and non-negative")
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "_stage_timings", MappingProxyType(timings))

    def serialize(self) -> SerializedAnswer:
        serialization_started = perf_counter()
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "answer": self.answer,
            "language": self.language,
            "grounded": self.grounded,
            "sources": [source.to_dict() for source in self.sources],
            "latency": self.latency.to_dict(),
        }
        finished_at = perf_counter()
        serialization_ms = max(0.0, (finished_at - serialization_started) * 1_000)
        total_ms = max(self.latency.total_ms, serialization_ms)
        if self._request_started_at is not None:
            total_ms = max(
                total_ms,
                (finished_at - self._request_started_at) * 1_000,
            )
        component_values = (
            value for key, value in payload["latency"].items()
            if key != "total_ms" and value is not None
        )
        total_ms = max(total_ms, *component_values)
        if self._deadline_ms is not None and total_ms >= self._deadline_ms:
            raise TimeoutError(
                f"RAG request exceeded {self._deadline_ms:g} ms deadline during serialization"
            )
        payload["latency"]["total_ms"] = total_ms
        stage_timings = dict(self._stage_timings)
        stage_timings["serialization_ms"] = serialization_ms
        return SerializedAnswer(
            payload=payload,
            total_ms=total_ms,
            serialization_ms=serialization_ms,
            stage_timings=MappingProxyType(stage_timings),
        )

    def to_dict(self) -> dict[str, Any]:
        return self.serialize().payload


__all__ = [
    "Answer",
    "Latency",
    "Query",
    "SerializedAnswer",
    "Source",
    "SUPPORTED_LOCALES",
]
