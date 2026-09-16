"""Canonical types shared by the MSMARCO-XI ingestion stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


DATASET_NAME = "ai4bharat/MSMARCO-XI"
DATASET_REVISION = "bf5cdc1f26e581e519018e434db14edd1b77602b"


@dataclass(frozen=True, slots=True)
class MSMarcoRecord:
    """Validated representation of one nested MSMARCO-XI parquet row."""

    source_language_tag: str
    target_language_tag: str
    target_language: str
    query_id: int
    query_type: str
    query: str
    english_query: str
    answer: str
    english_answer: str
    english_passages: tuple[str, ...]
    translated_passages: tuple[str, ...]
    selection_labels: tuple[int, ...]
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)
    split: str = "train"
    source_reference: str | None = None
    dataset_name: str = DATASET_NAME
    dataset_revision: str = DATASET_REVISION


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Metadata required to trace a canonical passage back to its source row."""

    dataset_name: str
    dataset_revision: str
    split: str
    source_reference: str | None
    query_id: int
    query_type: str
    source_language_tag: str
    target_language_tag: str
    passage_index: int
    selected: bool
    variant: str
    query: str
    english_query: str
    answer: str
    english_answer: str
    parallel_document_id: str
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    """Dataset-independent document consumed by downstream offline stages."""

    document_id: str
    text: str
    language: str
    source: str
    metadata: DocumentMetadata

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
