"""Single Query -> Answer RAG orchestration boundary."""

from __future__ import annotations

import inspect
import math
from time import perf_counter
from typing import Any, Callable

from generation.llm import Generator
from generation.schemas import Answer, Latency, Query, Source
from guardrails.grounding import GroundingResult, check_grounding
from guardrails.input_guard import InputGuardError, validate_query
from guardrails.relevance import NoRelevantContextError, filter_relevant
from orchestration.errors import PipelineError
from retrieval.retriever import Retriever, RetrievalResult


class RAGPipeline:
    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        *,
        grounding=None,
        relevance_floor: float = 0.0,
        deadline_ms: float = 200.0,
    ):
        if not isinstance(deadline_ms, (int, float)) or isinstance(deadline_ms, bool):
            raise ValueError("deadline_ms must be a finite positive number")
        if not math.isfinite(float(deadline_ms)) or float(deadline_ms) <= 0:
            raise ValueError("deadline_ms must be a finite positive number")
        self.retriever = retriever
        self.generator = generator
        self.grounding = grounding
        self.relevance_floor = relevance_floor
        self.deadline_ms = float(deadline_ms)

    @staticmethod
    def _remaining_ms(started: float, deadline_ms: float) -> float:
        return deadline_ms - max(0.0, (perf_counter() - started) * 1_000)

    @classmethod
    def _ensure_budget(cls, started: float, deadline_ms: float, stage: str) -> float:
        remaining = cls._remaining_ms(started, deadline_ms)
        if remaining <= 0:
            raise TimeoutError(f"RAG request exceeded {deadline_ms:g} ms deadline during {stage}")
        return remaining

    @staticmethod
    def _call_with_timeout(callable_object: Callable[..., Any], *args: Any, timeout_ms: float, **kwargs: Any) -> Any:
        """Pass a remaining timeout only when the injected boundary supports it."""
        try:
            parameters = inspect.signature(callable_object).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "timeout_ms" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        ):
            kwargs["timeout_ms"] = max(0, int(math.ceil(timeout_ms)))
        return callable_object(*args, **kwargs)

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return max(0.0, (perf_counter() - started) * 1_000)

    def run(self, value: Query | dict, *, stage_callback: Callable[[str], None] | None = None) -> Answer:
        started = perf_counter()
        stage_timings: dict[str, float] = {}

        def emit(stage: str) -> None:
            if stage_callback is None:
                return
            try:
                stage_callback(stage)
            except Exception:
                # Observability hooks are intentionally isolated from answer generation.
                return

        def measure(stage: str, stage_started: float) -> None:
            stage_timings[f"{stage}_ms"] = self._elapsed_ms(stage_started)

        try:
            preprocessing_started = perf_counter()
            emit("preprocessing")
            query = validate_query(value)
            measure("preprocessing", preprocessing_started)
            self._ensure_budget(started, self.deadline_ms, "preprocessing")

            retrieval_started = perf_counter()
            retrieval = self._call_with_timeout(
                self.retriever.retrieve,
                query.query,
                query.top_k,
                timeout_ms=self._ensure_budget(started, self.deadline_ms, "retrieval"),
            )
            measure("retrieval", retrieval_started)
            emit("embedding")
            emit("retrieval")
            emit("reranking")

            stage_timings["embedding_ms"] = retrieval.latency.embedding_ms
            stage_timings["vector_search_ms"] = retrieval.latency.search_ms
            stage_timings["reranking_ms"] = retrieval.latency.reranking_ms
            stage_timings["retrieval_total_ms"] = retrieval.latency.total_ms
            self._ensure_budget(started, self.deadline_ms, "retrieval")

            context_started = perf_counter()
            candidates = filter_relevant(retrieval.chunks, floor=self.relevance_floor)
            measure("context_construction", context_started)
            self._ensure_budget(started, self.deadline_ms, "context construction")

            generation_started = perf_counter()
            response = self._call_with_timeout(
                self.generator.generate,
                query,
                candidates,
                timeout_ms=self._ensure_budget(started, self.deadline_ms, "generation"),
            )
            measure("generation", generation_started)
            emit("generation")
            self._ensure_budget(started, self.deadline_ms, "generation")

            grounding_started = perf_counter()
            if self.grounding is None:
                grounding = self._call_with_timeout(
                    check_grounding,
                    response.text,
                    candidates,
                    timeout_ms=self._ensure_budget(started, self.deadline_ms, "grounding"),
                )
            else:
                grounding = self._call_with_timeout(
                    self.grounding.check,
                    response.text,
                    candidates,
                    timeout_ms=self._ensure_budget(started, self.deadline_ms, "grounding"),
                )
            measure("grounding", grounding_started)
            emit("grounding")
            self._ensure_budget(started, self.deadline_ms, "grounding")

            total_ms = max(
                self._elapsed_ms(started),
                retrieval.latency.total_ms,
                response.generation_ms,
                grounding.grounding_ms,
            )
            answer = Answer(
                request_id=query.request_id,
                answer=response.text,
                language=query.language,
                grounded=grounding.grounded,
                sources=tuple(Source(c.chunk_id, c.text, c.score, c.metadata) for c in candidates),
                latency=Latency(
                    total_ms=total_ms,
                    retrieval_total_ms=retrieval.latency.total_ms,
                    embedding_ms=retrieval.latency.embedding_ms,
                    retrieval_ms=retrieval.latency.search_ms,
                    reranking_ms=retrieval.latency.reranking_ms,
                    generation_ms=response.generation_ms,
                    grounding_ms=grounding.grounding_ms,
                ),
                _request_started_at=started,
                _deadline_ms=self.deadline_ms,
                _stage_timings=stage_timings,
            )
            self._ensure_budget(started, self.deadline_ms, "answer construction")
            return answer
        except InputGuardError as error:
            raise PipelineError(error.code, str(error)) from error
        except NoRelevantContextError as error:
            raise PipelineError(error.code, str(error)) from error
        except PipelineError:
            raise
        except TimeoutError as error:
            raise PipelineError("RAG_TIMEOUT", str(error), retryable=True) from error
        except Exception as error:
            raise PipelineError("RAG_ERROR", str(error)) from error
