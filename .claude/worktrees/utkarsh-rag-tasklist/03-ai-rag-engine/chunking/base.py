"""Common immutable types for offline document chunking."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from ingestion.metadata import CanonicalDocument, DocumentMetadata


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    language: str
    source: str
    metadata: DocumentMetadata
    chunk_index: int
    start_char: int
    end_char: int
    strategy_name: str
    strategy_config_id: str
    overlap_chars: int = 0


class ChunkingStrategy(Protocol):
    name: str

    @property
    def config_id(self) -> str: ...

    def chunk(self, document: CanonicalDocument) -> tuple[Chunk, ...]: ...


def build_chunk(
    document: CanonicalDocument,
    *,
    text: str,
    chunk_index: int,
    start_char: int,
    end_char: int,
    strategy_name: str,
    strategy_config_id: str,
    overlap_chars: int = 0,
) -> Chunk:
    identity = {
        "document_id": document.document_id,
        "strategy_name": strategy_name,
        "strategy_config_id": strategy_config_id,
        "chunk_index": chunk_index,
        "start_char": start_char,
        "end_char": end_char,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return Chunk(
        chunk_id=f"chunk_{hashlib.sha256(encoded).hexdigest()[:24]}",
        document_id=document.document_id,
        text=text,
        language=document.language,
        source=document.source,
        metadata=document.metadata,
        chunk_index=chunk_index,
        start_char=start_char,
        end_char=end_char,
        strategy_name=strategy_name,
        strategy_config_id=strategy_config_id,
        overlap_chars=overlap_chars,
    )
