"""Unicode-safe cleaning for canonical documents."""

from __future__ import annotations

import re
import sqlite3
import tempfile
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ingestion.metadata import CanonicalDocument


_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")


@dataclass(slots=True)
class CleaningReport:
    seen: int = 0
    emitted: int = 0
    empty: int = 0
    duplicates: int = 0


def clean_text(text: str) -> str:
    """Normalize line endings, Unicode, and whitespace without ASCII folding."""

    normalized = unicodedata.normalize(
        "NFC", text.replace("\r\n", "\n").replace("\r", "\n")
    )
    lines = [
        _HORIZONTAL_WHITESPACE.sub(" ", line).strip()
        for line in normalized.split("\n")
    ]
    return _EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def iter_clean_documents(
    documents: Iterable[CanonicalDocument],
    *,
    report: CleaningReport | None = None,
) -> Iterator[CanonicalDocument]:
    """Clean documents and drop repeated canonical source documents."""

    current_report = report if report is not None else CleaningReport()
    with tempfile.TemporaryDirectory(prefix="echoquery-ingestion-") as temporary_root:
        database_path = f"{temporary_root}/document_ids.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA cache_size=-8192")
            connection.execute(
                "CREATE TABLE seen_document_ids "
                "(document_id TEXT PRIMARY KEY) WITHOUT ROWID"
            )
            for document in documents:
                current_report.seen += 1
                text = clean_text(document.text)
                if not text:
                    current_report.empty += 1
                    continue
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO seen_document_ids(document_id) VALUES (?)",
                    (document.document_id,),
                )
                if inserted.rowcount == 0:
                    current_report.duplicates += 1
                    continue
                current_report.emitted += 1
                if current_report.emitted % 10_000 == 0:
                    connection.commit()
                if text == document.text:
                    yield document
                else:
                    yield CanonicalDocument(
                        document_id=document.document_id,
                        text=text,
                        language=document.language,
                        source=document.source,
                        metadata=document.metadata,
                    )
            connection.commit()
        finally:
            connection.close()
