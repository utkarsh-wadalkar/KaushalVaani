# EchoQuery Full Application Task List (Historical Snapshot)

> **Superseded by the 2026-09-05 audit.** The implementation described below is
> stored under an ignored directory and is not present in the tracked project.
> Use `CURRENT-TASKS.md` and `plan.md` as the current sources of truth.

**Historical purpose:** retained for comparison with the verified 2026-09-05
audit; it is no longer the active checklist.

**Current deployment decision:** frontend on Vercel; backend and RAG on a DigitalOcean Ubuntu Droplet; Nginx reverse proxy; Let's Encrypt via Certbot; DuckDNS hostname pointing to a DigitalOcean Reserved IP; Qdrant private inside Docker Compose. Qdrant must never be exposed to the public internet.

**Architecture boundary:** frontend audio and text requests use the existing WebSocket/HTTP contracts. FastAPI owns transport and integration. STT emits the normalized Transcript contract. The RAG engine consumes Query and produces Answer. The frontend consumes server WebSocket events and Answer. Offline ingestion, chunking, embedding, and index construction never run document chunking on the normal query path.

## Status legend

- `[x]` **Completed and locally verified** with the evidence named in the section.
- `[~]` **In progress**: code exists, but an integration, behavior, or verification gap remains.
- `[!]` **Blocked by external infrastructure or credentials**: the local implementation is ready or clearly bounded, but the gate cannot be exercised here.
- `[?]` **Pending human decision**: a production choice must be approved from benchmark evidence.
- `[ ]` **Pending verification**: implementation may exist, but the required evidence has not been produced.

## Evidence baseline

- `[x]` Repository, contracts, source tree, tests, and deployment files were inspected in this worktree.
- `[x]` Contract validator accepts five valid examples and rejects five invalid examples.
- `[x]` Python engine suite: 88 tests pass; two ingestion tests are skipped because `pyarrow` is not installed in this workspace.
- `[x]` Python `compileall` passes for the checked source roots.
- `[x]` Offline fixture harnesses exist for ingestion, chunking, embeddings, indexing, retrieval, reranking, grounding, and end-to-end latency.
- `[!]` No claim is made for live Sarvam, a real MSMARCO-XI corpus, a live Qdrant service, a DigitalOcean host, DuckDNS, Certbot, Vercel, or production latency until those systems are exercised.

## Phase 0 - Repository and architecture reconciliation

- `[x]` Inspect Git history/status, contracts, backend, frontend, external services, RAG engine, evaluation, and infrastructure.
- `[x]` Remove the old "do not touch teammate modules" restriction; this task now covers the complete application.
- `[x]` Record the Vercel/DigitalOcean/Nginx/Certbot/DuckDNS/private-Qdrant deployment decision.
- `[x]` Create the production environment guide at `notes/production-env-duckdns-digitalocean-vercel.md`.
- `[x]` Reconcile the three task documents with the current tree; continue synchronizing them after every completed phase.
- `[ ]` Add CI or pre-commit execution for contract validation and the Python test suite.

**Phase evidence:** on 2026-08-23 the synchronized documents were re-read; the engine suite reported 88 passing tests with two expected `pyarrow` skips, contract validation accepted five valid and rejected five invalid examples, Python compilation passed, and stale RAG-only ownership/deployment language was absent.

## Phase 1 - Dataset, ingestion, cleaning, and offline artifacts

### Dataset and provenance

- `[~]` Keep the pinned MSMARCO-XI revision in the loader and document its source, license, and access conditions.
- `[!]` Obtain and review the real corpus; the large raw dataset must stay off Git and off the production Droplet.
- `[ ]` Characterize counts, file format, length distribution, all eleven locales, and English versus non-English proportions.
- `[ ]` Create a deterministic held-out evaluation slice that is excluded from the production index.
- `[ ]` Record provenance and the held-out split in an ADR or evaluation document.

### Ingestion and cleaning

- `[x]` Stream parquet records without loading a whole language split into memory.
- `[x]` Validate nested passage/label arrays and preserve query, answer, language, passage, selection, and source metadata.
- `[x]` Normalize canonical text to Unicode NFC without stripping Indic characters.
- `[x]` Generate deterministic document IDs and byte-identical JSONL for repeated fixture runs.
- `[x]` Drop exact duplicates in the cleaner while preserving distinct source records with identical text.
- `[~]` Write and verify processed JSONL on the reviewed real corpus under `05-data/processed/`.
- `[ ]` Emit a keyed drop/duplicate report and run round-trip integrity tests using real samples from all eleven locales.

### Offline chunks and index inputs

- `[x]` Implement fixed-size, sentence-aware, and semantic chunk candidates behind one immutable interface.
- `[x]` Preserve parent document IDs, source metadata, language, offsets, overlap configuration, and strategy identity.
- `[~]` Benchmark all candidates on the reviewed corpus; no production strategy is frozen from fixture timing.
- `[~]` Write selected chunks under `05-data/chunks/` only after the strategy decision.

