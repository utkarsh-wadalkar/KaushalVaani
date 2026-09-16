import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from chunking.base import Chunk
from embeddings.base import EmbeddingValidationError
from embeddings.base import EmbeddingBatch
from embeddings.provider import HashingEmbedder
from ingestion.metadata import DocumentMetadata
from retrieval.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorPoint

BUILD_INDEX_PATH = ENGINE_ROOT.parent / "07-scripts" / "build_index.py"
BENCHMARK_PATH = ENGINE_ROOT.parent / "06-evaluation" / "benchmarks" / "embeddings.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_chunk(chunk_id: str = "chunk-1", text: str = "hello world") -> Chunk:
    metadata = DocumentMetadata(
        dataset_name="fixture",
        dataset_revision="r1",
        split="test",
        source_reference="fixture.jsonl",
        query_id=1,
        query_type="DESCRIPTION",
        source_language_tag="eng_Latn",
        target_language_tag="hin_Deva",
        passage_index=0,
        selected=True,
        variant="translated",
        query="प्रश्न",
        english_query="question",
        answer="उत्तर",
        english_answer="answer",
        parallel_document_id="doc-en",
        generation_metadata={"fixture": True},
    )
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        text=text,
        language="hi-IN",
        source="fixture",
        metadata=metadata,
        chunk_index=0,
        start_char=0,
        end_char=len(text),
        strategy_name="fixed",
        strategy_config_id="fixed-v1",
    )


class EmbeddingTests(unittest.TestCase):
    def test_hashing_embedder_is_deterministic_and_batch_validated(self):
        embedder = HashingEmbedder(dimension=8)
        first = embedder.embed_batch(["hello", "नमस्ते"])
        second = embedder.embed_batch(["hello", "नमस्ते"])
        self.assertEqual(first, second)
        self.assertEqual(first.dimension, 8)
        self.assertEqual(len(first.vectors), 2)
        self.assertTrue(all(len(vector) == 8 for vector in first.vectors))

    def test_embedder_rejects_non_finite_or_wrong_dimension_results(self):
        class BadEmbedder:
            dimension = 2

            def embed_batch(self, texts):
                return ((float("nan"),),) * len(texts)

        with self.assertRaises(EmbeddingValidationError):
            EmbeddingValidationError.validate(BadEmbedder().embed_batch(["x"]), dimension=2)

        with self.assertRaises(EmbeddingValidationError):
            EmbeddingValidationError.validate(((0.0, 1.0),), dimension=2, expected_count=2)

        with self.assertRaises(EmbeddingValidationError):
            EmbeddingValidationError.validate(((None, 1.0),), dimension=2)


class InMemoryStoreTests(unittest.TestCase):
    def test_upsert_is_idempotent_and_preserves_full_chunk_metadata(self):
        embedder = HashingEmbedder(dimension=8)
        vector = embedder.embed_batch(["hello"]).vectors[0]
        chunk = sample_chunk()
        store = InMemoryVectorStore(dimension=8)
        point = VectorPoint.from_chunk(chunk, vector)
        store.upsert([point])
        store.upsert([point])
        self.assertEqual(store.count, 1)
        self.assertEqual(store.get("chunk-1").payload["metadata"]["query_id"], 1)
        self.assertEqual(store.get("chunk-1").payload["text"], "hello world")

    def test_search_returns_cosine_ranked_results_with_metadata(self):
        embedder = HashingEmbedder(dimension=16)
        store = InMemoryVectorStore(dimension=16)
        chunks = [sample_chunk("a", "alpha"), sample_chunk("b", "beta")]
        store.upsert([VectorPoint.from_chunk(c, embedder.embed_batch([c.text]).vectors[0]) for c in chunks])
        result = store.search(embedder.embed_batch(["alpha"]).vectors[0], limit=1)
        self.assertEqual(result[0].chunk_id, "a")
        self.assertIn("metadata", result[0].payload)

    def test_snapshot_round_trip_supports_resumable_idempotent_index(self):
        embedder = HashingEmbedder(dimension=8)
        store = InMemoryVectorStore(dimension=8)
        chunk = sample_chunk()
        store.upsert([VectorPoint.from_chunk(chunk, embedder.embed_batch([chunk.text]).vectors[0])])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            store.save(path)
            resumed = InMemoryVectorStore.load(path)
            resumed.upsert(store.points())
            self.assertEqual(resumed.count, 1)
            self.assertEqual(resumed.get(chunk.chunk_id).payload, store.get(chunk.chunk_id).payload)
            json.loads(path.read_text(encoding="utf-8"))

    def test_upsert_validates_complete_batch_before_mutating(self):
        store = InMemoryVectorStore(dimension=2)
        good = VectorPoint("good", (1.0, 0.0), {})
        bad = VectorPoint("bad", (1.0,), {})
        with self.assertRaises(ValueError):
            store.upsert([good, bad])
        self.assertEqual(store.count, 0)

    def test_search_rejects_non_positive_limit(self):
        store = InMemoryVectorStore(dimension=2)
        with self.assertRaises(ValueError):
            store.search((1.0, 0.0), limit=0)


