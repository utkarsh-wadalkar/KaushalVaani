import importlib.util
import math
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ENGINE_ROOT.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from embeddings.base import EmbeddingBatch, EmbeddingValidationError
from retrieval.reranker import DeterministicFixtureReranker, RetrievalCandidate
from retrieval.retriever import RetrievalLatency, RetrievalResult, Retriever
from retrieval.vector_store import SearchResult


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


METRICS = load_module(
    "retrieval_metrics_fixture",
    PROJECT_ROOT / "06-evaluation" / "metrics" / "retrieval.py",
)
BENCHMARK = load_module(
    "retrieval_benchmark_fixture",
    PROJECT_ROOT / "06-evaluation" / "benchmarks" / "retrieval.py",
)


class FixtureEmbedder:
    dimension = 2
    model_name = "fixture"
    config = {"fixture": True}

    def __init__(self, batch=None):
        self.batch = batch or EmbeddingBatch(((1.0, 0.0),), 2, self.model_name)
        self.calls = []

    def embed_batch(self, texts):
        self.calls.append(tuple(texts))
        return self.batch


class FixtureStore:
    dimension = 2

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def search(self, query_vector, *, limit=10):
        self.calls.append((tuple(query_vector), limit))
        return self.results[:limit]


def search_result(chunk_id, score, text=None, metadata=None):
    return SearchResult(
        chunk_id,
        score,
        {
            "text": text or f"text-{chunk_id}",
            "metadata": metadata or {"language": "en-IN", "rank": chunk_id},
        },
    )


