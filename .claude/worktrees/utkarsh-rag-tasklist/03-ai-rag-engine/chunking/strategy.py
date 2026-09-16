"""Explicit construction helpers for chunking benchmark candidates."""

from __future__ import annotations

from chunking.base import ChunkingStrategy


def build_candidate_strategies(
    *strategies: ChunkingStrategy,
) -> tuple[ChunkingStrategy, ...]:
    """Return explicitly supplied candidates without selecting a winner."""

    identities: set[tuple[str, str]] = set()
    for strategy in strategies:
        identity = (strategy.name, strategy.config_id)
        if identity in identities:
            raise ValueError(f"duplicate chunking candidate: {identity!r}")
        identities.add(identity)
    return tuple(strategies)
