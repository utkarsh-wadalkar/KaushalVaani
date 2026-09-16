"""Vector point models and offline/optional persistent stores."""

from __future__ import annotations

import json
import math
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from chunking.base import Chunk


def _validate_vector(vector: Sequence[float], dimension: int) -> tuple[float, ...]:
    if len(vector) != dimension:
        raise ValueError(f"expected vector dimension {dimension}, got {len(vector)}")
    try:
        values = tuple(float(value) for value in vector)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("vector values must be finite numbers") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError("vector values must be finite numbers")
    return values


@dataclass(frozen=True, slots=True)
class VectorPoint:
    chunk_id: str
    vector: tuple[float, ...]
    payload: Mapping[str, Any]

    @classmethod
    def from_chunk(cls, chunk: Chunk, vector: Sequence[float]) -> "VectorPoint":
        data = asdict(chunk)
        data["metadata"] = asdict(chunk.metadata)
        values = _validate_vector(vector, len(vector))
        return cls(chunk_id=chunk.chunk_id, vector=values, payload=data)


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: str
    score: float
    payload: Mapping[str, Any]


class InMemoryVectorStore:
    SNAPSHOT_VERSION = 2

    def __init__(self, dimension: int, *, index_metadata: Mapping[str, Any] | None = None) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension
        self.index_metadata = dict(index_metadata or {})
        self._points: dict[str, VectorPoint] = {}

    @property
    def count(self) -> int:
        return len(self._points)

    def upsert(self, points: Sequence[VectorPoint]) -> None:
        validated = [
            VectorPoint(
                point.chunk_id,
                _validate_vector(point.vector, self.dimension),
                dict(point.payload),
            )
            for point in points
        ]
        for point in validated:
            self._points[point.chunk_id] = point

    def get(self, chunk_id: str) -> VectorPoint:
        return self._points[chunk_id]

    def points(self) -> tuple[VectorPoint, ...]:
        return tuple(self._points[key] for key in sorted(self._points))

    def delete(self, chunk_ids: Sequence[str]) -> None:
        for chunk_id in chunk_ids:
            self._points.pop(chunk_id, None)

    def search(self, query_vector: Sequence[float], *, limit: int = 10) -> list[SearchResult]:
        query = _validate_vector(query_vector, self.dimension)
        if limit <= 0:
            raise ValueError("limit must be positive")
        query_norm = math.sqrt(sum(value * value for value in query)) or 1.0
        ranked = []
        for point in self._points.values():
            point_norm = math.sqrt(sum(value * value for value in point.vector)) or 1.0
            score = sum(a * b for a, b in zip(query, point.vector)) / (query_norm * point_norm)
            ranked.append(SearchResult(point.chunk_id, score, point.payload))
        ranked.sort(key=lambda item: (-item.score, item.chunk_id))
        return ranked[:limit]

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "snapshot_version": self.SNAPSHOT_VERSION,
            "dimension": self.dimension,
            "index_metadata": self.index_metadata,
            "points": [asdict(point) for point in self.points()],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @classmethod
    def load(cls, path: str | Path) -> "InMemoryVectorStore":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("snapshot_version") != cls.SNAPSHOT_VERSION:
            raise ValueError("unsupported vector snapshot version")
        store = cls(
            int(payload["dimension"]),
            index_metadata=payload.get("index_metadata", {}),
        )
        store.upsert([VectorPoint(item["chunk_id"], tuple(item["vector"]), item["payload"]) for item in payload["points"]])
        return store


class QdrantVectorStore:
    """Adapter for an injected client and an already-created compatible collection.

    Collection creation and vector-size/distance configuration are deliberately owned by
    deployment integration, not this offline baseline.
    """

    POINT_NAMESPACE = uuid.UUID("fd9e05f0-32e4-5ddd-90bd-74c35ae3dd84")

    def __init__(
        self,
        client: Any,
        collection: str,
        dimension: int,
        *,
        point_factory: Any | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if not collection:
            raise ValueError("collection must be non-empty")
        self.client = client
        self.collection = collection
        self.dimension = dimension
        self._point_factory = point_factory

    def _resolve_point_factory(self) -> Any:
        if self._point_factory is not None:
            return self._point_factory
        try:
            from qdrant_client.models import PointStruct
        except ImportError as error:
            raise RuntimeError(
                "Qdrant point_factory is required when optional qdrant-client is absent"
            ) from error
        return PointStruct

    def upsert(self, points: Sequence[VectorPoint]) -> None:
        point_factory = self._resolve_point_factory()
        validated = [
            (point, _validate_vector(point.vector, self.dimension))
            for point in points
        ]
        records = []
        for point, vector in validated:
            payload = dict(point.payload)
            payload["chunk_id"] = point.chunk_id
            records.append(
                point_factory(
                    id=str(uuid.uuid5(self.POINT_NAMESPACE, point.chunk_id)),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=self.collection, points=records, wait=True)

    def search(self, query_vector: Sequence[float], *, limit: int = 10) -> list[SearchResult]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        hits = self.client.query_points(collection_name=self.collection, query=_validate_vector(query_vector, self.dimension), limit=limit).points
        results = []
        for hit in hits:
            payload = dict(hit.payload or {})
            results.append(
                SearchResult(str(payload.get("chunk_id", hit.id)), float(hit.score), payload)
            )
        return results
