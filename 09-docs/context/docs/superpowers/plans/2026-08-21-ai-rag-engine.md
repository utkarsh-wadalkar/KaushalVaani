# EchoQuery Full Application Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for behavior changes and `superpowers:verification-before-completion` before checking off a task. Execute this plan task-by-task in the current linked worktree; preserve unrelated user changes.

**Goal:** make EchoQuery a complete multilingual voice-to-grounded-answer application with a verified fixture mode, production provider integration points, reproducible evaluation, and the selected Vercel plus DigitalOcean deployment path.

**Architecture:** React/Vite captures text or audio and communicates through HTTP/WSS with FastAPI. FastAPI validates transport contracts, invokes Sarvam STT for audio, and calls the single RAG pipeline. The RAG engine uses offline-built chunks and embeddings, private Qdrant retrieval, optional reranking, Sarvam 105B generation, grounding/guardrails, and structured Answer output. Production frontend is Vercel; backend/RAG/Qdrant run on a DigitalOcean Droplet behind Nginx, Certbot, and DuckDNS.

**Tech stack:** Python 3.11+, FastAPI, Pydantic, HTTPX, Qdrant client/server, React 18, TypeScript, Vite, Docker Compose, Nginx, Certbot, DuckDNS, Vercel, DigitalOcean.

**Authoritative checklist:** `notes/Utkarsh-TASK.md`

## Global constraints

