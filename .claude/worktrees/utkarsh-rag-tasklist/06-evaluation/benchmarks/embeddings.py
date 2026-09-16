"""Benchmark explicitly supplied embedding candidates without selecting a winner."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "03-ai-rag-engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


def benchmark_candidates(candidates: Sequence[object], fixtures: Sequence[str]) -> dict:
    texts = [item["text"] if isinstance(item, dict) else item for item in fixtures]
    languages = sorted({item["language"] for item in fixtures if isinstance(item, dict) and "language" in item})
    results = []
    for candidate in candidates:
        start = time.perf_counter()
        batch = candidate.embed_batch(texts)
        elapsed_ms = (time.perf_counter() - start) * 1000
        results.append({"candidate": getattr(candidate, "model_name", type(candidate).__name__), "fixtures": len(fixtures), "dimension": batch.dimension, "elapsed_ms": elapsed_ms})
    return {"fixtures": len(fixtures), "languages": languages, "candidates": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True, help="JSON file containing a list of multilingual fixture strings")
    args = parser.parse_args(argv)
    from embeddings.provider import HashingEmbedder
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    print(json.dumps(benchmark_candidates([HashingEmbedder()], fixtures), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
