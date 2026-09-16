"""Online query embedding, vector search, and optional reranking."""

from __future__ import annotations

from dataclasses import dataclass
import math
from time import perf_counter
from typing import Mapping, Protocol, Sequence

from embeddings.base import Embedder, EmbeddingValidationError
from retrieval.reranker import Reranker, RetrievalCandidate
from retrieval.vector_store import SearchResult


class VectorSearcher(Protocol):
    dimension: int

    def search(
        self, query_vector: Sequence[float], *, limit: int = 10
    ) -> Sequence[SearchResult]: ...


@dataclass(frozen=True, slots=True)
class RetrievalLatency:
    embedding_ms: float
    search_ms: float
    reranking_ms: float
    total_ms: float

    def __post_init__(self) -> None:
        values = (
            self.embedding_ms,
            self.search_ms,
            self.reranking_ms,
            self.total_ms,
        )
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("retrieval latency values must be non-negative")
        if any(value > self.total_ms for value in values[:-1]):
            raise ValueError("retrieval component latency cannot exceed total latency")


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    chunks: tuple[RetrievalCandidate, ...]
    latency: RetrievalLatency

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunks", tuple(self.chunks))


RetrievalChunk = RetrievalCandidate
RetrievalContext = RetrievalResult


def _elapsed_ms(started: float, finished: float) -> float:
    return max(0.0, (finished - started) * 1_000)


def _candidate_from_search(result: SearchResult) -> RetrievalCandidate:
    if not isinstance(result.payload, Mapping):
        raise ValueError(f"search payload for {result.chunk_id!r} must be a mapping")
    if "text" not in result.payload:
        raise ValueError(f"search payload for {result.chunk_id!r} is missing text")
    if "metadata" not in result.payload:
        raise ValueError(f"search payload for {result.chunk_id!r} is missing metadata")
    return RetrievalCandidate(
        chunk_id=result.chunk_id,
        text=result.payload["text"],
        score=result.score,
        metadata=result.payload["metadata"],
    )


def _validate_reranked(
    original: tuple[RetrievalCandidate, ...],
    reranked: Sequence[RetrievalCandidate],
) -> tuple[RetrievalCandidate, ...]:
    output = tuple(reranked)
    if len(output) != len(original):
        raise ValueError("reranker must return every candidate exactly once")
    original_by_id = {candidate.chunk_id: candidate for candidate in original}
    if len(original_by_id) != len(original):
        raise ValueError("vector search returned duplicate candidate IDs")
    if any(not isinstance(candidate, RetrievalCandidate) for candidate in output):
        raise ValueError("reranker must return RetrievalCandidate objects")
    output_ids = tuple(candidate.chunk_id for candidate in output)
    if len(set(output_ids)) != len(output_ids):
        raise ValueError("reranker returned duplicate candidates")
    if set(output_ids) != set(original_by_id):
        raise ValueError("reranker cannot invent or drop candidates")
    if any(candidate != original_by_id[candidate.chunk_id] for candidate in output):
        raise ValueError("reranker may reorder candidates but cannot mutate them")
    return output


class Retriever:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorSearcher,
        *,
        reranker: Reranker | None = None,
        fetch_k: int | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.fetch_k = fetch_k

    def retrieve(
        self, query: str, top_k: int, *, fetch_k: int | None = None
    ) -> RetrievalResult:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
            raise ValueError("top_k must be an integer in 1..20")
        resolved_fetch_k = fetch_k if fetch_k is not None else self.fetch_k
        if resolved_fetch_k is None:
            resolved_fetch_k = top_k
        if (
            not isinstance(resolved_fetch_k, int)
            or isinstance(resolved_fetch_k, bool)
            or resolved_fetch_k < top_k
        ):
            raise ValueError("fetch_k must be an integer greater than or equal to top_k")

        total_started = perf_counter()
        embedding_started = perf_counter()
        batch = self.embedder.embed_batch([query])
        embedding_finished = perf_counter()
        EmbeddingValidationError.validate(
            batch,
            dimension=self.embedder.dimension,
            expected_count=1,
        )

        search_started = perf_counter()
        search_results = tuple(
            self.vector_store.search(batch.vectors[0], limit=resolved_fetch_k)
        )[:resolved_fetch_k]
        search_finished = perf_counter()
        candidates = tuple(_candidate_from_search(result) for result in search_results)
        if len({candidate.chunk_id for candidate in candidates}) != len(candidates):
            raise ValueError("vector search returned duplicate candidate IDs")

        reranking_ms = 0.0
        if self.reranker is not None:
            reranking_started = perf_counter()
            candidates = _validate_reranked(
                candidates, self.reranker.rerank(query, candidates)
            )
            reranking_ms = _elapsed_ms(reranking_started, perf_counter())

        embedding_ms = _elapsed_ms(embedding_started, embedding_finished)
        search_ms = _elapsed_ms(search_started, search_finished)
        total_ms = _elapsed_ms(total_started, perf_counter())
        total_ms = max(
            total_ms,
            embedding_ms,
            search_ms,
            reranking_ms,
            embedding_ms + search_ms + reranking_ms,
        )
        return RetrievalResult(
            query=query,
            chunks=candidates[:top_k],
            latency=RetrievalLatency(
                embedding_ms=embedding_ms,
                search_ms=search_ms,
                reranking_ms=reranking_ms,
                total_ms=total_ms,
            ),
        )


__all__ = [
    "RetrievalChunk",
    "RetrievalContext",
    "RetrievalLatency",
    "RetrievalResult",
    "Retriever",
    "VectorSearcher",
]
