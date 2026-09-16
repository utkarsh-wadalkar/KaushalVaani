"""Fast, deterministic grounding classifier with an injectable verifier."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Sequence

from retrieval.reranker import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class GroundingResult:
    grounded: bool
    score: float
    grounding_ms: float
    reason: str


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def check_grounding(
    answer: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    verifier: Callable[[str, Sequence[RetrievalCandidate]], bool] | None = None,
    timeout_ms: int = 25,
) -> GroundingResult:
    started = perf_counter()
    if verifier is not None:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(verifier, answer, candidates)
        try:
            grounded = bool(future.result(timeout=max(0, timeout_ms) / 1000))
            reason = "injected_verifier"
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            elapsed = (perf_counter() - started) * 1000
            return GroundingResult(False, 0.0, elapsed, "timeout")
        finally:
            if not future.done():
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True, cancel_futures=True)
    else:
        answer_tokens = _tokens(answer)
        context_tokens = set().union(*(_tokens(item.text) for item in candidates)) if candidates else set()
        overlap = len(answer_tokens & context_tokens) / max(1, len(answer_tokens))
        grounded = overlap >= 0.2
        reason = "lexical_overlap" if grounded else "insufficient_context_overlap"
    elapsed = (perf_counter() - started) * 1000
    if elapsed > timeout_ms:
        return GroundingResult(False, 0.0, elapsed, "timeout")
    return GroundingResult(grounded, 1.0 if grounded else 0.0, elapsed, reason)