- Preserve the existing Query, Transcript, Answer, and WebSocket contracts unless a verified blocker requires a coordinated contract change.
- Support exactly `en-IN`, `hi-IN`, `bn-IN`, `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `gu-IN`, `pa-IN`, and `od-IN`.
- Preserve Indic/non-ASCII text and normalize ingested text to Unicode NFC.
- Keep corpus ingestion, document chunking, corpus embedding, and index construction offline.
- Use Sarvam STT and Sarvam 105B in production; fixture providers are test/development-only and must never be silently selected in production.
- Select production chunking, embedding, Qdrant layout, and reranker behavior from measured multilingual evidence, recorded in ADR 0002-0005.
- Treat `grounded: false` as a successful low-evidence Answer; return `NO_RELEVANT_CONTEXT` before generation when evidence is absent.
- Measure STT, RAG, and E2E separately. RAG P100 must be strictly below 200 ms and includes final serialization; STT is excluded.
- Keep Qdrant private, secrets outside Git, and raw datasets off the production server.
- Deployment remains: Vercel frontend; DigitalOcean backend/RAG; Nginx; Certbot; DuckDNS; private Qdrant.

---

## Task 0: Reconcile documentation and establish the evidence baseline

**Files:**
- Modify: `notes/Utkarsh-TASK.md`
- Modify: `notes/docs/superpowers/plans/2026-08-21-ai-rag-engine.md`
- Modify: `notes/AI-RAG-TASKS.md`

**Interfaces:**
- Consumes: current Git state, contracts, source, test output, and deployment decisions.
- Produces: one phase hierarchy, one executable plan, and one concise evidence ledger.

- [x] Inspect Git history/status and all component directories.
- [x] Run the existing engine tests and contract validator.
- [x] Identify gaps that fixture tests do not cover: production providers, FastAPI integration, audio transport, readiness, live latency analytics, frontend build, and deployment connectivity.
- [x] Remove obsolete RAG-only ownership restrictions and synchronize the Vercel/DigitalOcean deployment decision.
- [x] Re-read all three files and verify every completed checkbox is supported by current evidence.

**Verification:**

```powershell
python -m unittest discover -s 03-ai-rag-engine/tests -v
python 07-scripts/validate_contracts.py
python -m compileall -q 01-backend-api 03-ai-rag-engine 04-external-services 06-evaluation 07-scripts
```

## Task 1: Correct full RAG timing, deadlines, and stage observability

**Files:**
- Modify: `03-ai-rag-engine/orchestration/pipeline.py`
- Modify: `03-ai-rag-engine/orchestration/stages.py`
- Modify: `03-ai-rag-engine/generation/schemas.py`
- Modify: `03-ai-rag-engine/observability/metrics.py`
- Modify: `03-ai-rag-engine/config/settings.py`
- Modify: `01-backend-api/app/schemas/response.py`
- Test: `03-ai-rag-engine/tests/test_pipeline.py`
- Test: `03-ai-rag-engine/tests/test_observability.py`

**Interfaces:**
- Consumes: `RAGPipeline.run(Query, stage_callback=...)`.
- Produces: deadline-enforced Answer creation plus a serialization function that finalizes `latency.total_ms` at the HTTP/WebSocket boundary.

- [ ] Write failing tests proving an over-deadline pipeline raises retryable `RAG_TIMEOUT`.
- [ ] Write a failing test proving final serialization is included in reported `total_ms` without corrupting component latency.
- [ ] Add explicit preprocessing, context-construction, and serialization measurements while retaining contract fields.
- [ ] Enforce one request deadline across retrieval, generation, grounding, and serialization; propagate remaining budget to provider calls where their interfaces support it.
- [ ] Emit structured per-stage timing events and keep callback failures isolated.
- [ ] Run focused tests, the full engine suite, contract validation, compile checks, and diff inspection.

## Task 2: Complete production-configured embeddings, Qdrant, reranking, and Sarvam generation

**Files:**
- Modify: `03-ai-rag-engine/config/settings.py`
- Modify: `03-ai-rag-engine/embeddings/provider.py`
- Modify: `03-ai-rag-engine/retrieval/vector_store.py`
- Modify: `03-ai-rag-engine/retrieval/reranker.py`
- Modify: `03-ai-rag-engine/generation/llm.py`
- Modify: `01-backend-api/app/api/dependencies.py`
- Modify: `.env.example`
- Test: `03-ai-rag-engine/tests/test_settings.py`
- Test: `03-ai-rag-engine/tests/test_vector_store.py`
- Test: `03-ai-rag-engine/tests/test_guardrails_generation.py`
- Create: `01-backend-api/tests/test_dependencies.py`

**Interfaces:**
- Produces: explicit provider factories selected by environment and a production pipeline using the configured embedding model, private Qdrant, optional reranker, and Sarvam generation client.
- Guarantees: development fixture mode is explicit; production rejects fixture providers, unresolved models, missing collection readiness, and missing credentials.

- [ ] Write failing settings/factory tests for fixture development and fail-closed production modes.
- [ ] Implement a structured HTTP client for Sarvam generation with model ID, language, timeout, bounded retries, response validation, and sanitized provider errors.
- [ ] Implement the benchmark-selected embedding provider adapter only after its model ID/dimension are supplied; keep candidate adapters in evaluation code.
- [ ] Construct Qdrant client/store from settings and verify collection existence, vector size, distance, and point readiness.
- [ ] Add optional production reranker construction; empty configuration means no reranker and contract `reranking_ms` remains null.
- [ ] Run factory tests without network, then separately label any live provider/Qdrant tests.

## Task 3: Complete FastAPI lifecycle, middleware, readiness, and query integration

**Files:**
- Modify: `01-backend-api/app/main.py`
- Modify: `01-backend-api/app/api/dependencies.py`
- Modify: `01-backend-api/app/api/routes/health.py`
- Modify: `01-backend-api/app/api/routes/query.py`
- Modify: `01-backend-api/app/middleware/errors.py`
- Modify: `01-backend-api/app/middleware/logging.py`
- Create: `01-backend-api/tests/test_api.py`

**Interfaces:**
- Consumes: one configured `RAGPipeline` and `QueryRequest`.
- Produces: `/health`, `/ready`, and `/api/query` with contract-valid responses and typed errors.

- [ ] Add fixture-mode FastAPI integration tests for successful query, no context, unsafe input, unsupported locale, timeout, malformed JSON, and request-ID propagation.
- [ ] Register logging/error middleware and sanitize unexpected failures.
- [ ] Initialize providers during application lifespan and close HTTP/Qdrant resources on shutdown.
- [ ] Make `/health` process-only and `/ready` verify settings, pipeline, index/Qdrant, and configured providers.
- [ ] Keep route code transport-only and map `PipelineError.retryable` consistently.
- [ ] Run backend tests plus the full engine/contract suite.

## Task 4: Implement and verify Sarvam STT normalization

**Files:**
- Modify: `04-external-services/stt/base.py`
- Modify: `04-external-services/stt/sarvam/config.py`
- Modify: `04-external-services/stt/sarvam/models.py`
- Modify: `04-external-services/stt/sarvam/client.py`
- Create: `04-external-services/stt/__init__.py`
- Create: `04-external-services/tests/test_sarvam_stt.py`
- Modify: `01-backend-api/app/api/dependencies.py`

**Interfaces:**
- Consumes: encoded audio bytes, request ID, optional supported locale.
- Produces: normalized `Transcript(request_id, text, language, is_final, provider, confidence)` plus measured STT duration kept outside RAG timing.

- [ ] Write failing adapter tests for request construction, supported locale mapping, response normalization, empty audio, oversize audio, timeout, and provider failure.
- [ ] Implement Sarvam HTTP request/response handling behind the existing STT protocol.
- [ ] Make fixture STT explicit in development/test and reject it in production.
- [ ] Validate transcript WebSocket data against the existing contract shape; do not send provider-only fields in that event.
- [ ] Run focused adapter tests and backend integration tests.

## Task 5: Complete and validate the WebSocket audio-to-answer flow

**Files:**
- Modify: `01-backend-api/app/api/routes/websocket.py`
- Modify: `01-backend-api/app/schemas/websocket.py`
- Create: `01-backend-api/tests/test_websocket.py`

**Interfaces:**
- Consumes: contract-defined `session_start`, binary audio frames, `audio_end`, and `cancel`.
- Produces: contract-defined `processing`, `transcript`, `answer`, `error`, and `complete` events.

- [ ] Write an in-process WebSocket test using fixture STT and fixture RAG from session start through successful completion.
- [ ] Add negative tests for invalid JSON, invalid/duplicate controls, request-ID mismatch, unsupported locale, empty/oversize audio, cancellation, and disconnect.
- [ ] Inject configured STT/RAG dependencies instead of hard-coding fixtures.
- [ ] Forward each RAG stage callback as a processing event in order.
- [ ] Bound session bytes and duration, enforce timeouts, and emit only contract-valid transcript data.
- [ ] Validate recorded server events with the contract validator.

## Task 6: Complete frontend microphone, transcript, answer, and reliability behavior

**Files:**
- Modify: `02-frontend/src/main.tsx`
- Modify: `02-frontend/src/styles.css`
- Create: `02-frontend/src/vite-env.d.ts`
- Modify: `02-frontend/package.json`
- Create: `02-frontend/package-lock.json`
- Optional test files: `02-frontend/src/*.test.tsx`

**Interfaces:**
- Consumes: Vite public API/WSS URLs and the existing WebSocket server event contract.
- Produces: usable text and voice query experiences with visible transcript, stages, answer, evidence, grounding, errors, and latency.

- [ ] Add frontend tests for event parsing/state transitions where the chosen test stack can run reliably.
- [ ] Request microphone permission and choose a browser-supported MediaRecorder MIME type.
- [ ] Send binary recording chunks and `audio_end` when the user stops; send `cancel` only for cancellation.
- [ ] Render transcript and answer events, keep `grounded: false` successful, and show reconnect/disconnect/error states.
- [ ] Use stable request IDs per request rather than deriving them from busy-state renders.
- [ ] Add the lockfile and run `npm ci`, type checking, production build, and responsive browser verification.

## Task 7: Complete latency aggregation, evaluation datasets, and benchmark commands

**Files:**
- Modify: `06-evaluation/datasets/queries.json`
- Modify: `06-evaluation/benchmarks/end_to_end.py`
- Modify: `06-evaluation/benchmarks/latency.py`
- Modify: `06-evaluation/benchmarks/embeddings.py`
- Modify: `06-evaluation/benchmarks/retrieval.py`
- Modify: `06-evaluation/metrics/latency.py`
- Modify: `07-scripts/benchmark.py`
- Modify: `09-docs/evaluation/benchmark-results.md`
- Add tests under: `03-ai-rag-engine/tests/`

**Interfaces:**
- Produces: reproducible fixture/local/production-like reports for STT, RAG, E2E, internal stages, retrieval quality, reranking quality, and grounding quality.

- [ ] Define a versioned multilingual query dataset covering all eleven locales, monolingual and cross-lingual cases, and held-out relevant chunk IDs.
- [ ] Report STT, RAG, and E2E P50/P70/P95/P100 independently.
- [ ] Report preprocessing, embedding, vector search, reranking, context, generation, grounding/guardrails, and serialization.
- [ ] Add concurrency controls and label single-request versus concurrent runs.
- [ ] Run the real corpus/model/provider benchmark when gates are available; never select winners or claim `<200 ms` from fixtures.
- [ ] Write ADR 0002-0005 with inline result summaries after decisions are made.

## Task 8: Make Docker and DigitalOcean deployment reproducible

**Files:**
- Modify: `08-infrastructure/docker/Dockerfile.api`
- Modify: `08-infrastructure/docker/Dockerfile.web`
- Modify: `08-infrastructure/compose/docker-compose.dev.yml`
- Modify: `08-infrastructure/compose/docker-compose.prod.yml`
- Modify: `08-infrastructure/nginx/nginx.conf`
- Modify: `08-infrastructure/deployment/server-setup.sh`
- Modify: `08-infrastructure/deployment/deploy.sh`
- Modify: `08-infrastructure/deployment/duckdns-update.sh`
- Modify: `.env.example`
- Modify: `notes/production-env-duckdns-digitalocean-vercel.md`

**Interfaces:**
- Produces: reproducible local Compose and a production backend/Qdrant stack reachable only through host Nginx; frontend remains Vercel-hosted.

- [ ] Fix API image import path and install behavior; run a real image build.
- [ ] Ensure `Dockerfile.web` uses a committed lockfile even though production frontend deploys on Vercel.
- [ ] Bind the API container only to `127.0.0.1:8000` for host Nginx or move Nginx into the Compose network; do not leave the current unreachable `expose` configuration.
- [ ] Keep Qdrant private with persistent storage and readiness checks.
- [ ] Make deployment scripts consume validated environment files, retain rollback-safe release paths, and verify health/readiness.
- [ ] Validate Compose configuration, Nginx syntax, certificate renewal instructions, DuckDNS update behavior, firewall rules, and log troubleshooting.
- [ ] Run external HTTPS/WSS smoke tests after the Droplet, Reserved IP, DuckDNS, certificate, and Vercel project exist.

## Task 9: Security, reliability, and final end-to-end verification

**Files:**
- Modify only files implicated by failed checks.
- Update: all three task documents and `09-docs/evaluation/benchmark-results.md`.

**Interfaces:**
- Produces: a requirement-by-requirement completion audit and a demonstrable application.

- [ ] Scan the working tree and Git history for secrets/debug credentials.
- [ ] Verify request/audio limits, locale/input validation, timeouts, safe provider errors, log redaction, and no public Qdrant port.
- [ ] Verify unit, integration, contract, compile/type, frontend build, Docker build, Compose, health/readiness, persistence, and WebSocket tests.
- [ ] Run a complete fixture E2E flow without paid calls.
- [ ] Run a real multilingual provider-backed E2E flow when credentials and infrastructure are supplied.
- [ ] Record STT/RAG/E2E percentiles and the RAG P100 pass/fail result honestly.
- [ ] Reconcile documentation and mark only requirements supported by direct evidence.
