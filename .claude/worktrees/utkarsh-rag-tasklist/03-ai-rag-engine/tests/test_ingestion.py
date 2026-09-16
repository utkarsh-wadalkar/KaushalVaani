from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from ingestion.cleaner import CleaningReport, clean_text, iter_clean_documents
from ingestion.loader import (
    DatasetSchemaError,
    iter_documents,
    iter_parquet_records,
    normalize_record,
    write_documents_jsonl,
)
from ingestion.metadata import DATASET_REVISION


def sample_record() -> dict:
    return {
        "source_lang": "eng_Latn",
        "target_lang": "hin_Deva",
        "meta": {
            "frequency_penalty": 0,
            "max_tokens": 256,
            "model_name": "dataset-generator",
            "presence_penalty": 0,
            "temperature": 0,
            "top_p": 1,
        },
        "Answer": "सौर ऊर्जा सूर्य के प्रकाश से बिजली बनाती है।",
        "query_id": 42,
        "query_type": "DESCRIPTION",
        "passages": {
            "English_passages": [
                "Solar panels convert sunlight into electricity.",
                "This passage is unrelated.",
            ],
            "Translated_passages": [
                "सौर पैनल सूर्य के प्रकाश को बिजली में बदलते हैं।",
                "यह अनुच्छेद असंबंधित है।",
            ],
            "is_selected": [1, 0],
        },
        "Eng_Query": "How does solar energy work?",
        "Eng_Answer": "Solar panels convert sunlight into electricity.",
        "query": "सौर ऊर्जा कैसे काम करती है?",
    }


class NormalizeRecordTests(unittest.TestCase):
    def test_rejects_misaligned_parallel_passage_arrays(self) -> None:
        raw = sample_record()
        raw["passages"]["is_selected"] = [1]

        with self.assertRaisesRegex(DatasetSchemaError, "same length"):
            normalize_record(raw)

    def test_rejects_non_string_passage_elements_with_schema_error(self) -> None:
        raw = sample_record()
        raw["passages"]["English_passages"][0] = 123

        with self.assertRaisesRegex(DatasetSchemaError, "non-string"):
            normalize_record(raw)

    def test_rejects_non_binary_selection_labels(self) -> None:
        for invalid_label in (0.5, True, False, -1, 2):
            with self.subTest(invalid_label=invalid_label):
                raw = sample_record()
                raw["passages"]["is_selected"] = [invalid_label, 0]

                with self.assertRaisesRegex(DatasetSchemaError, "0 or 1"):
                    normalize_record(raw)

    def test_preserves_nested_metadata(self) -> None:
        record = normalize_record(sample_record(), split="train")

        self.assertEqual(record.query_id, 42)
        self.assertEqual(record.target_language, "hi-IN")
        self.assertEqual(record.generation_metadata["model_name"], "dataset-generator")
        self.assertEqual(record.selection_labels, (1, 0))

    def test_rejects_falsy_non_mapping_metadata(self) -> None:
        raw = sample_record()
        raw["meta"] = []

        with self.assertRaisesRegex(DatasetSchemaError, "meta must be an object"):
            normalize_record(raw)

    def test_normalizes_all_canonical_text_fields_to_nfc(self) -> None:
        raw = sample_record()
        for key in ("query", "Eng_Query", "Answer", "Eng_Answer"):
            raw[key] = unicodedata.normalize("NFD", f"{raw[key]} café")
        raw["passages"]["English_passages"][0] = unicodedata.normalize(
            "NFD", "café passage"
        )

        record = normalize_record(raw)

        values = (
            record.query,
            record.english_query,
            record.answer,
            record.english_answer,
            record.english_passages[0],
        )
        self.assertTrue(
            all(unicodedata.is_normalized("NFC", value) for value in values)
        )


