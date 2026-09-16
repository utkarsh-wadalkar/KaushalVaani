from __future__ import annotations

import dataclasses
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from chunking.base import Chunk, ChunkingStrategy
from chunking.fixed import FixedChunkingStrategy
from chunking.semantic import SemanticChunkingStrategy
from chunking.sentence import SentenceChunkingStrategy
from chunking.strategy import build_candidate_strategies
from ingestion.metadata import CanonicalDocument, DocumentMetadata


BENCHMARK_PATH = ENGINE_ROOT.parent / "06-evaluation" / "benchmarks" / "chunking.py"


def load_benchmark_module():
    specification = importlib.util.spec_from_file_location(
        "chunking_benchmark",
        BENCHMARK_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("unable to load chunking benchmark module")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def sample_document(
    text: str = "abcdefghij",
    *,
    document_id: str = "doc-1",
    language: str = "hi-IN",
) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=document_id,
        text=text,
        language=language,
        source="fixture-corpus",
        metadata=DocumentMetadata(
            dataset_name="fixture-dataset",
            dataset_revision="fixture-revision",
            split="test",
            source_reference="fixture.jsonl",
            query_id=7,
            query_type="DESCRIPTION",
            source_language_tag="eng_Latn",
            target_language_tag="hin_Deva",
            passage_index=2,
            selected=True,
            variant="translated",
            query="प्रश्न?",
            english_query="Question?",
            answer="उत्तर।",
            english_answer="Answer.",
            parallel_document_id="doc-en",
            generation_metadata={"temperature": 0},
        ),
    )


class ChunkModelTests(unittest.TestCase):
    def test_chunk_is_immutable_and_strategy_implements_common_protocol(self) -> None:
        strategy: ChunkingStrategy = FixedChunkingStrategy(max_chars=5)
        chunk = strategy.chunk(sample_document())[0]

        self.assertIsInstance(chunk, Chunk)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            chunk.text = "changed"  # type: ignore[misc]


class FixedChunkingTests(unittest.TestCase):
    def test_fixed_chunks_preserve_offsets_overlap_and_document_metadata(self) -> None:
        document = sample_document()

        chunks = FixedChunkingStrategy(max_chars=4, overlap_chars=1).chunk(document)

        self.assertEqual([chunk.text for chunk in chunks], ["abcd", "defg", "ghij"])
        self.assertEqual(
            [(chunk.start_char, chunk.end_char) for chunk in chunks],
            [(0, 4), (3, 7), (6, 10)],
        )
        self.assertEqual([chunk.overlap_chars for chunk in chunks], [0, 1, 1])
        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1, 2])
        self.assertTrue(all(chunk.document_id == document.document_id for chunk in chunks))
        self.assertTrue(all(chunk.language == document.language for chunk in chunks))
        self.assertTrue(all(chunk.source == document.source for chunk in chunks))
        self.assertTrue(all(chunk.metadata == document.metadata for chunk in chunks))
        reconstructed = chunks[0].text + "".join(
            chunk.text[chunk.overlap_chars :] for chunk in chunks[1:]
        )
        self.assertEqual(reconstructed, document.text)
        self.assertTrue(all(chunk.text for chunk in chunks))

    def test_fixed_chunk_ids_ignore_mutable_source_text(self) -> None:
        strategy = FixedChunkingStrategy(max_chars=4, overlap_chars=1)
        original = strategy.chunk(sample_document("abcdefghij"))
        corrected = strategy.chunk(sample_document("abcXefghij"))

        self.assertEqual(
            [chunk.chunk_id for chunk in original],
            [chunk.chunk_id for chunk in corrected],
        )
        self.assertNotEqual(original[0].text, corrected[0].text)

    def test_fixed_chunk_ids_include_strategy_configuration(self) -> None:
        document = sample_document("abcdefghijkl")

        short = FixedChunkingStrategy(max_chars=4).chunk(document)
        wide = FixedChunkingStrategy(max_chars=6).chunk(document)

        self.assertNotEqual(short[0].chunk_id, wide[0].chunk_id)

    def test_fixed_configuration_rejects_invalid_sizes(self) -> None:
        for max_chars, overlap_chars in ((0, 0), (-1, 0), (4, -1), (4, 4), (4, 5)):
            with self.subTest(max_chars=max_chars, overlap_chars=overlap_chars):
                with self.assertRaises(ValueError):
                    FixedChunkingStrategy(
                        max_chars=max_chars,
                        overlap_chars=overlap_chars,
                    )

    def test_fixed_empty_document_emits_no_chunks(self) -> None:
        chunks = FixedChunkingStrategy(max_chars=4).chunk(sample_document(""))

        self.assertEqual(chunks, ())