## Phase 2 - Embeddings, vector storage, retrieval, and reranking

### Embeddings and Qdrant

- `[x]` Define a batch embedding protocol and strict dimension/finite-value validation.
- `[x]` Provide a deterministic hashing embedder for tests and local demos only.
- `[x]` Provide resumable, atomic local index snapshots with metadata and model configuration.
- `[x]` Provide an optional Qdrant adapter with deterministic point UUIDs and payload preservation.
- `[~]` Add runtime provider selection from settings; production must fail closed instead of silently using the hashing fixture.
- `[!]` Run the multilingual candidate benchmark on deployment-like hardware and select a production embedding model, dimension, and distance metric.
- `[!]` Start private Qdrant, create the versioned collection, build the index, verify point/chunk counts, and spot-check at least three languages.
- `[?]` Record the embedding winner and collection layout in ADR 0002 and ADR 0005 after the benchmark.

### Retrieval and reranking

- `[x]` Implement query embedding, bounded `fetch_k`, top-k selection, immutable `RetrievedContext`, and latency attribution.
- `[x]` Implement fixture reranking and reject rerankers that drop, invent, duplicate, or mutate candidates.
- `[x]` Implement Recall@k, MRR@k, nDCG@k, language-direction breakdowns, and fixture reranking deltas.
- `[~]` Add production metadata filters and a bounded query cache only if benchmark evidence shows they help without compromising correctness.
- `[!]` Measure monolingual and cross-lingual retrieval separately, including per-locale worst cases, under realistic concurrency.
- `[?]` Keep or drop the reranker based on quality gain and hot-path latency; record ADR 0004.
- `[?]` Freeze fixed, sentence-aware, or semantic chunking from real quality/latency results; record ADR 0003.

## Phase 3 - Generation, guardrails, and orchestration

### Generation and model harness

- `[x]` Define immutable Query, Answer, Source, and Latency models matching the contracts.
- `[x]` Keep the prompt language-specific, context-only, and explicit about not inventing facts.
- `[x]` Provide a deterministic FixtureLLM for tests and an injected Sarvam generation boundary.
- `[~]` Implement the production Sarvam 105B HTTP client with structured request/response parsing, timeout, bounded retry, and provider error mapping.
- `[!]` Validate Sarvam credentials, current model ID, supported locale behavior, and live prompt responses across all eleven locales.
- `[x]` Treat `grounded: false` as a successful Answer; return `NO_RELEVANT_CONTEXT` before generation when no evidence passes the floor.

### Guardrails

- `[x]` Reject unsupported locales, malformed queries, overlong inputs, and known unsafe/prompt-injection markers.
- `[~]` Add explicit off-topic/relevance classification or calibrated relevance floors so the system can decline unsupported questions.
- `[x]` Run grounding validation after generation and return `grounded: false` on unsupported or timed-out verification.
- `[~]` Track grounded-false rate per locale and test agglutinative/Indic scripts with representative data.
- `[x]` Keep model calls inside a structured harness with typed inputs/outputs and recoverable errors; do not use a raw prompt-in/text-out path.

### Orchestrator and latency boundary

- `[x]` Coordinate validation, retrieval, reranking, context, generation, grounding, and Answer construction in one RAG entry point.
- `[x]` Preserve `request_id` and stage names through callbacks and typed errors.
- `[~]` Enforce `RAG_TOTAL_DEADLINE_MS` across the entire RAG request, including final serialization.
- `[~]` Include serialization in `total_ms`; keep `retrieval_total_ms`, generation, grounding, and stage attribution separate.
- `[~]` Stream stage events to the backend instead of discarding the callback.
- `[ ]` Add structured request logs and an in-process latency aggregation endpoint/dashboard suitable for deployment.

## Phase 4 - FastAPI integration

- `[~]` Keep FastAPI as a transport/integration boundary; do not duplicate RAG logic in routes.
- `[~]` Wire `POST /api/query` to the configured RAG pipeline with Pydantic validation, request ID propagation, typed error status mapping, and response serialization.
- `[~]` Register request logging and error middleware and ensure errors do not leak credentials or stack traces.
- `[~]` Make `/health` and `/ready` distinguish process health from settings, index, Qdrant, and provider readiness.
- `[ ]` Add backend integration tests using fixture providers for success, no context, unsafe input, unsupported locale, timeout, and malformed JSON.
- `[!]` Run the integration tests against live Sarvam/Qdrant only after credentials and a deployed index are supplied.

## Phase 5 - Sarvam STT and normalized transcript

- `[x]` Keep a provider-neutral STT protocol and deterministic FixtureSTT for local tests.
- `[~]` Implement the Sarvam STT adapter, request construction, response normalization, locale propagation, request IDs, and confidence handling.
- `[~]` Validate audio type/size/content and map provider timeout/error responses to the transcript boundary.
- `[~]` Measure STT latency as audio-to-transcript and keep it outside the 200 ms RAG SLO.
- `[!]` Verify live Sarvam STT credentials, supported audio formats, and all eleven locale paths.
- `[ ]` Add fixture integration tests that assert the normalized Transcript contract has no extra runtime fields in WebSocket transcript data.