class DocumentTests(unittest.TestCase):
    def test_selected_passages_become_parallel_canonical_documents(self) -> None:
        documents = list(
            iter_documents([normalize_record(sample_record())], selected_only=True)
        )

        self.assertEqual(len(documents), 2)
        english, hindi = documents
        self.assertEqual(english.language, "en-IN")
        self.assertEqual(hindi.language, "hi-IN")
        self.assertTrue(english.metadata.selected)
        self.assertEqual(hindi.metadata.query_id, 42)
        self.assertEqual(hindi.metadata.passage_index, 0)
        self.assertEqual(hindi.metadata.variant, "translated")
        self.assertEqual(hindi.metadata.parallel_document_id, english.document_id)
        self.assertEqual(english.metadata.parallel_document_id, hindi.document_id)

    def test_document_ids_are_stable(self) -> None:
        first = list(iter_documents([normalize_record(sample_record())]))
        second = list(iter_documents([normalize_record(sample_record())]))

        self.assertEqual(
            [document.document_id for document in first],
            [document.document_id for document in second],
        )

    def test_all_passages_are_preserved_by_default(self) -> None:
        documents = list(iter_documents([normalize_record(sample_record())]))

        self.assertEqual(len(documents), 4)
        self.assertEqual(
            [document.metadata.selected for document in documents],
            [True, True, False, False],
        )

    def test_selected_only_mode_is_explicit(self) -> None:
        documents = list(
            iter_documents([normalize_record(sample_record())], selected_only=True)
        )

        self.assertEqual(len(documents), 2)
        self.assertTrue(all(document.metadata.selected for document in documents))

    def test_document_id_survives_passage_text_correction(self) -> None:
        original = list(iter_documents([normalize_record(sample_record())]))
        corrected_raw = sample_record()
        corrected_raw["passages"]["English_passages"][0] += " Corrected."
        corrected = list(iter_documents([normalize_record(corrected_raw)]))

        self.assertEqual(original[0].document_id, corrected[0].document_id)

    def test_document_ids_do_not_collide_across_target_languages(self) -> None:
        hindi = list(iter_documents([normalize_record(sample_record())]))
        bengali_raw = sample_record()
        bengali_raw["target_lang"] = "ben_Beng"
        bengali = list(iter_documents([normalize_record(bengali_raw)]))

        self.assertNotEqual(hindi[0].document_id, bengali[0].document_id)
        self.assertNotEqual(hindi[1].document_id, bengali[1].document_id)


class CleaningTests(unittest.TestCase):
    def test_nfc_normalization_preserves_indic_text(self) -> None:
        decomposed = unicodedata.normalize("NFD", "हिंदी café")

        cleaned = clean_text(f"  {decomposed}\r\n\r\n\r\nपाठ  ")

        self.assertEqual(unicodedata.normalize("NFC", cleaned), cleaned)
        self.assertIn("हिंदी", cleaned)
        self.assertIn("पाठ", cleaned)
        self.assertNotIn("\r", cleaned)

    def test_exact_duplicates_are_dropped_with_a_report(self) -> None:
        documents = list(iter_documents([normalize_record(sample_record())]))
        report = CleaningReport()

        result = list(
            iter_clean_documents([documents[0], documents[0]], report=report)
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(report.duplicates, 1)
        self.assertEqual(report.emitted, 1)

    def test_identical_text_from_distinct_source_records_is_preserved(self) -> None:
        first = list(iter_documents([normalize_record(sample_record())]))[0]
        second_raw = sample_record()
        second_raw["query_id"] = 43
        second = list(iter_documents([normalize_record(second_raw)]))[0]
        report = CleaningReport()

        result = list(iter_clean_documents([first, second], report=report))

        self.assertEqual(len(result), 2)
        self.assertEqual(report.duplicates, 0)


class SerializationTests(unittest.TestCase):
    def test_repeated_jsonl_writes_are_byte_identical(self) -> None:
        documents = list(iter_documents([normalize_record(sample_record())]))

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.jsonl"
            second = root / "second.jsonl"

            write_documents_jsonl(documents, first)
            write_documents_jsonl(documents, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            payload = json.loads(first.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["metadata"]["dataset_revision"], "bf5cdc1f26e581e519018e434db14edd1b77602b")


class ParquetTests(unittest.TestCase):
    def test_local_sources_require_explicit_pinned_revision(self) -> None:
        with self.assertRaisesRegex(ValueError, "dataset_revision is required"):
            list(iter_parquet_records("local.parquet"))

    def test_remote_sources_reject_unpinned_revisions(self) -> None:
        source = "hf://datasets/ai4bharat/MSMARCO-XI@main/train/hintrain.parquet"

        with self.assertRaisesRegex(ValueError, "pinned MSMARCO-XI revision"):
            list(iter_parquet_records(source))

    def test_streams_the_inspected_msmarco_xi_schema(self) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as error:
            self.skipTest(f"pyarrow is not installed: {error}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "sample.parquet"
            pq.write_table(pa.Table.from_pylist([sample_record()]), source)

            records = list(
                iter_parquet_records(
                    source,
                    batch_size=1,
                    dataset_revision=DATASET_REVISION,
                )
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].query_id, 42)
        self.assertEqual(records[0].translated_passages[0], "सौर पैनल सूर्य के प्रकाश को बिजली में बदलते हैं।")


class IngestionCliTests(unittest.TestCase):
    def test_cli_writes_processed_documents_and_summary(self) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as error:
            self.skipTest(f"pyarrow is not installed: {error}")

        script = ENGINE_ROOT.parent / "07-scripts" / "ingest.py"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.parquet"
            destination = root / "processed.jsonl"
            pq.write_table(pa.Table.from_pylist([sample_record()]), source)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--source",
                    str(source),
                    "--output",
                    str(destination),
                    "--batch-size",
                    "1",
                    "--dataset-revision",
                    DATASET_REVISION,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            summary = json.loads(completed.stdout)
            self.assertEqual(summary["records"], 1)
            self.assertEqual(summary["documents"], 4)
            self.assertEqual(len(destination.read_text(encoding="utf-8").splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