class QdrantAdapterTests(unittest.TestCase):
    def test_qdrant_adapter_maps_chunk_id_to_uuid_and_preserves_original_id(self):
        class Models:
            class PointStruct:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

        class Client:
            def __init__(self):
                self.calls = []

            def upsert(self, **kwargs):
                self.calls.append(kwargs)

        client = Client()
        store = QdrantVectorStore(client, "fixture", 2, point_factory=Models.PointStruct)
        store.upsert([VectorPoint.from_chunk(sample_chunk("chunk-stable"), (1.0, 0.0))])
        record = client.calls[0]["points"][0]
        self.assertRegex(record.id, r"^[0-9a-f-]{36}$")
        self.assertEqual(record.payload["chunk_id"], "chunk-stable")

    def test_qdrant_adapter_requires_factory_or_optional_dependency(self):
        store = QdrantVectorStore(object(), "fixture", 2)
        with self.assertRaisesRegex(RuntimeError, "point_factory|qdrant-client"):
            store.upsert([VectorPoint("x", (1.0, 0.0), {})])

    def test_qdrant_adapter_rejects_non_positive_limit_and_dimension(self):
        with self.assertRaises(ValueError):
            QdrantVectorStore(object(), "fixture", 0)


class IndexBuilderTests(unittest.TestCase):
    def test_builder_resumes_snapshot_without_reembedding_existing_chunks(self):
        module = load_module("build_index_fixture", BUILD_INDEX_PATH)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "chunks.jsonl"
            snapshot = root / "index.json"
            chunk = sample_chunk()
            source.write_text(json.dumps({
                "chunk_id": chunk.chunk_id, "document_id": chunk.document_id,
                "text": chunk.text, "language": chunk.language, "source": chunk.source,
                "metadata": __import__("dataclasses").asdict(chunk.metadata),
                "chunk_index": chunk.chunk_index, "start_char": chunk.start_char,
                "end_char": chunk.end_char, "strategy_name": chunk.strategy_name,
                "strategy_config_id": chunk.strategy_config_id,
                "overlap_chars": chunk.overlap_chars,
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            first = module.build_index(source, snapshot, dimension=8, batch_size=1)
            first_bytes = snapshot.read_bytes()
            second = module.build_index(source, snapshot, dimension=8, batch_size=1)
            self.assertEqual(first["embedded_points"], 1)
            self.assertEqual(second["embedded_points"], 0)
            self.assertEqual(second["resumed_points"], 1)
            self.assertEqual(snapshot.read_bytes(), first_bytes)

    def test_build_index_cli_writes_fixture_snapshot_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "chunks.jsonl"
            snapshot = root / "index.json"
            chunk = sample_chunk()
            source.write_text(
                json.dumps(
                    {
                        **{field: getattr(chunk, field) for field in (
                            "chunk_id", "document_id", "text", "language", "source",
                            "chunk_index", "start_char", "end_char", "strategy_name",
                            "strategy_config_id", "overlap_chars",
                        )},
                        "metadata": __import__("dataclasses").asdict(chunk.metadata),
                    },
                    ensure_ascii=False,
                ) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(BUILD_INDEX_PATH), "--input", str(source), "--output", str(snapshot), "--dimension", "8"],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["points"], 1)
            self.assertEqual(report["embedded_points"], 1)
            self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8"))["dimension"], 8)
            snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_data["snapshot_version"], 2)
            self.assertEqual(snapshot_data["index_metadata"]["embedder"]["model"], "hashing-baseline-test-v1")

    def test_builder_recomputes_changed_content_and_reconciles_deleted_chunks(self):
        module = load_module("build_index_reconcile", BUILD_INDEX_PATH)
        with tempfile.TemporaryDirectory() as directory:
            root, source, snapshot = Path(directory), Path(directory) / "chunks.jsonl", Path(directory) / "index.json"
            first, removed = sample_chunk("stable", "old"), sample_chunk("removed", "gone")

            def write(chunks):
                source.write_text("".join(json.dumps({**{field: getattr(chunk, field) for field in ("chunk_id", "document_id", "text", "language", "source", "chunk_index", "start_char", "end_char", "strategy_name", "strategy_config_id", "overlap_chars")}, "metadata": __import__("dataclasses").asdict(chunk.metadata)}, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")

            write([first, removed])
            module.build_index(source, snapshot, dimension=8)
            write([sample_chunk("stable", "new")])
            report = module.build_index(source, snapshot, dimension=8)
            loaded = InMemoryVectorStore.load(snapshot)
            self.assertEqual(report["embedded_points"], 1)
            self.assertEqual(report["deleted_points"], 1)
            self.assertEqual(loaded.count, 1)
            self.assertEqual(loaded.get("stable").payload["text"], "new")

    def test_builder_accepts_injected_embedder_and_rejects_cardinality_mismatch(self):
        module = load_module("build_index_injected", BUILD_INDEX_PATH)
        class ShortEmbedder:
            dimension = 2
            model_name = "short"
            config = {"salt": "x"}
            def embed_batch(self, texts):
                return EmbeddingBatch((), 2, self.model_name)

        with tempfile.TemporaryDirectory() as directory:
            root, source, snapshot = Path(directory), Path(directory) / "chunks.jsonl", Path(directory) / "index.json"
            chunk = sample_chunk()
            source.write_text(json.dumps({**{field: getattr(chunk, field) for field in ("chunk_id", "document_id", "text", "language", "source", "chunk_index", "start_char", "end_char", "strategy_name", "strategy_config_id", "overlap_chars")}, "metadata": __import__("dataclasses").asdict(chunk.metadata)}, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaises(EmbeddingValidationError):
                module.build_index(source, snapshot, embedder=ShortEmbedder())

    def test_builder_rejects_resume_when_embedder_config_changes(self):
        module = load_module("build_index_provider_config", BUILD_INDEX_PATH)
        with tempfile.TemporaryDirectory() as directory:
            source, snapshot = Path(directory) / "chunks.jsonl", Path(directory) / "index.json"
            chunk = sample_chunk()
            source.write_text(json.dumps({**{field: getattr(chunk, field) for field in ("chunk_id", "document_id", "text", "language", "source", "chunk_index", "start_char", "end_char", "strategy_name", "strategy_config_id", "overlap_chars")}, "metadata": __import__("dataclasses").asdict(chunk.metadata)}, ensure_ascii=False) + "\n", encoding="utf-8")
            module.build_index(source, snapshot, embedder=HashingEmbedder(8, salt="one"))
            with self.assertRaisesRegex(ValueError, "embedder"):
                module.build_index(source, snapshot, embedder=HashingEmbedder(8, salt="two"))

    def test_builder_rejects_embedder_missing_or_invalid_config_before_indexing(self):
        module = load_module("build_index_missing_config", BUILD_INDEX_PATH)

        class MissingConfig:
            dimension = 2
            model_name = "fixture"
            def embed_batch(self, texts):
                raise AssertionError("must not embed")

        class InvalidConfig(MissingConfig):
            config = {"bad": object()}

        with tempfile.TemporaryDirectory() as directory:
            source, snapshot = Path(directory) / "chunks.jsonl", Path(directory) / "index.json"
            source.write_text("", encoding="utf-8")
            for embedder in (MissingConfig(), InvalidConfig()):
                with self.subTest(embedder=type(embedder).__name__):
                    with self.assertRaisesRegex(ValueError, "config"):
                        module.build_index(source, snapshot, embedder=embedder)

    def test_same_model_and_dimension_with_different_config_cannot_resume(self):
        module = load_module("build_index_generic_config", BUILD_INDEX_PATH)

        class Configurable:
            dimension = 2
            model_name = "same"
            def __init__(self, revision):
                self.config = {"revision": revision}
            def embed_batch(self, texts):
                return EmbeddingBatch(tuple((1.0, 0.0) for _ in texts), 2, self.model_name)

        with tempfile.TemporaryDirectory() as directory:
            source, snapshot = Path(directory) / "chunks.jsonl", Path(directory) / "index.json"
            chunk = sample_chunk()
            source.write_text(json.dumps({**{field: getattr(chunk, field) for field in ("chunk_id", "document_id", "text", "language", "source", "chunk_index", "start_char", "end_char", "strategy_name", "strategy_config_id", "overlap_chars")}, "metadata": __import__("dataclasses").asdict(chunk.metadata)}, ensure_ascii=False) + "\n", encoding="utf-8")
            module.build_index(source, snapshot, embedder=Configurable("r1"))
            with self.assertRaisesRegex(ValueError, "embedder"):
                module.build_index(source, snapshot, embedder=Configurable("r2"))

    def test_cli_requires_explicit_fixture_provider_choice(self):
        completed = subprocess.run(
            [sys.executable, str(BUILD_INDEX_PATH), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--provider {hashing-fixture}", completed.stdout)
        self.assertIn("--hash-salt", completed.stdout)


class EmbeddingBenchmarkTests(unittest.TestCase):
    def test_benchmark_accepts_language_labeled_multilingual_fixtures_without_ranking(self):
        module = load_module("embedding_benchmark_fixture", BENCHMARK_PATH)
        fixtures = [
            {"language": "en-IN", "text": "Where is the station?"},
            {"language": "hi-IN", "text": "स्टेशन कहाँ है?"},
        ]
        report = module.benchmark_candidates([HashingEmbedder(dimension=8)], fixtures)
        self.assertEqual(report["languages"], ["en-IN", "hi-IN"])
        self.assertNotIn("winner", report)
        self.assertNotIn("ranking", report)
        self.assertEqual(report["candidates"][0]["fixtures"], 2)


if __name__ == "__main__":
    unittest.main()
