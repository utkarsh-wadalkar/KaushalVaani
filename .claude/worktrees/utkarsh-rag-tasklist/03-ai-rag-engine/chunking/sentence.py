"""Sentence-aware chunking for multilingual canonical documents."""

from __future__ import annotations

from dataclasses import dataclass

from chunking.base import Chunk, build_chunk
from ingestion.metadata import CanonicalDocument


@dataclass(frozen=True, slots=True)
class SentenceChunkingStrategy:
    max_chars: int
    overlap_sentences: int = 0
    name: str = "sentence"

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be greater than zero")
        if self.overlap_sentences < 0:
            raise ValueError("overlap_sentences cannot be negative")

    @property
    def config_id(self) -> str:
        return (
            f"max_chars={self.max_chars};overlap_sentences={self.overlap_sentences}"
        )

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]:
        sentences = sentence_spans(document.text)
        if not sentences:
            return ()

        groups: list[tuple[int, int]] = []
        start_index = 0
        while start_index < len(sentences):
            end_index = start_index
            while end_index < len(sentences):
                candidate_end = sentences[end_index][1]
                candidate_length = candidate_end - sentences[start_index][0]
                if end_index > start_index and candidate_length > self.max_chars:
                    break
                end_index += 1
                if candidate_length > self.max_chars:
                    break
            groups.append((start_index, end_index))

            next_start = end_index
            if self.overlap_sentences and end_index < len(sentences):
                overlap_start = max(start_index, end_index - self.overlap_sentences)
                if sentences[end_index - 1][1] - sentences[overlap_start][0] <= self.max_chars:
                    next_start = overlap_start
            if next_start == start_index:
                next_start = end_index
            start_index = next_start

        chunks: list[Chunk] = []
        for sentence_start, sentence_end in groups:
            start_char = sentences[sentence_start][0]
            end_char = sentences[sentence_end - 1][1]
            overlap_chars = 0
            if chunks:
                overlap_chars = max(0, chunks[-1].end_char - start_char)
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


def sentence_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return source-offset sentence spans while retaining separators verbatim."""

    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    terminators = ".?!।॥\n"
    while index < len(text):
        if text[index] not in terminators:
            index += 1
            continue
        index += 1
        if text[index - 1] == "।" and index < len(text) and text[index] == "।":
            index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        if start < index:
            spans.append((start, index))
        start = index
    if start < len(text):
        spans.append((start, len(text)))
    return tuple(spans)