class RetrieverTests(unittest.TestCase):
    def test_retrieve_preserves_vector_order_and_fetches_top_k_without_reranker(self):
        embedder = FixtureEmbedder()
        store = FixtureStore(
            [search_result("b", 0.9), search_result("a", 0.8), search_result("c", 0.7)]
        )
        result = Retriever(embedder, store).retrieve("query", top_k=2)

        self.assertEqual(embedder.calls, [("query",)])
        self.assertEqual(store.calls, [((1.0, 0.0), 2)])
        self.assertEqual(tuple(chunk.chunk_id for chunk in result.chunks), ("b", "a"))
        self.assertEqual(result.chunks[0].text, "text-b")
        self.assertEqual(result.chunks[0].metadata["language"], "en-IN")

    def test_retriever_uses_broad_fetch_k_then_deterministic_fixture_reranker(self):
        store = FixtureStore(
            [search_result("a", 0.9), search_result("b", 0.8), search_result("c", 0.7)]
        )
        reranker = DeterministicFixtureReranker({"query": ("c", "a")})
        result = Retriever(FixtureEmbedder(), store, reranker=reranker, fetch_k=3).retrieve(
            "query", top_k=2
        )

        self.assertEqual(store.calls[0][1], 3)
        self.assertEqual(tuple(chunk.chunk_id for chunk in result.chunks), ("c", "a"))
        self.assertIn("non-production", reranker.label)

    def test_over_returning_store_is_bounded_to_fetch_k_before_reranking(self):
        class OverReturningStore(FixtureStore):
            def search(self, query_vector, *, limit=10):
                self.calls.append((tuple(query_vector), limit))
                return list(self.results)

        class RecordingReranker:
            def __init__(self):
                self.seen = None

            def rerank(self, query, candidates):
                self.seen = tuple(candidate.chunk_id for candidate in candidates)
                return candidates

        store = OverReturningStore(
            [
                search_result("a", 0.9),
                search_result("b", 0.8),
                search_result("c", 0.7),
                search_result("d", 0.6),
            ]
        )
        reranker = RecordingReranker()
        result = Retriever(
            FixtureEmbedder(), store, reranker=reranker, fetch_k=2
        ).retrieve("query", top_k=1)

        self.assertEqual(store.calls[0][1], 2)
        self.assertEqual(reranker.seen, ("a", "b"))
        self.assertEqual(tuple(chunk.chunk_id for chunk in result.chunks), ("a",))

    def test_top_k_and_fetch_k_boundaries_are_validated(self):
        retriever = Retriever(FixtureEmbedder(), FixtureStore([]), fetch_k=20)
        for invalid in (0, 21):
            with self.subTest(top_k=invalid):
                with self.assertRaisesRegex(ValueError, "top_k"):
                    retriever.retrieve("query", top_k=invalid)

        with self.assertRaisesRegex(ValueError, "fetch_k"):
            Retriever(FixtureEmbedder(), FixtureStore([]), fetch_k=1).retrieve(
                "query", top_k=2
            )
        with self.assertRaisesRegex(ValueError, "fetch_k"):
            retriever.retrieve("query", top_k=2, fetch_k=1)

    def test_empty_index_returns_an_immutable_empty_result(self):
        result = Retriever(FixtureEmbedder(), FixtureStore([])).retrieve("missing", top_k=3)
        self.assertEqual(result.query, "missing")
        self.assertEqual(result.chunks, ())
        with self.assertRaises(FrozenInstanceError):
            result.query = "changed"

    def test_embedding_cardinality_and_dimension_errors_fail_before_search(self):
        store = FixtureStore([])
        short = FixtureEmbedder(EmbeddingBatch((), 2, "short"))
        with self.assertRaises(EmbeddingValidationError):
            Retriever(short, store).retrieve("query", top_k=1)
        self.assertEqual(store.calls, [])

        wrong_dimension = FixtureEmbedder(EmbeddingBatch(((1.0, 0.0),), 2, "wrong"))
        wrong_dimension.dimension = 3
        with self.assertRaises(EmbeddingValidationError):
            Retriever(wrong_dimension, store).retrieve("query", top_k=1)

    def test_missing_payload_fields_fail_clearly_and_metadata_is_immutable(self):
        for payload, field in (({"metadata": {}}, "text"), ({"text": "x"}, "metadata")):
            with self.subTest(field=field):
                store = FixtureStore([SearchResult("a", 1.0, payload)])
                with self.assertRaisesRegex(ValueError, field):
                    Retriever(FixtureEmbedder(), store).retrieve("query", top_k=1)

        result = Retriever(
            FixtureEmbedder(), FixtureStore([search_result("a", 1.0)])
        ).retrieve("query", top_k=1)
        with self.assertRaises(TypeError):
            result.chunks[0].metadata["new"] = "value"

    def test_reranker_cannot_drop_duplicate_invent_or_mutate_candidates(self):
        candidates = [search_result("a", 1.0), search_result("b", 0.5)]

        class BadReranker:
            def __init__(self, output):
                self.output = output

            def rerank(self, query, supplied):
                if callable(self.output):
                    return self.output(supplied)
                return self.output

        cases = {
            "drop": lambda supplied: supplied[:1],
            "duplicate": lambda supplied: (supplied[0], supplied[0]),
            "invent": lambda supplied: supplied
            + (RetrievalCandidate("invented", "new", 0.0, {}),),
            "mutate": lambda supplied: (
                RetrievalCandidate("a", "changed", 1.0, {}),
                supplied[1],
            ),
        }
        for name, output in cases.items():
            with self.subTest(name=name):
                retriever = Retriever(
                    FixtureEmbedder(),
                    FixtureStore(candidates),
                    reranker=BadReranker(output),
                    fetch_k=2,
                )
                with self.assertRaisesRegex(ValueError, "reranker"):
                    retriever.retrieve("query", top_k=1)

    def test_latency_components_are_non_negative_and_bounded_by_total(self):
        result = Retriever(
            FixtureEmbedder(),
            FixtureStore([search_result("a", 1.0)]),
            reranker=DeterministicFixtureReranker(),
        ).retrieve("query", top_k=1)
        latency = result.latency
        self.assertGreaterEqual(latency.embedding_ms, 0.0)
        self.assertGreaterEqual(latency.search_ms, 0.0)
        self.assertGreaterEqual(latency.reranking_ms, 0.0)
        self.assertGreaterEqual(latency.total_ms, 0.0)
        for component in (latency.embedding_ms, latency.search_ms, latency.reranking_ms):
            self.assertLessEqual(component, latency.total_ms)
        with self.assertRaises(ValueError):
            RetrievalLatency(float("nan"), 0.0, 0.0, 1.0)


