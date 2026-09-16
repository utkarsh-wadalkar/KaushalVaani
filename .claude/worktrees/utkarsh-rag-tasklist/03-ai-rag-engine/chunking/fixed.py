"""Deterministic fixed-character chunking baseline."""

from __future__ import annotations

from dataclasses import dataclass

from chunking.base import Chunk, build_chunk
from ingestion.metadata import CanonicalDocument


@dataclass(frozen=True, slots=True)
class FixedChunkingStrategy:
    max_chars: int
    overlap_chars: int = 0
    name: str = "fixed"

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        if not 0 <= self.overlap_chars < self.max_chars:
            raise ValueError("overlap_chars must satisfy 0 <= overlap_chars < max_chars")

    @property
    def config_id(self) -> str:
        return f"max_chars={self.max_chars};overlap_chars={self.overlap_chars}"

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        start = 0
        step = self.max_chars - self.overlap_chars
        while start < len(document.text):
            end = min(start + self.max_chars, len(document.text))
            chunks.append(
                build_chunk(
                    document,
                    text=document.text[start:end],
                    chunk_index=len(chunks),
                    start_char=start,
                    end_char=end,
                    strategy_name=self.name,
                    strategy_config_id=self.config_id,
                    overlap_chars=0 if not chunks else self.overlap_chars,
                )
            )
            if end == len(document.text):
                break
            start += step
        return tuple(chunks)
