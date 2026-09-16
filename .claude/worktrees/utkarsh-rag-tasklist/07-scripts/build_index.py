"""Build a deterministic local vector snapshot from chunk JSONL."""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
import time
from dataclasses import asdict, fields
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1] / "03-ai-rag-engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from chunking.base import Chunk
from embeddings.base import Embedder, EmbeddingValidationError
from embeddings.provider import HashingEmbedder
from ingestion.metadata import DocumentMetadata
from retrieval.vector_store import InMemoryVectorStore, VectorPoint


def read_chunks(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        item["metadata"] = DocumentMetadata(**item["metadata"])
        yield Chunk(**{field.name: item[field.name] for field in fields(Chunk) if field.name in item})


def _chunk_fingerprint(chunk: Chunk) -> str:
    encoded = json.dumps(
        asdict(chunk),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _embedder_identity(embedder: Embedder) -> dict:
    if not hasattr(embedder, "config"):
        raise ValueError("embedder config is required for deterministic resume identity")
    config = embedder.config
    if not isinstance(config, dict):
        raise ValueError("embedder config must be a JSON-serializable mapping")
    try:
        canonical_config = json.loads(
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as error:
        raise ValueError("embedder config must be JSON-serializable") from error
    model_name = getattr(embedder, "model_name", None)
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("embedder model_name must be a non-empty string")
    if not isinstance(embedder.dimension, int) or embedder.dimension <= 0:
        raise ValueError("embedder dimension must be a positive integer")
    return {
        "model": model_name,
        "config": canonical_config,
        "dimension": embedder.dimension,
    }


def build_index(input_path: Path, output_path: Path, *, dimension: int | None = None, batch_size: int = 128, embedder: Embedder | None = None) -> dict:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if embedder is None:
        embedder = HashingEmbedder(dimension=dimension or 64)
    if dimension is not None and embedder.dimension != dimension:
        raise ValueError("embedder dimension does not match requested dimension")
    dimension = embedder.dimension
    embedder_identity = _embedder_identity(embedder)
    resumed_points = 0
    if output_path.exists():
        store = InMemoryVectorStore.load(output_path)
        if store.dimension != dimension:
            raise ValueError("existing snapshot dimension does not match requested dimension")
        if store.index_metadata.get("embedder") != embedder_identity:
            raise ValueError("existing snapshot embedder identity/config does not match")
        resumed_points = store.count
    else:
        store = InMemoryVectorStore(dimension=dimension)
    chunks = list(read_chunks(input_path))
    started = time.perf_counter()
    input_fingerprint = hashlib.sha256(
        "\n".join(_chunk_fingerprint(chunk) for chunk in chunks).encode("ascii")
    ).hexdigest()
    current = {point.chunk_id: point for point in store.points()}
    pending = []
    stale_ids = set(current)
    for chunk in chunks:
        fingerprint = _chunk_fingerprint(chunk)
        point = current.get(chunk.chunk_id)
        if point is None or point.payload.get("_chunk_fingerprint") != fingerprint:
            pending.append((chunk, fingerprint))
        stale_ids.discard(chunk.chunk_id)
    store.delete(tuple(stale_ids))
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = embedder.embed_batch([chunk.text for chunk, _ in batch])
        EmbeddingValidationError.validate(vectors, dimension=dimension, expected_count=len(batch))
        points = []
        for (chunk, fingerprint), vector in zip(batch, vectors.vectors):
            point = VectorPoint.from_chunk(chunk, vector)
            payload = dict(point.payload)
            payload["_chunk_fingerprint"] = fingerprint
            points.append(VectorPoint(point.chunk_id, point.vector, payload))
        store.upsert(points)
    store.index_metadata = {
        "input_fingerprint": input_fingerprint,
        "embedder": embedder_identity,
    }
    store.save(output_path)
    return {"points": store.count, "embedded_points": len(pending), "resumed_points": resumed_points, "deleted_points": len(stale_ids), "dimension": dimension, "elapsed_ms": (time.perf_counter() - started) * 1000, "model": embedder_identity["model"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--provider",
        choices=("hashing-fixture",),
        default="hashing-fixture",
        help="Fixture-only provider; no production embedding provider is selected",
    )
    parser.add_argument("--dimension", type=int, default=64)
    parser.add_argument("--hash-salt", default="echoquery")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args(argv)
    embedder = HashingEmbedder(dimension=args.dimension, salt=args.hash_salt)
    print(
        json.dumps(
            build_index(
                args.input,
                args.output,
                batch_size=args.batch_size,
                embedder=embedder,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
