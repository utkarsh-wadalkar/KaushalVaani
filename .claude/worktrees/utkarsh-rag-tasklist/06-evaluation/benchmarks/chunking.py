"""Structural and timing benchmarks for explicit offline chunking candidates."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = PROJECT_ROOT / "03-ai-rag-engine"
# When this file is executed directly, Python puts its ``benchmarks`` directory
# first on ``sys.path``.  Insert the engine source root ahead of it so the
# ``chunking`` package is not shadowed by this file's ``chunking.py`` basename.
if str(ENGINE_ROOT) in sys.path:
    sys.path.remove(str(ENGINE_ROOT))
sys.path.insert(0, str(ENGINE_ROOT))

from chunking.base import ChunkingStrategy
from chunking.fixed import FixedChunkingStrategy
from chunking.sentence import SentenceChunkingStrategy
from chunking.strategy import build_candidate_strategies
from ingestion.metadata import CanonicalDocument, DocumentMetadata


Clock = Callable[[], float]


def benchmark_chunking(
    documents: Iterable[CanonicalDocument],
    strategies: Sequence[ChunkingStrategy],
    *,
    clock: Clock = perf_counter,
) -> dict[str, Any]:
    """Benchmark every supplied candidate over the same materialized documents."""

    corpus = tuple(documents)
    results: list[dict[str, Any]] = []
    for strategy in strategies:
        started = clock()
        chunks = [chunk for document in corpus for chunk in strategy.chunk(document)]
        elapsed_ms = round((clock() - started) * 1_000, 6)
        lengths = [len(chunk.text) for chunk in chunks]
        elapsed_seconds = elapsed_ms / 1_000
        results.append(
            {
                "strategy": strategy.name,
                "config_id": strategy.config_id,
                "documents": len(corpus),
                "chunks": len(chunks),
                "empty_chunks": sum(not chunk.text for chunk in chunks),
                "min_chunk_chars": min(lengths, default=0),
                "max_chunk_chars": max(lengths, default=0),
                "mean_chunk_chars": round(sum(lengths) / len(lengths), 6)
                if lengths
                else 0.0,
                "duplicated_chars": sum(chunk.overlap_chars for chunk in chunks),
                "elapsed_ms": elapsed_ms,
                "throughput": {
                    "documents_per_second": round(len(corpus) / elapsed_seconds, 6)
                    if elapsed_seconds > 0
                    else 0.0,
                    "chunks_per_second": round(len(chunks) / elapsed_seconds, 6)
                    if elapsed_seconds > 0
                    else 0.0,
                },
            }
        )
    return {"documents": len(corpus), "strategies": results}


def iter_processed_jsonl(path: str | Path) -> Iterator[CanonicalDocument]:
    """Load canonical ingestion JSONL without importing dataset-specific loaders."""

    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                metadata = DocumentMetadata(**payload["metadata"])
                yield CanonicalDocument(
                    document_id=payload["document_id"],
                    text=payload["text"],
                    language=payload["language"],
                    source=payload["source"],
                    metadata=metadata,
                )
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"invalid canonical document at {path}:{line_number}"
                ) from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Canonical processed JSONL")
    parser.add_argument("--output", help="Optional JSON report destination")
    parser.add_argument("--max-chars", type=int, default=1_000)
    parser.add_argument("--overlap-chars", type=int, default=0)
    parser.add_argument("--overlap-sentences", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    strategies = build_candidate_strategies(
        FixedChunkingStrategy(
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        ),
        SentenceChunkingStrategy(
            max_chars=args.max_chars,
            overlap_sentences=args.overlap_sentences,
        ),
    )
    report = benchmark_chunking(iter_processed_jsonl(args.input), strategies)
    serialized = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
