"""Injected-scorer semantic chunking candidate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from chunking.base import Chunk, build_chunk
from chunking.sentence import sentence_spans
from ingestion.metadata import CanonicalDocument


SimilarityScorer = Callable[[str, str], float]


@dataclass(frozen=True, slots=True)
class SemanticChunkingStrategy:
    max_chars: int
    similarity_threshold: float
    scorer: SimilarityScorer
    scorer_id: str
    overlap_sentences: int = 0
    name: str = "semantic"

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must satisfy 0 <= threshold <= 1")
        if self.overlap_sentences < 0:
            raise ValueError("overlap_sentences cannot be negative")
        if not self.scorer_id:
            raise ValueError("scorer_id must be non-empty")

    @property
    def config_id(self) -> str:
        return (
            f"max_chars={self.max_chars};threshold={self.similarity_threshold};"
            f"scorer={self.scorer_id};overlap_sentences={self.overlap_sentences}"
        )

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        spans = sentence_spans(document.text)
        if not spans:
            return ()
        groups: list[tuple[int, int]] = []
        group_start = 0
        for index in range(1, len(spans)):
            candidate_end = spans[index][1]
            exceeds_limit = candidate_end - spans[group_start][0] > self.max_chars
            low_similarity = self.scorer(
                document.text[spans[index - 1][0] : spans[index - 1][1]],
                document.text[spans[index][0] : spans[index][1]],
            ) < self.similarity_threshold
            if exceeds_limit or low_similarity:
                groups.append((group_start, index))
                group_start = index
        groups.append((group_start, len(spans)))

        if self.overlap_sentences:
            overlapped: list[tuple[int, int]] = []
            for index, (start, end) in enumerate(groups):
                if index == 0:
                    overlapped.append((start, end))
                    continue
                overlap_start = max(0, start - self.overlap_sentences)
                while overlap_start < start and spans[end - 1][1] - spans[overlap_start][0] > self.max_chars:
                    overlap_start += 1
                overlapped.append((overlap_start, end))
            groups = overlapped

        chunks: list[Chunk] = []
        for start, end in groups:
            start_char, end_char = spans[start][0], spans[end - 1][1]
            overlap_chars = 0 if not chunks else max(0, chunks[-1].end_char - start_char)
            chunks.append(
                build_chunk(
                    document,
                    text=document.text[start_char:end_char],
                    chunk_index=len(chunks),
                    start_char=start_char,
                    end_char=end_char,
                    strategy_name=self.name,
                    strategy_config_id=self.config_id,
                    overlap_chars=overlap_chars,
                )
            )
        return tuple(chunks)
