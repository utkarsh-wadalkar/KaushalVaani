from __future__ import annotations

import time
import unittest

from generation.llm import FixtureLLM, GenerationResponse
from generation.schemas import Query
from guardrails.grounding import GroundingResult
from orchestration.errors import PipelineError
from orchestration.pipeline import RAGPipeline
from retrieval.reranker import RetrievalCandidate
from retrieval.retriever import RetrievalLatency, RetrievalResult


class StubRetriever:
    def __init__(self, chunks):
        self.chunks = tuple(chunks)

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        return RetrievalResult(
            query=query,
            chunks=self.chunks[:top_k],
            latency=RetrievalLatency(1.0, 1.0, 0.0, 2.0),
        )


class StubGrounding:
    def __init__(self, grounded: bool):
        self.grounded = grounded

    def check(self, answer, candidates, timeout_ms=25):
        return GroundingResult(self.grounded, 1.0 if self.grounded else 0.0, 0.1, "fixture")


class DelayedRetriever(StubRetriever):
    def __init__(self, chunks, delay_seconds: float):
        super().__init__(chunks)
        self.delay_seconds = delay_seconds

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        time.sleep(self.delay_seconds)
        return super().retrieve(query, top_k)


class DelayedGenerator:
    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds

    def generate(self, query, candidates, *, timeout_ms=None):
        time.sleep(self.delay_seconds)
        return GenerationResponse("The station is downtown.", self.delay_seconds * 1_000)


class DelayedGrounding(StubGrounding):
    def __init__(self, delay_seconds: float):
        super().__init__(True)
        self.delay_seconds = delay_seconds

    def check(self, answer, candidates, timeout_ms=25):
        time.sleep(self.delay_seconds)
        return GroundingResult(True, 1.0, self.delay_seconds * 1_000, "fixture")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.candidate = RetrievalCandidate(
            "c1", "The station is downtown.", 0.9, {"language": "en-IN"}
        )

    def test_pipeline_emits_stages_and_returns_grounded_false_success(self):
        stages = []
        pipeline = RAGPipeline(
            StubRetriever((self.candidate,)),
            FixtureLLM("The station is downtown."),
            grounding=StubGrounding(False),
            relevance_floor=0.5,
        )
        answer = pipeline.run(
            Query("r1", "Where is the station?", "en-IN"),
            stage_callback=stages.append,
        )
        self.assertFalse(answer.grounded)
        self.assertEqual(answer.request_id, "r1")
        self.assertEqual(answer.sources[0].id, "c1")
        self.assertEqual(
            stages,
            ["preprocessing", "embedding", "retrieval", "reranking", "generation", "grounding"],
        )
        self.assertGreaterEqual(answer.latency.total_ms, answer.latency.retrieval_total_ms)

    def test_pipeline_stops_before_generation_when_no_context(self):
        pipeline = RAGPipeline(
            StubRetriever((RetrievalCandidate("c1", "weak", 0.1, {}),)),
            FixtureLLM("must not be used"),
            relevance_floor=0.5,
        )
        with self.assertRaises(PipelineError) as error:
            pipeline.run(Query("r1", "question", "en-IN"))
        self.assertEqual(error.exception.code, "NO_RELEVANT_CONTEXT")

    def test_pipeline_maps_unsupported_language_to_typed_error(self):
        pipeline = RAGPipeline(StubRetriever(()), FixtureLLM("answer"))
        with self.assertRaises(PipelineError) as error:
            pipeline.run({"request_id": "r1", "query": "question", "language": "xx-IN"})
        self.assertEqual(error.exception.code, "UNSUPPORTED_LANGUAGE")

    def test_stage_callback_failure_does_not_break_answer(self):
        pipeline = RAGPipeline(
            StubRetriever((self.candidate,)),
            FixtureLLM("The station is downtown."),
            relevance_floor=0.5,
        )

        def failing_callback(stage):
            raise RuntimeError(stage)

        answer = pipeline.run(
            Query("r1", "Where is the station?", "en-IN"),
            stage_callback=failing_callback,
        )
        self.assertEqual(answer.request_id, "r1")

    def test_pipeline_enforces_one_deadline_after_each_blocking_stage(self):
        cases = (
            (
                "retrieval",
                DelayedRetriever((self.candidate,), 0.02),
                FixtureLLM("The station is downtown."),
                StubGrounding(True),
            ),
            (
                "generation",
                StubRetriever((self.candidate,)),
                DelayedGenerator(0.02),
                StubGrounding(True),
            ),
            (
                "grounding",
                StubRetriever((self.candidate,)),
                FixtureLLM("The station is downtown."),
                DelayedGrounding(0.02),
            ),
        )

        for stage, retriever, generator, grounding in cases:
            with self.subTest(stage=stage):
                pipeline = RAGPipeline(
                    retriever,
                    generator,
                    grounding=grounding,
                    deadline_ms=1,
                )
                with self.assertRaises(PipelineError) as error:
                    pipeline.run(Query("r1", "Where is the station?", "en-IN"))
                self.assertEqual(error.exception.code, "RAG_TIMEOUT")
                self.assertTrue(error.exception.retryable)

    def test_final_serialization_updates_total_and_internal_stage_attribution(self):
        pipeline = RAGPipeline(
            StubRetriever((self.candidate,)),
            FixtureLLM("The station is downtown."),
            grounding=StubGrounding(True),
            deadline_ms=1_000,
        )
        answer = pipeline.run(Query("r1", "Where is the station?", "en-IN"))
        pipeline_total = answer.latency.total_ms
        time.sleep(0.01)

        serialized = answer.serialize()

        self.assertGreater(serialized.payload["latency"]["total_ms"], pipeline_total)
        self.assertIn("preprocessing_ms", serialized.stage_timings)
        self.assertIn("context_construction_ms", serialized.stage_timings)
        self.assertIn("serialization_ms", serialized.stage_timings)
        for component in serialized.payload["latency"].values():
            if component is not None:
                self.assertLessEqual(component, serialized.payload["latency"]["total_ms"])

    def test_final_serialization_enforces_the_pipeline_deadline(self):
        pipeline = RAGPipeline(
            StubRetriever((self.candidate,)),
            FixtureLLM("The station is downtown."),
            grounding=StubGrounding(True),
            deadline_ms=50,
        )
        answer = pipeline.run(Query("r1", "Where is the station?", "en-IN"))
        time.sleep(0.06)

        with self.assertRaises(TimeoutError):
            answer.serialize()


if __name__ == "__main__":
    unittest.main()