class SentenceChunkingTests(unittest.TestCase):
    def test_sentence_chunking_recognizes_danda_double_danda_and_newline(self) -> None:
        document = sample_document("अ। ब॥ C!\nD?")

        chunks = SentenceChunkingStrategy(max_chars=8, overlap_sentences=1).chunk(
            document
        )

        self.assertEqual([chunk.text for chunk in chunks], ["अ। ब॥ ", "ब॥ C!\nD?"])
        self.assertEqual(
            [(chunk.start_char, chunk.end_char) for chunk in chunks],
            [(0, 6), (3, 11)],
        )
        self.assertEqual([chunk.overlap_chars for chunk in chunks], [0, 3])
        reconstructed = chunks[0].text + chunks[1].text[chunks[1].overlap_chars :]
        self.assertEqual(reconstructed, document.text)

    def test_sentence_chunking_preserves_oversized_sentence_without_data_loss(self) -> None:
        document = sample_document("Oversized sentence! Tiny.")

        chunks = SentenceChunkingStrategy(max_chars=8).chunk(document)

        self.assertEqual([chunk.text for chunk in chunks], ["Oversized sentence! ", "Tiny."])
        self.assertEqual(
            [(chunk.start_char, chunk.end_char) for chunk in chunks],
            [(0, 20), (20, 25)],
        )
        self.assertEqual("".join(chunk.text for chunk in chunks), document.text)

    def test_sentence_configuration_rejects_invalid_values(self) -> None:
        for max_chars, overlap_sentences in ((0, 0), (-1, 0), (8, -1)):
            with self.subTest(
                max_chars=max_chars,
                overlap_sentences=overlap_sentences,
            ):
                with self.assertRaises(ValueError):
                    SentenceChunkingStrategy(
                        max_chars=max_chars,
                        overlap_sentences=overlap_sentences,
                    )


class SemanticChunkingTests(unittest.TestCase):
    def test_semantic_chunking_breaks_at_low_similarity_with_sentence_overlap(self) -> None:
        document = sample_document("Alpha. Beta. Gamma. Delta.", language="en-IN")

        def similarity(left: str, right: str) -> float:
            pair = (left.strip(), right.strip())
            return 0.1 if pair == ("Beta.", "Gamma.") else 0.9

        chunks = SemanticChunkingStrategy(
            max_chars=100,
            similarity_threshold=0.5,
            scorer=similarity,
            scorer_id="fixture-scorer-v1",
            overlap_sentences=1,
        ).chunk(document)

        self.assertEqual(
            [chunk.text for chunk in chunks],
            ["Alpha. Beta. ", "Beta. Gamma. Delta."],
        )
        self.assertEqual(
            [(chunk.start_char, chunk.end_char) for chunk in chunks],
            [(0, 13), (7, 26)],
        )
        self.assertEqual([chunk.overlap_chars for chunk in chunks], [0, 6])

    def test_semantic_chunking_obeys_maximum_when_similarity_is_high(self) -> None:
        document = sample_document("One. Two. Three.", language="en-IN")

        chunks = SemanticChunkingStrategy(
            max_chars=10,
            similarity_threshold=0.5,
            scorer=lambda left, right: 1.0,
            scorer_id="always-similar",
        ).chunk(document)

        self.assertEqual([chunk.text for chunk in chunks], ["One. Two. ", "Three."])
        self.assertEqual(
            [(chunk.start_char, chunk.end_char) for chunk in chunks],
            [(0, 10), (10, 16)],
        )

    def test_semantic_configuration_rejects_invalid_values(self) -> None:
        valid_scorer = lambda left, right: 1.0
        invalid_configs = (
            {"max_chars": 0},
            {"similarity_threshold": -0.1},
            {"similarity_threshold": 1.1},
            {"overlap_sentences": -1},
            {"scorer_id": ""},
        )
        for overrides in invalid_configs:
            with self.subTest(overrides=overrides):
                config = {
                    "max_chars": 10,
                    "similarity_threshold": 0.5,
                    "scorer": valid_scorer,
                    "scorer_id": "fake",
                    "overlap_sentences": 0,
                }
                config.update(overrides)
                with self.assertRaises(ValueError):
                    SemanticChunkingStrategy(**config)


