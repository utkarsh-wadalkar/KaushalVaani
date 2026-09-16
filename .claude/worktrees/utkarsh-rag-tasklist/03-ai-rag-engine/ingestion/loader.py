"""Streaming loader for the inspected AI4Bharat MSMARCO-XI schema."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from ingestion.metadata import (
    DATASET_NAME,
    DATASET_REVISION,
    CanonicalDocument,
    DocumentMetadata,
    MSMarcoRecord,
)


PARQUET_COLUMNS = (
    "source_lang",
    "target_lang",
    "meta",
    "Answer",
    "query_id",
    "query_type",
    "passages",
    "Eng_Query",
    "Eng_Answer",
    "query",
)

LANGUAGE_TAG_TO_LOCALE = {
    "eng_Latn": "en-IN",
    "hin_Deva": "hi-IN",
    "ben_Beng": "bn-IN",
    "tam_Taml": "ta-IN",
    "tel_Telu": "te-IN",
    "kan_Knda": "kn-IN",
    "mal_Mlym": "ml-IN",
    "mar_Deva": "mr-IN",
    "guj_Gujr": "gu-IN",
    "pan_Guru": "pa-IN",
    "ory_Orya": "od-IN",
    "odi_Orya": "od-IN",
}


class DatasetSchemaError(ValueError):
    """Raised when an input row does not match the inspected dataset schema."""


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetSchemaError(f"{key} must be a non-empty string")
    return unicodedata.normalize("NFC", value)


def _text_sequence(passages: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = passages.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise DatasetSchemaError(f"passages.{key} must be a list of strings")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise DatasetSchemaError(f"passages.{key} contains an empty/non-string value")
    return tuple(unicodedata.normalize("NFC", value) for value in values)


def _selection_sequence(passages: Mapping[str, Any]) -> tuple[int, ...]:
    values = passages.get("is_selected")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise DatasetSchemaError("passages.is_selected must be a list")
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in (0, 1)
        for value in values
    ):
        raise DatasetSchemaError("passages.is_selected values must be 0 or 1")
    return tuple(values)


def normalize_record(
    raw: Mapping[str, Any],
    *,
    split: str = "train",
    source_reference: str | None = None,
) -> MSMarcoRecord:
    """Validate and normalize one MSMARCO-XI parquet row."""

    if not isinstance(raw, Mapping):
        raise DatasetSchemaError("dataset row must be an object")

    source_language_tag = _required_text(raw, "source_lang")
    target_language_tag = _required_text(raw, "target_lang")
    try:
        target_language = LANGUAGE_TAG_TO_LOCALE[target_language_tag]
    except KeyError as error:
        raise DatasetSchemaError(
            f"unsupported MSMARCO-XI target language tag: {target_language_tag}"
        ) from error

    query_id = raw.get("query_id")
    if isinstance(query_id, bool) or not isinstance(query_id, int):
        raise DatasetSchemaError("query_id must be an integer")

    passages = raw.get("passages")
    if not isinstance(passages, Mapping):
        raise DatasetSchemaError("passages must be an object")
    english_passages = _text_sequence(passages, "English_passages")
    translated_passages = _text_sequence(passages, "Translated_passages")
    selection_labels = _selection_sequence(passages)
    passage_count = len(english_passages)
    if not (
        passage_count == len(translated_passages) == len(selection_labels)
    ):
        raise DatasetSchemaError(
            "English_passages, Translated_passages, and is_selected must have the same length"
        )
    if passage_count == 0:
        raise DatasetSchemaError("passages must contain at least one aligned passage")

    generation_metadata = raw.get("meta")
    if generation_metadata is None:
        generation_metadata = {}
    if not isinstance(generation_metadata, Mapping):
        raise DatasetSchemaError("meta must be an object or null")

    return MSMarcoRecord(
        source_language_tag=source_language_tag,
        target_language_tag=target_language_tag,
        target_language=target_language,
        query_id=query_id,
        query_type=_required_text(raw, "query_type"),
        query=_required_text(raw, "query"),
        english_query=_required_text(raw, "Eng_Query"),
        answer=_required_text(raw, "Answer"),
        english_answer=_required_text(raw, "Eng_Answer"),
        english_passages=english_passages,
        translated_passages=translated_passages,
        selection_labels=selection_labels,
        generation_metadata=dict(generation_metadata),
        split=split,
        source_reference=source_reference,
    )


def _document_id(
    record: MSMarcoRecord,
    passage_index: int,
    variant: str,
) -> str:
    identity = {
        "dataset": record.dataset_name,
        "revision": record.dataset_revision,
        "split": record.split,
        "query_id": record.query_id,
        "target_language_tag": record.target_language_tag,
        "passage_index": passage_index,
        "variant": variant,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"msxi_{hashlib.sha256(encoded).hexdigest()[:24]}"


def _document(
    record: MSMarcoRecord,
    *,
    passage_index: int,
    text: str,
    language: str,
    variant: str,
    document_id: str,
    parallel_document_id: str,
) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=document_id,
        text=text,
        language=language,
        source=record.dataset_name,
        metadata=DocumentMetadata(
            dataset_name=record.dataset_name,
            dataset_revision=record.dataset_revision,
            split=record.split,
            source_reference=record.source_reference,
            query_id=record.query_id,
            query_type=record.query_type,
            source_language_tag=record.source_language_tag,
            target_language_tag=record.target_language_tag,
            passage_index=passage_index,
            selected=bool(record.selection_labels[passage_index]),
            variant=variant,
            query=record.query,
            english_query=record.english_query,
            answer=record.answer,
            english_answer=record.english_answer,
            parallel_document_id=parallel_document_id,
            generation_metadata=dict(record.generation_metadata),
        ),
    )


def iter_documents(
    records: Iterable[MSMarcoRecord],
    *,
    selected_only: bool = False,
) -> Iterator[CanonicalDocument]:
    """Yield aligned English/translated passage documents in source order."""

    for record in records:
        for index, (english, translated, selected) in enumerate(
            zip(
                record.english_passages,
                record.translated_passages,
                record.selection_labels,
                strict=True,
            )
        ):
            if selected_only and not selected:
                continue
            english_id = _document_id(record, index, "english")
            translated_id = _document_id(record, index, "translated")
            yield _document(
                record,
                passage_index=index,
                text=english,
                language="en-IN",
                variant="english",
                document_id=english_id,
                parallel_document_id=translated_id,
            )
            yield _document(
                record,
                passage_index=index,
                text=translated,
                language=record.target_language,
                variant="translated",
                document_id=translated_id,
                parallel_document_id=english_id,
            )


def iter_parquet_records(
    source: str | Path,
    *,
    batch_size: int = 1_000,
    limit: int | None = None,
    split: str = "train",
    dataset_revision: str | None = None,
) -> Iterator[MSMarcoRecord]:
    """Stream normalized records from local or ``hf://`` parquet data."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if limit is not None and limit < 0:
        raise ValueError("limit cannot be negative")

    source_reference = str(source)
    if source_reference.startswith("hf://"):
        pinned_prefix = f"hf://datasets/{DATASET_NAME}@{DATASET_REVISION}/"
        if not source_reference.startswith(pinned_prefix):
            raise ValueError(
                f"hf:// source must use pinned MSMARCO-XI revision {DATASET_REVISION}"
            )
    elif dataset_revision is None:
        raise ValueError(
            "dataset_revision is required for local parquet sources to assert provenance"
        )

    if dataset_revision is not None and dataset_revision != DATASET_REVISION:
        raise ValueError(
            f"dataset_revision must equal pinned MSMARCO-XI revision {DATASET_REVISION}"
        )

    try:
        import pyarrow.parquet as parquet
    except ImportError as error:
        raise RuntimeError("pyarrow is required to ingest parquet files") from error

    emitted = 0

    def stream(parquet_file: Any) -> Iterator[MSMarcoRecord]:
        nonlocal emitted
        for batch in parquet_file.iter_batches(
            batch_size=batch_size,
            columns=list(PARQUET_COLUMNS),
        ):
            for raw in batch.to_pylist():
                if limit is not None and emitted >= limit:
                    return
                yield normalize_record(
                    raw,
                    split=split,
                    source_reference=source_reference,
                )
                emitted += 1

    if source_reference.startswith("hf://"):
        try:
            import fsspec
        except ImportError as error:
            raise RuntimeError("fsspec is required for hf:// dataset paths") from error
        with fsspec.open(source_reference, "rb") as handle:
            yield from stream(parquet.ParquetFile(handle))
    else:
        yield from stream(parquet.ParquetFile(source_reference))


def write_documents_jsonl(
    documents: Iterable[CanonicalDocument],
    destination: str | Path,
) -> int:
    """Write deterministic UTF-8 JSONL and return the document count."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for document in documents:
            output.write(
                json.dumps(
                    document.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            output.write("\n")
            count += 1
    return count
