from __future__ import annotations

import unittest
import sys
from pathlib import Path

EVALUATION_ROOT = Path(__file__).resolve().parents[2] / "06-evaluation"
if str(EVALUATION_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALUATION_ROOT))

from benchmarks.end_to_end import benchmark_pipeline
from generation.llm import FixtureLLM
from generation.schemas import Query
from retrieval.reranker import RetrievalCandidate
from retrieval.retriever import RetrievalLatency, RetrievalResult


class StubRetriever:
    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        return RetrievalResult(
            query=query,
            chunks=(RetrievalCandidate("c1", "The answer is here.", 0.9, {}),),
            latency=RetrievalLatency(1.0, 1.0, 0.0, 2.0),
        )


class EndToEndBenchmarkTests(unittest.TestCase):
    def test_benchmark_reports_percentiles_and_cold_start_separately(self):
        pipeline = __import__("orchestration.pipeline", fromlist=["RAGPipeline"]).RAGPipeline(
            StubRetriever(), FixtureLLM("The answer is here."), relevance_floor=0.5
        )
        report = benchmark_pipeline(
            pipeline,
            [Query(f"r{i}", "Where?", "en-IN") for i in range(5)],
            cold_start_ms=12.0,
        )
        self.assertEqual(report["steady_state"]["latency"]["count"], 5)
        self.assertIn("p70", report["steady_state"]["latency"])
        self.assertEqual(report["cold_start_ms"], 12.0)
        self.assertIn("p100", report["steady_state"]["latency"])


if __name__ == "__main__":
    unittest.main()