class StrategyConstructionTests(unittest.TestCase):
    def test_candidate_construction_preserves_only_explicit_ordered_strategies(self) -> None:
        fixed = FixedChunkingStrategy(max_chars=10)
        sentence = SentenceChunkingStrategy(max_chars=20)

        strategies = build_candidate_strategies(fixed, sentence)

        self.assertEqual(strategies, (fixed, sentence))
        self.assertFalse(hasattr(strategies, "winner"))

    def test_candidate_construction_rejects_duplicate_candidate_identity(self) -> None:
        fixed = FixedChunkingStrategy(max_chars=10)

        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_candidate_strategies(fixed, fixed)


class ChunkingBenchmarkTests(unittest.TestCase):
    def test_benchmark_aggregates_each_explicit_strategy_without_ranking(self) -> None:
        benchmark = load_benchmark_module()
        documents = [sample_document("abcdefghij"), sample_document("abcd", document_id="doc-2")]
        strategies = build_candidate_strategies(
            FixedChunkingStrategy(max_chars=4, overlap_chars=1),
            SentenceChunkingStrategy(max_chars=6),
        )
        times = iter((10.0, 10.5, 20.0, 20.25))

        report = benchmark.benchmark_chunking(
            documents,
            strategies,
            clock=lambda: next(times),
        )

        self.assertEqual(report["documents"], 2)
        self.assertEqual([result["strategy"] for result in report["strategies"]], ["fixed", "sentence"])
        fixed = report["strategies"][0]
        self.assertEqual(fixed["chunks"], 4)
        self.assertEqual(fixed["empty_chunks"], 0)
        self.assertEqual(fixed["min_chunk_chars"], 4)
        self.assertEqual(fixed["max_chunk_chars"], 4)
        self.assertEqual(fixed["mean_chunk_chars"], 4.0)
        self.assertEqual(fixed["duplicated_chars"], 2)
        self.assertEqual(fixed["elapsed_ms"], 500.0)
        self.assertEqual(
            fixed["throughput"],
            {"documents_per_second": 4.0, "chunks_per_second": 8.0},
        )
        self.assertNotIn("winner", report)
        self.assertNotIn("ranking", report)
        json.dumps(report, sort_keys=True)

    def test_processed_jsonl_cli_benchmarks_fixed_and_sentence_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "processed.jsonl"
            output = root / "chunking.json"
            documents = [sample_document("Hello. नमस्ते।", language="hi-IN")]
            source.write_text(
                "".join(
                    json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True)
                    + "\n"
                    for document in documents
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(BENCHMARK_PATH),
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--max-chars",
                    "8",
                    "--overlap-sentences",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            stdout_report = json.loads(completed.stdout)
            file_report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(stdout_report, file_report)
            self.assertEqual(stdout_report["documents"], 1)
            self.assertEqual(
                [item["strategy"] for item in stdout_report["strategies"]],
                ["fixed", "sentence"],
            )
            self.assertNotIn("winner", stdout_report)


if __name__ == "__main__":
    unittest.main()
