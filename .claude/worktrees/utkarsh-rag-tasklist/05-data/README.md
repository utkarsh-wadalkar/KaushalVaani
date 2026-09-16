# 05-data

Working data for the RAG engine. **All contents are gitignored** — only the directory structure and this file are tracked, via `.gitkeep`.

## Pipeline stages

```
raw/  ──ingestion──►  processed/  ──chunking──►  chunks/  ──embed+upsert──►  indexes/
```

| Directory | Written by | Read by | Contents |
|---|---|---|---|
| `raw/` | manual download (Phase 1) | `ingestion/loader.py` | AI4Bharat / MSMEAROC corpus, untouched |
| `processed/` | `07-scripts/ingest.py` | `chunking/*` | normalized `Document`s + metadata, NFC-cleaned |
| `chunks/` | `07-scripts/ingest.py` | `07-scripts/build_index.py`, benchmarks | `Chunk`s with parent `doc_id` linkage |
| `indexes/` | `07-scripts/build_index.py` | `retrieval/vector_store.py` | Qdrant local storage / snapshots |

Phase numbers refer to [`../Utkarsh-TASK.md`](../Utkarsh-TASK.md).

## Rules

- **Nothing here is a source of truth.** Every stage must be reproducible from `raw/` by re-running the scripts. If a file here cannot be regenerated, it belongs somewhere tracked.
- **Hold the eval slice out of `indexes/`.** If evaluation queries' gold chunks are in the index, Recall@k measures memorisation rather than retrieval. Keep the split explicit and reproducible.
- **`doc_id` must be stable across re-ingestion** — it becomes `sources[].id` in `answer.schema.json`, so unstable ids break frontend citations.
- **Benchmark results are gitignored too** (`06-evaluation/results/`). Any number used to justify a decision must be copied into the relevant ADR in `09-docs/decisions/`, or the evidence is lost.
- Re-running ingestion twice on the same `raw/` should produce byte-identical output.

## Local setup

The directories are tracked but empty. To start:

1. Inspect and approve the source before downloading. The current inspected source is `ai4bharat/MSMARCO-XI` at revision `bf5cdc1f26e581e519018e434db14edd1b77602b`; the Hindi train parquet contains `source_lang`, `target_lang`, nested `meta`, `Answer`, `query_id`, `query_type`, nested bilingual `passages`, `Eng_Query`, `Eng_Answer`, and `query`.
2. Keep the original parquet untouched under `raw/`.
3. Run `python 07-scripts/ingest.py --source 05-data/raw/<split>.parquet --dataset-revision bf5cdc1f26e581e519018e434db14edd1b77602b --output 05-data/processed/<split>.jsonl` to assert the reviewed local source revision and stream validated rows into canonical bilingual documents.
4. Review the processed output before adding chunking. Chunking, embeddings, and indexing are later milestones and must not run as part of ingestion.