## Phase 6 - WebSocket real-time flow

- `[~]` Validate `session_start`, binary audio frames, `audio_end`, and `cancel` against the existing client contract.
- `[~]` Send only contract-defined `processing`, `transcript`, `answer`, `error`, and `complete` events.
- `[~]` Use the configured STT provider instead of hard-coded FixtureSTT in the runtime path.
- `[~]` Forward RAG stage callbacks as processing events and preserve one request ID from connection to completion.
- `[ ]` Bound audio frame/session sizes, handle disconnects, cancellation, timeouts, and duplicate control events.
- `[ ]` Add an in-process WebSocket integration test covering text fixture audio through transcript and answer.

## Phase 7 - Frontend demo and API integration

- `[x]` Provide the Vite/React workspace, locale selector, text query form, evidence list, grounding badge, and latency strip.
- `[~]` Request microphone permission, record browser audio, send binary frames, and send `audio_end`.
- `[~]` Render transcript events, processing stages, answer events, errors, cancellation, and reconnect state.
- `[~]` Keep `grounded: false` as a successful low-evidence state, not a frontend error.
- `[ ]` Add `vite-env.d.ts`, a committed frontend lockfile, and a reproducible `npm ci && npm run build` verification.
- `[!]` Verify the deployed Vercel build against the production HTTPS/WSS origins after deployment credentials are available.

## Phase 8 - Configuration, Docker, and deployment

- `[x]` Maintain `.env.example` and the production variable guide without committing secrets.
- `[~]` Align all environment names with runtime settings; remove unused flags and ensure short `DUCKDNS_DOMAIN` semantics.
- `[~]` Complete Docker images for API and frontend and ensure the frontend build has a lockfile.
- `[~]` Keep Qdrant persistent and private; add health checks, restart policies, and dependency readiness.
- `[~]` Fix production host-Nginx connectivity: the current Compose `expose` does not publish API port 8000 to host Nginx. The production Compose stack needs only backend and private Qdrant because Vercel is the selected frontend target.
- `[~]` Make the deploy script load/validate operator environment and verify `/health` plus `/ready` after startup.
- `[!]` Provision the DigitalOcean Droplet, Reserved IP, DuckDNS record, Nginx, Certbot certificate, private Qdrant, and firewall externally.
- `[!]` Deploy backend/RAG and frontend to DigitalOcean/Vercel, then run external HTTPS/WSS smoke tests.

## Phase 9 - Evaluation and latency analytics

- `[x]` Provide fixture metrics for retrieval, grounding, and latency percentiles.
- `[x]` Separate cold-start and steady-state measurements in the local harness.
- `[~]` Expand the harness to report STT, RAG, and E2E P50/P70/P95/P100 separately and label fixture/local/production-like/concurrent runs.
- `[~]` Add every RAG stage: preprocessing, embedding, vector search, reranking, context construction, generation, grounding, and serialization.
- `[!]` Measure the real deployed pipeline over a reasonable multilingual query set; never present fixture numbers as production evidence.
- `[ ]` Publish the measured result and bottleneck analysis. The RAG P100 target is strictly `<200 ms`; configuration alone is not evidence.

## Phase 10 - Security, reliability, and end-to-end demo

- `[ ]` Run secret scans and inspect Git history for credentials or debug keys.
- `[ ]` Verify API/WebSocket request limits, validation, timeout behavior, safe error messages, and log redaction.
- `[ ]` Verify container restart behavior, health/readiness checks, Qdrant persistence, and index rollback/rebuild procedure.
- `[ ]` Demonstrate the complete flow: Vercel UI -> WSS audio -> Sarvam STT -> Query -> embedding -> Qdrant -> reranking -> Sarvam 105B -> grounding -> Answer -> frontend evidence/latency display.
- `[ ]` Confirm all eleven locales with representative fixture and provider-backed tests.
- `[ ]` Complete the final requirement audit; only then mark the application complete.

## Human-owned gates

The following cannot be honestly marked complete from this workspace: Sarvam API credentials and model access, reviewed MSMARCO-XI download/license, production embedding/reranker approval, DigitalOcean account/server, Reserved IP, DuckDNS token/DNS, Certbot issuance, Vercel project deployment, and external HTTPS/WSS smoke testing. The code and documentation should make each gate executable without silently substituting a fixture.

## Invariants

- Exactly eleven locales are supported; unsupported locales fail explicitly.
- Indic text is preserved and normalized with Unicode NFC during ingestion.
- Offline chunking/indexing is separate from the normal query path.
- `grounded: false` is a valid successful Answer.
- `NO_RELEVANT_CONTEXT` happens before generation.
- STT latency is reported separately from the RAG `<200 ms` target.
- No production claim is made from fixture-only measurements.
- Qdrant remains private and production secrets remain outside Git.
