"""Stream MSMARCO-XI parquet rows into deterministic processed JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1] / "03-ai-rag-engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from ingestion.cleaner import CleaningReport, iter_clean_documents
from ingestion.loader import (
    iter_documents,
    iter_parquet_records,
    write_documents_jsonl,
)
from ingestion.metadata import DATASET_REVISION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize MSMARCO-XI parquet rows into processed JSONL documents."
    )
    parser.add_argument(
        "--source", required=True, help="Local parquet path or hf:// URL"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Processed JSONL destination"
    )
    parser.add_argument(
        "--split", default="train", help="Dataset split recorded in metadata"
    )
    parser.add_argument(
        "--dataset-revision",
        choices=[DATASET_REVISION],
        help="Required for local parquet sources; asserts the pinned dataset revision",
    )
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--limit", type=int, default=None, help="Maximum source rows to read")
    parser.add_argument(
        "--selected-only",
        action="store_true",
        help="Emit only passages whose is_selected label is 1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_records = iter_parquet_records(
        args.source,
        batch_size=args.batch_size,
        limit=args.limit,
        split=args.split,
        dataset_revision=args.dataset_revision,
    )

    records_seen = 0

    def count_records() -> Iterator[object]:
        nonlocal records_seen
        for record in source_records:
            records_seen += 1
            yield record

    documents = iter_documents(count_records(), selected_only=args.selected_only)
    report = CleaningReport()
    cleaned = iter_clean_documents(documents, report=report)
    count = write_documents_jsonl(cleaned, args.output)
    print(
        json.dumps(
            {
                "source": args.source,
                "output": str(args.output),
                "records": records_seen,
                "documents": count,
                "cleaning": {
                    "seen": report.seen,
                    "emitted": report.emitted,
                    "empty": report.empty,
                    "duplicates": report.duplicates,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
