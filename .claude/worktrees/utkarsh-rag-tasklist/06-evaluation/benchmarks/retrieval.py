"""Compare local fixture retrieval with reranking disabled and enabled."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


def _load_metrics():
    path = Path(__file__).resolve().parents[1] / "metrics" / "retrieval.py"
    spec = importlib.util.spec_from_file_location("echoquery_retrieval_metrics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load retrieval metrics from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


METRICS = _load_metrics()


@dataclass(frozen=True, slots=True)
class RetrievalBenchmarkCase:
    query: str
    query_locale: str
    evidence_locale: str
    relevance_judgments: Mapping[str, float]


class RetrieverLike(Protocol):
    def retrieve(self, query: str, top_k: int): ...


def _run_cases(
    cases: Sequence[RetrievalBenchmarkCase], retriever: RetrieverLike, top_k: int
) -> tuple[dict[str, object], float]:
    evaluations = []
    total_latency_ms = 0.0
    for case in cases:
        result = retriever.retrieve(case.query, top_k)
        evaluations.append(
            METRICS.RetrievalEvaluationCase(
                query_locale=case.query_locale,
                evidence_locale=case.evidence_locale,
                ranked_ids=tuple(chunk.chunk_id for chunk in result.chunks),
                relevance_judgments=case.relevance_judgments,
            )
        )
        total_latency_ms += result.latency.total_ms
    quality = METRICS.aggregate_retrieval_metrics(evaluations, k=top_k)
    mean_latency_ms = total_latency_ms / len(cases) if cases else 0.0
    return quality, mean_latency_ms


def benchmark_reranking(
    cases: Sequence[RetrievalBenchmarkCase],
    without_reranking: RetrieverLike,
    with_reranking: RetrieverLike,
    *,
    top_k: int,
) -> dict[str, object]:
    materialized = tuple(cases)
    disabled_quality, disabled_latency = _run_cases(
        materialized, without_reranking, top_k
    )
    enabled_quality, enabled_latency = _run_cases(
        materialized, with_reranking, top_k
    )
    disabled_overall = disabled_quality["overall"]
    enabled_overall = enabled_quality["overall"]
    return {
        "observation_label": "local fixture observations; non-production",
        "cases": len(materialized),
        "top_k": top_k,
        "reranking_disabled": {
            "quality": disabled_quality,
            "mean_total_latency_ms": disabled_latency,
        },
        "reranking_enabled": {
            "quality": enabled_quality,
            "mean_total_latency_ms": enabled_latency,
        },
        "quality_delta": {
            metric: enabled_overall[metric] - disabled_overall[metric]
            for metric in ("recall_at_k", "mrr_at_k", "ndcg_at_k")
        },
        "latency_delta_ms": enabled_latency - disabled_latency,
    }


benchmark_retrieval = benchmark_reranking


__all__ = ["RetrievalBenchmarkCase", "benchmark_retrieval", "benchmark_reranking"]
