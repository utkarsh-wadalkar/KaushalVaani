"""Generation boundary with a deterministic fixture and async-ready protocol."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, Sequence

from generation.prompts import build_grounded_prompt
from generation.schemas import Query
from retrieval.reranker import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    text: str
    generation_ms: float
    generation_ttft_ms: float | None = None


class Generator(Protocol):
    def generate(
        self,
        query: Query,
        candidates: Sequence[RetrievalCandidate],
        *,
        timeout_ms: int | None = None,
    ) -> GenerationResponse: ...


class FixtureLLM:
    """Deterministic local generator for tests; not a production model."""

    def __init__(self, answer: str):
        if not answer.strip():
            raise ValueError("fixture answer must be non-empty")
        self.answer = answer

    def generate(
        self,
        query: Query,
        candidates: Sequence[RetrievalCandidate],
        *,
        timeout_ms: int | None = None,
    ) -> GenerationResponse:
        build_grounded_prompt(query, tuple(candidates))
        started = perf_counter()
        return GenerationResponse(self.answer, max(0.0, (perf_counter() - started) * 1000))


class SarvamGenerator:
    """Dependency-injected production boundary; HTTP client is supplied by deployment."""

    def __init__(self, client, *, timeout_ms: int = 150, max_retries: int = 0):
        self.client = client
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries

    def generate(
        self,
        query: Query,
        candidates: Sequence[RetrievalCandidate],
        *,
        timeout_ms: int | None = None,
    ) -> GenerationResponse:
        started = perf_counter()
        resolved_timeout_ms = self.timeout_ms
        if timeout_ms is not None:
            resolved_timeout_ms = min(resolved_timeout_ms, timeout_ms)
        response = self.client.generate(
            prompt=build_grounded_prompt(query, tuple(candidates)),
            language=query.language,
            timeout_ms=resolved_timeout_ms,
            max_retries=self.max_retries,
        )
        text = response if isinstance(response, str) else response["text"]
        return GenerationResponse(text, (perf_counter() - started) * 1000)
