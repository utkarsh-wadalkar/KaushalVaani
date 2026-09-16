"""Dependency-free deterministic embedding providers for tests and fixtures."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from .base import Embedder, EmbeddingBatch, EmbeddingValidationError


class HashingEmbedder:
    """Deterministic local baseline; suitable for fixtures/tests, not production quality."""

    model_name = "hashing-baseline-test-v1"

    def __init__(self, dimension: int = 64, *, salt: str = "echoquery") -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension
        self.salt = salt

    @property
    def config(self) -> dict[str, object]:
        return {"dimension": self.dimension, "salt": self.salt}

    def embed_batch(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors = tuple(self._embed(text) for text in texts)
        batch = EmbeddingBatch(vectors=vectors, dimension=self.dimension, model=self.model_name)
        EmbeddingValidationError.validate(
            batch,
            dimension=self.dimension,
            expected_count=len(texts),
        )
        return batch

    def _embed(self, text: str) -> tuple[float, ...]:
        raw = hashlib.sha256(f"{self.salt}\0{text}".encode("utf-8")).digest()
        values = []
        for index in range(self.dimension):
            digest = hashlib.sha256(raw + index.to_bytes(4, "big")).digest()
            integer = int.from_bytes(digest[:8], "big")
            values.append((integer / 2**63) - 1.0)
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)


__all__ = ["Embedder", "HashingEmbedder"]
