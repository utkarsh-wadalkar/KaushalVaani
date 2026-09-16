"""Steady-state end-to-end RAG latency benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = PROJECT_ROOT / "03-ai-rag-engine"
if str(ENGINE_ROOT) in sys.path:
    sys.path.remove(str(ENGINE_ROOT))
sys.path.insert(0, str(ENGINE_ROOT))
EVALUATION_ROOT = PROJECT_ROOT / "06-evaluation"
if str(EVALUATION_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALUATION_ROOT))

from embeddings.provider import HashingEmbedder
from generation.llm import FixtureLLM
from generation.schemas import Query
from metrics.latency import percentile_report
from orchestration.pipeline import RAGPipeline
from retrieval.retriever import Retriever
from retrieval.vector_store import InMemoryVectorStore


def benchmark_pipeline(pipeline, queries: Sequence[Query], *, cold_start_ms: float | None = None) -> dict[str, object]:
    latencies: list[float] = []
    grounded = 0
    errors: dict[str, int] = {}
    for query in queries:
        started = perf_counter()
        try:
            answer = pipeline.run(query)
            grounded += int(answer.grounded)
        except Exception as error:
            code = getattr(error, "code", type(error).__name__)
            errors[code] = errors.get(code, 0) + 1
        latencies.append((perf_counter() - started) * 1000)
    return {
        "observation_label": "measured local benchmark; not production evidence",
        "queries": len(queries),
        "cold_start_ms": cold_start_ms,
        "steady_state": {
            "latency": percentile_report(latencies),
            "grounded_answers": grounded,
            "errors": errors,
        },
        "target_ms": 200,
        "target_applies_to": "total RAG request wall-clock through serialized answer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--answer", default="Fixture answer; replace with the configured model in production.")
    parser.add_argument("--fetch-k", type=int, default=20)
    parser.add_argument("--relevance-floor", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    store = InMemoryVectorStore.load(args.index)
    retriever = Retriever(
        HashingEmbedder(dimension=store.dimension),
        store,
        fetch_k=args.fetch_k,
    )
    pipeline = RAGPipeline(
        retriever,
        FixtureLLM(args.answer),
        relevance_floor=args.relevance_floor,
    )
    raw_queries = json.loads(args.queries.read_text(encoding="utf-8"))
    queries = [Query(**item) for item in raw_queries]
    report = benchmark_pipeline(pipeline, queries)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
