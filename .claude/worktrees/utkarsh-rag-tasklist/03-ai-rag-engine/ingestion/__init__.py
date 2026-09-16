"""Dataset ingestion primitives for the EchoQuery RAG engine."""

from .loader import (
    DatasetSchemaError,
    iter_documents,
    iter_parquet_records,
    normalize_record,
    write_documents_jsonl,
)
from .metadata import CanonicalDocument, DocumentMetadata, MSMarcoRecord

__all__ = [
    "CanonicalDocument",
    "DatasetSchemaError",
    "DocumentMetadata",
    "MSMarcoRecord",
    "iter_documents",
    "iter_parquet_records",
    "normalize_record",
    "write_documents_jsonl",
]
