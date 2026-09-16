"""Embedding contracts and strict offline result validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    dimension: int
    model: str = "unknown"

    def __post_init__(self) -> None:
        EmbeddingValidationError.validate(self, dimension=self.dimension)


class EmbeddingValidationError(ValueError):
    """Raised when an embedding result is malformed or unsafe to index."""

    @staticmethod
    def validate(
        result: EmbeddingBatch | Sequence[Sequence[float]],
        *,
        dimension: int,
        expected_count: int | None = None,
    ) -> None:
        vectors = result.vectors if isinstance(result, EmbeddingBatch) else result
        if dimension <= 0:
            raise EmbeddingValidationError("embedding dimension must be positive")
        if expected_count is not None and len(vectors) != expected_count:
            raise EmbeddingValidationError(
                f"expected {expected_count} vectors, got {len(vectors)}"
            )
        for vector in vectors:
            if len(vector) != dimension:
                raise EmbeddingValidationError(
                    f"expected dimension {dimension}, got {len(vector)}"
                )
            try:
                finite = all(math.isfinite(float(value)) for value in vector)
            except (TypeError, ValueError, OverflowError) as error:
                raise EmbeddingValidationError(
                    "embedding values must be finite numbers"
                ) from error
            if not finite:
                raise EmbeddingValidationError("embedding values must be finite numbers")


class Embedder(Protocol):
    dimension: int
    model_name: str
    config: Mapping[str, Any]

    def embed_batch(self, texts: Sequence[str]) -> EmbeddingBatch: ...