class RetrievalMetricTests(unittest.TestCase):
    def test_recall_mrr_and_graded_ndcg_have_exact_values(self):
        ranked = ("a", "b", "c", "d")
        self.assertEqual(METRICS.recall_at_k(ranked, {"b", "d"}, 3), 0.5)
        self.assertEqual(METRICS.mrr_at_k(ranked, {"b", "d"}, 3), 0.5)
        expected_dcg = 7 / math.log2(3) + 3 / math.log2(4)
        expected_ideal = 7 + 3 / math.log2(3)
        self.assertAlmostEqual(
            METRICS.ndcg_at_k(ranked, {"b": 3, "c": 2}, 3),
            expected_dcg / expected_ideal,
        )
        self.assertEqual(METRICS.recall_at_k(ranked, set(), 3), 0.0)
        self.assertEqual(METRICS.ndcg_at_k(ranked, {}, 3), 0.0)

    def test_metrics_reject_invalid_k_duplicate_ids_and_bad_gains(self):
        for metric, relevance in (
            (METRICS.recall_at_k, {"a"}),
            (METRICS.mrr_at_k, {"a"}),
            (METRICS.ndcg_at_k, {"a": 1}),
        ):
            with self.subTest(metric=metric.__name__):
                with self.assertRaisesRegex(ValueError, "k"):
                    metric(("a",), relevance, 0)
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    metric(("a", "a"), relevance, 2)

        for gain in (-1, float("nan"), float("inf"), 1e308, "high", None):
            with self.subTest(gain=gain):
                with self.assertRaisesRegex(ValueError, "gain"):
                    METRICS.ndcg_at_k(("a",), {"a": gain}, 1)

    def test_aggregation_reports_overall_language_direction_and_query_locale(self):
        cases = (
            METRICS.RetrievalEvaluationCase(
                query_locale="en-IN",
                evidence_locale="en-IN",
                ranked_ids=("a", "b"),
                relevance_judgments={"b": 1},
            ),
            METRICS.RetrievalEvaluationCase(
                query_locale="hi-IN",
                evidence_locale="en-IN",
                ranked_ids=("b", "a"),
                relevance_judgments={"b": 1},
            ),
        )
        report = METRICS.aggregate_retrieval_metrics(cases, k=2)
        self.assertEqual(report["overall"]["count"], 2)
        self.assertEqual(report["monolingual"]["count"], 1)
        self.assertEqual(report["cross_lingual"]["count"], 1)
        self.assertEqual(set(report["per_query_locale"]), {"en-IN", "hi-IN"})
        self.assertEqual(report["overall"]["recall_at_k"], 1.0)
        self.assertEqual(report["overall"]["mrr_at_k"], 0.75)
        self.assertAlmostEqual(
            report["overall"]["ndcg_at_k"],
            (1 / math.log2(3) + 1) / 2,
        )


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_benchmark_reports_reranking_quality_and_latency_deltas_without_winner(self):
        def result(query, ranked_ids, total_ms):
            chunks = tuple(
                RetrievalCandidate(chunk_id, f"text-{chunk_id}", 1.0, {})
                for chunk_id in ranked_ids
            )
            return RetrievalResult(
                query,
                chunks,
                RetrievalLatency(0.1, 0.2, 0.0, total_ms),
            )

        class StaticRetriever:
            def __init__(self, ranked_ids, latency_ms):
                self.ranked_ids = ranked_ids
                self.latency_ms = latency_ms

            def retrieve(self, query, top_k):
                return result(query, self.ranked_ids[:top_k], self.latency_ms)

        cases = (
            BENCHMARK.RetrievalBenchmarkCase(
                query="station",
                query_locale="hi-IN",
                evidence_locale="en-IN",
                relevance_judgments={"relevant": 2},
            ),
        )
        report = BENCHMARK.benchmark_reranking(
            cases,
            StaticRetriever(("irrelevant", "relevant"), 1.0),
            StaticRetriever(("relevant", "irrelevant"), 1.5),
            top_k=2,
        )
        self.assertIn("local fixture", report["observation_label"])
        self.assertEqual(report["quality_delta"]["mrr_at_k"], 0.5)
        self.assertEqual(report["latency_delta_ms"], 0.5)
        self.assertNotIn("winner", report)
        self.assertNotIn("selection", report)


if __name__ == "__main__":
    unittest.main()
