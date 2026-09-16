"""Offline chunking candidates for canonical documents."""

from .base import Chunk, ChunkingStrategy
from .fixed import FixedChunkingStrategy
from .semantic import SemanticChunkingStrategy, SimilarityScorer
from .sentence import SentenceChunkingStrategy
from .strategy import build_candidate_strategies

__all__ = [
    "Chunk",
    "ChunkingStrategy",
    "FixedChunkingStrategy",
    "SemanticChunkingStrategy",
    "SentenceChunkingStrategy",
    "SimilarityScorer",
    "build_candidate_strategies",
]
