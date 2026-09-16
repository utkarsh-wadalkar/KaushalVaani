# EchoQuery Deployment-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete EchoQuery inside the ignored experimental workspace as a
tested, measurable, deployable multilingual voice-enabled RAG application,
without committing or pushing its source to GitHub.

**Architecture:** React/Vite streams binary microphone frames to FastAPI.
FastAPI streams the audio to Saaras v3, waits for one finalized utterance,
normalizes it to the Transcript contract, and invokes the RAG pipeline exactly
once. RAG embeds the query, retrieves from private Qdrant, optionally reranks,
generates with Sarvam-105B, validates grounding, and returns a contract-valid
Answer with sources and latency.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, HTTPX, Sarvam Saaras v3,
Sarvam-105B, sentence-transformers, Qdrant, React, TypeScript, Vite, Vitest,
Docker Compose, Nginx, Certbot, DuckDNS, DigitalOcean, and Vercel.

**Spec:** `CURRENT-TASKS.md`,
`production-env-duckdns-digitalocean-vercel.md`, the official HH Goa 2026
Shortlisting Task 2 brief supplied by the user, and canonical schemas copied
from the repository's `00-contracts/` directory.

## Global Constraints

- Production STT is Sarvam `saaras:v3`.
- Stream audio to STT, but never invoke RAG for partial transcripts.
- Invoke RAG once after a nonempty finalized utterance.
- Use `sarvam-105b` for answer generation.
- Support exactly `en-IN`, `hi-IN`, `bn-IN`, `ta-IN`, `te-IN`, `kn-IN`,
  `ml-IN`, `mr-IN`, `gu-IN`, `pa-IN`, and `od-IN`.
- Preserve the user's language; do not add a translation layer.
- Keep corpus chunking, corpus embedding, and index construction offline.
- Compare fixed, sentence-aware, and semantic chunking before freezing one.
- Complete online RAG through final serialization has a strict 200 ms target.
- Report P50, P70, and P100 for STT, complete RAG, and voice end-to-end.
- Keep `grounded: false` as a valid successful Answer.
- Keep Qdrant private and all secrets outside Git and browser bundles.
- Preserve `.claude/` and `notes/` during experimentation.
- Make every code and documentation change inside
  `.claude/worktrees/utkarsh-rag-tasklist/`.
- Do not commit, push, open a pull request, or promote files into the tracked
  repository unless the user explicitly changes this decision.
- Replace Git rollback with timestamped source archives, SHA-256 manifests, and
  a checkpoint log.

---

## Current State

The project is not deployable. The experiment intentionally lives under
`.claude/worktrees/utkarsh-rag-tasklist/` and is ignored by the parent
repository. It is not a registered Git worktree and has no independent Git
metadata, so Git commands cannot roll its files back. Local checkpoints provide
rollback, and release archives provide reproducible deployment without GitHub.

The staged suite currently reports:

```text
Ran 93 tests
90 passed
1 error: contracts missing from the nested staging root
2 skipped: pyarrow unavailable
```

The staged implementation has no complete backend or frontend, and its Saaras
adapter files are empty. Baseline stabilization must therefore precede feature
work.

## Manual Inputs

### Needed before Task 1

1. No further approval is needed for the workspace location: the user confirmed
   the ignored experiment is the working baseline.
2. Confirm local Docker Qdrant for development, unless Qdrant Cloud is preferred.
3. State the disk budget available for MSMARCO-XI and model caches.

### Needed before live provider tests

1. Put a valid `SARVAM_API_KEY` in the root `.env`; do not send it in chat.
2. Verify the key can call Saaras v3 and `sarvam-105b`.

### Needed only before public deployment

1. DigitalOcean Droplet and Reserved IP.
2. DuckDNS label and token.
3. Vercel project and its exact production origin.
4. Certificate-renewal email and preferred deployment region.

Local baseline stabilization, fixture implementation, tests, and container
validation can
proceed before public infrastructure exists.

---

### Task 1: Establish a self-contained experimental baseline and rollback system

**Files:**

- Modify: `.claude/worktrees/utkarsh-rag-tasklist/pyproject.toml`
- Create: `.claude/worktrees/utkarsh-rag-tasklist/00-contracts/**`
- Create: `.claude/worktrees/utkarsh-rag-tasklist/.env.example`
- Create: `.claude/worktrees/utkarsh-rag-tasklist/.checkpoints/`
- Create: `.claude/worktrees/utkarsh-rag-tasklist/notes/checkpoint-log.md`
- Modify: `.claude/worktrees/utkarsh-rag-tasklist/03-ai-rag-engine/tests/test_contracts.py`

**Interfaces:**

- Consumes: the current ignored prototype plus read-only copies of canonical
  parent contracts and the environment template.
- Produces: a self-contained experiment with local rollback checkpoints and a
  reproducible green baseline.

- [ ] **Step 1: Record the baseline inventory**

```powershell
Set-Location .claude/worktrees/utkarsh-rag-tasklist
rg --files
python -m unittest discover -s 03-ai-rag-engine/tests -v
```

- [ ] **Step 2: Create the checkpoint policy**

Snapshots include source, tests, contracts, manifests, configuration templates,
and notes. They exclude `.env`, `.checkpoints/`, `__pycache__/`, `*.pyc`,
raw/processed data, chunks, indexes, model weights, notebook outputs, and
generated benchmark results.

- [ ] **Step 3: Create the initial checkpoint**

Create a timestamped source archive under `.checkpoints/`, write its SHA-256
hash and included-file manifest, and add the exact restore command to
`notes/checkpoint-log.md`. Never overwrite an earlier checkpoint.

- [ ] **Step 4: Make the experiment self-contained**

Copy the parent contract files and `.env.example` into the experimental root.
Repair tests and scripts to resolve these local copies. Reconcile
`pyproject.toml` with imports and install `.[dev]` plus `pyarrow`.

- [ ] **Step 5: Verify and log the experimental baseline**

```powershell
python 07-scripts/validate_contracts.py
python -m unittest discover -s 03-ai-rag-engine/tests -v
python -m compileall -q 01-backend-api 03-ai-rag-engine 04-external-services 06-evaluation 07-scripts
```

Expected: no missing-contract error, no unintended skip, and a documented
checkpoint capable of restoring the baseline without Git.

---

### Task 2: Freeze valid contracts and executable examples

**Files:**

- Modify: `00-contracts/answer.schema.json`
- Modify: `00-contracts/query.schema.json`
- Modify: `00-contracts/transcript.schema.json`
- Modify: `00-contracts/websocket-client-events.schema.json`
- Modify: `00-contracts/websocket-server-events.schema.json`
- Create: `00-contracts/examples/*.valid.json`
- Create: `00-contracts/examples/*.invalid.json`
- Modify: `07-scripts/validate_contracts.py`
- Test: `03-ai-rag-engine/tests/test_contracts.py`

**Interfaces:**

- Produces: Draft 2020-12 schemas that validate independently and as one
  registered schema set.
- Guarantees: event and nested Answer request IDs agree in application code;
  transcript events contain only contract fields.

- [ ] **Step 1: Add failing event-schema tests**

Cover all valid event variants plus unknown properties, invalid locales, empty
IDs, invalid completion states, and an unregistered Answer reference.

- [ ] **Step 2: Repair WebSocket composition**

Replace the incompatible `allOf` plus `additionalProperties: false` inheritance
with complete event objects or a proven `unevaluatedProperties: false` design.

- [ ] **Step 3: Align latency semantics**

`latency.total_ms` measures complete online RAG through serialization.
`embedding_ms`, `retrieval_ms`, `reranking_ms`, and `generation_ms` remain
components. Internal stages stay out of the public contract unless a coordinated
revision explicitly adds them.

- [ ] **Step 4: Register schema IDs locally**

Load every contract by canonical `$id` so the Answer reference resolves without
network access.

- [ ] **Step 5: Verify contracts**

```powershell
python 07-scripts/validate_contracts.py
python -m unittest 03-ai-rag-engine.tests.test_contracts -v
```

---

### Task 3: Make configuration and provider construction reproducible

**Files:**

- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `03-ai-rag-engine/config/settings.py`
- Modify: `03-ai-rag-engine/embeddings/provider.py`
- Modify: `03-ai-rag-engine/retrieval/vector_store.py`
- Modify: `03-ai-rag-engine/retrieval/reranker.py`
- Modify: `03-ai-rag-engine/generation/llm.py`
- Create: `01-backend-api/app/api/dependencies.py`
- Test: `03-ai-rag-engine/tests/test_settings.py`
- Create: `01-backend-api/tests/test_dependencies.py`

**Interfaces:**

```python
def build_embedder(settings: Settings) -> Embedder: ...
def build_vector_store(settings: Settings) -> VectorStore: ...
def build_generator(settings: Settings) -> Generator: ...
def build_pipeline(settings: Settings) -> RAGPipeline: ...
```

- [ ] **Step 1: Write failing factory tests**

Cover the documented environment names, missing Sarvam key, unresolved model,
invalid Qdrant URL, vector mismatch, fixture provider in production, and valid
fixture construction.

- [ ] **Step 2: Reconcile environment names**

Use one name per setting. Resolve the current mismatch between `VECTOR_DB_*` and
staged `QDRANT_*` readers, and between `LLM_MODEL` and
`SARVAM_LLM_MODEL`.

- [ ] **Step 3: Construct production providers once**

Build the embedder, Qdrant store, optional reranker, and Sarvam generator during
FastAPI lifespan. Production rejects silent fixture fallback.

- [ ] **Step 4: Validate readiness**

Check collection existence, vector dimension, distance, point count, model IDs,
and credentials without logging secrets.

- [ ] **Step 5: Verify installation and factories**

```powershell
python -m pip install -e '.[dev]'
python -m unittest 03-ai-rag-engine.tests.test_settings -v
python -m unittest discover -s 01-backend-api/tests -v
```

---

### Task 4: Build and benchmark the multilingual offline index

**Files:**

- Modify: `03-ai-rag-engine/ingestion/*.py`
- Modify: `03-ai-rag-engine/chunking/*.py`
- Modify: `07-scripts/ingest.py`
- Modify: `07-scripts/build_index.py`
- Modify: `06-evaluation/benchmarks/chunking.py`
- Modify: `06-evaluation/benchmarks/embeddings.py`
- Create: `09-docs/decisions/0002-embedding-model.md`
- Create: `09-docs/decisions/0003-chunking-strategy.md`
- Create: `09-docs/decisions/0004-reranker.md`
- Create: `09-docs/decisions/0005-qdrant-layout.md`

**Interfaces:**

- Produces: deterministic processed JSONL, chunks, a held-out query set, a
  versioned Qdrant collection, and an artifact manifest containing dataset
  revision, strategy, embedding model, dimension, distance, and counts.

- [ ] **Step 1: Pin and inspect an eleven-locale subset**

Record revision, terms, row counts, deterministic sample IDs, length
distribution, and language mapping, including dataset `or` to application
`od-IN`.

- [ ] **Step 2: Create the held-out split**

Exclude held-out queries and answers from indexed material and hash the split
manifest for repeatability.

- [ ] **Step 3: Benchmark chunk strategies**

Compare fixed, sentence-aware, and semantic strategies on retrieval quality,
chunk count, build time, query latency, and storage.

- [ ] **Step 4: Benchmark embeddings and reranking**

Measure Recall@k, MRR@k, nDCG@k, P50/P70/P100, worst-locale quality, and
monolingual/cross-lingual behavior on deployment-like hardware.

- [ ] **Step 5: Record decisions and build Qdrant**

Write ADR 0002-0005, create the versioned collection, upload idempotently, and
verify point counts and representative searches.

---

### Task 5: Complete the bounded RAG pipeline

**Files:**

- Modify: `03-ai-rag-engine/orchestration/pipeline.py`
- Modify: `03-ai-rag-engine/orchestration/errors.py`
- Modify: `03-ai-rag-engine/observability/metrics.py`
- Modify: `03-ai-rag-engine/generation/llm.py`
- Modify: `03-ai-rag-engine/guardrails/*.py`
- Test: `03-ai-rag-engine/tests/test_pipeline.py`
- Test: `03-ai-rag-engine/tests/test_guardrails_generation.py`
- Test: `03-ai-rag-engine/tests/test_observability.py`

**Interfaces:**

```python
def run(
    self,
    query: Query | dict,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> Answer: ...
```

- [ ] **Step 1: Add failing production-boundary tests**

Cover remaining-budget propagation, timeout, malformed provider output, empty
context, `grounded: false`, callback failure, request-ID preservation, and
serialization crossing the deadline.

- [ ] **Step 2: Implement Sarvam-105B generation**

Send bounded context and same-language instructions, disable unnecessary
reasoning, cap output, validate responses, retry only transient failures within
the remaining budget, and sanitize errors.

- [ ] **Step 3: Complete guardrails**

Reject malformed, unsafe, unsupported-language, and off-topic input; return
`NO_RELEVANT_CONTEXT` before generation; return a successful ungrounded Answer
when evidence validation does not support the output.

- [ ] **Step 4: Finalize timing**

Measure one wall clock from accepted Query through serialization. Attribute
embedding, retrieval, reranking, generation, grounding, and serialization
without summing overlapping timers.

- [ ] **Step 5: Separate fixture and live verification**

Fixture tests remain deterministic and free. Live tests are opt-in and clearly
skipped when credentials are absent.

---

### Task 6: Implement FastAPI, Saaras v3, and the WebSocket state machine

**Files:**

- Modify: `01-backend-api/app/main.py`
- Modify: `01-backend-api/app/api/dependencies.py`
- Modify: `01-backend-api/app/api/routes/health.py`
- Modify: `01-backend-api/app/api/routes/query.py`
- Modify: `01-backend-api/app/api/routes/websocket.py`
- Modify: `01-backend-api/app/middleware/*.py`
- Modify: `04-external-services/stt/base.py`
- Modify: `04-external-services/stt/sarvam/config.py`
- Modify: `04-external-services/stt/sarvam/models.py`
- Modify: `04-external-services/stt/sarvam/client.py`
- Create: `01-backend-api/tests/test_api.py`
- Create: `01-backend-api/tests/test_websocket.py`
- Create: `04-external-services/tests/test_sarvam_stt.py`

**Interfaces:**

```python
async def transcribe_final(
    audio: bytes,
    *,
    request_id: str,
    language: str | None,
) -> Transcript: ...
```

WebSocket states are `idle -> receiving_audio -> transcribing -> rag_running ->
complete`, with cancellation and failure terminal paths.

- [ ] **Step 1: Write fixture integration tests**

Cover health/readiness, session start, binary frames, audio end, one final
transcript, stage events, Answer, completion, cancellation, duplicate controls,
oversize audio, disconnect, and request-ID mismatch.

- [ ] **Step 2: Implement Saaras v3 streaming**

Connect to `wss://api.sarvam.ai/speech-to-text/ws`, send supported audio,
consume the finalized utterance, normalize provider data, and never call RAG for
an unstable fragment.

- [ ] **Step 3: Implement lifecycle and readiness**

Create providers once, close them on shutdown, keep `/health` process-only, and
make `/ready` inspect configuration, Qdrant/index, and providers.

- [ ] **Step 4: Enforce limits and safe errors**

Bound frame size, session bytes, duration, concurrency, and timeouts. Never emit
stack traces or credentials.

- [ ] **Step 5: Validate every captured event**

Run server messages through the contract validator and prove RAG executes once
per finalized utterance.

---

### Task 7: Build the React/Vite voice interface

**Files:**

- Create: `02-frontend/package.json`
- Create: `02-frontend/package-lock.json`
- Create: `02-frontend/tsconfig.json`
- Create: `02-frontend/vite.config.ts`
- Create: `02-frontend/src/vite-env.d.ts`
- Create: `02-frontend/src/main.tsx`
- Create: `02-frontend/src/App.tsx`
- Create: `02-frontend/src/lib/websocket.ts`
- Create: `02-frontend/src/lib/audio.ts`
- Create: `02-frontend/src/lib/contracts.ts`
- Create: `02-frontend/src/**/*.test.tsx`

**Interfaces:**

- Sends: `session_start`, binary frames, `audio_end`, and `cancel`.
- Receives: `processing`, `transcript`, `answer`, `error`, and `complete`.

- [ ] **Step 1: Test parsers and state transitions**

Cover every event, unknown events, request mismatch, successful
`grounded: false`, cancellation, disconnection, and subsequent requests.

- [ ] **Step 2: Implement microphone capture**

Ask permission after user action, select a supported MIME type, stream binary
chunks, stop tracks on every terminal path, and send `audio_end` only for normal
completion.

- [ ] **Step 3: Render the lifecycle**

Show final transcript, processing stages, answer, evidence, grounding, errors,
and latency. Never submit partial text to RAG.

- [ ] **Step 4: Add connection reliability**

Use one request ID per attempt, prevent double submission, distinguish retry
from cancellation, and expose actionable audio/WebSocket failures.

- [ ] **Step 5: Verify a clean build**

```powershell
Set-Location 02-frontend
npm ci
npm run test
npm run typecheck
npm run build
```

---

### Task 8: Produce official evaluation evidence

**Files:**

- Modify: `06-evaluation/datasets/queries.json`
- Modify: `06-evaluation/benchmarks/retrieval.py`
- Modify: `06-evaluation/benchmarks/latency.py`
- Modify: `06-evaluation/benchmarks/end_to_end.py`
- Modify: `07-scripts/benchmark.py`
- Modify: `09-docs/evaluation/benchmark-results.md`

**Interfaces:**

The benchmark emits JSON and Markdown containing environment, source-manifest
hash, corpus and index versions, models, query count, concurrency, cold/warm
classification, failures, and P50/P70/P100.

- [ ] **Step 1: Build the multilingual query suite**

Cover eleven locales, monolingual/cross-lingual retrieval, off-topic questions,
unsafe input, missing evidence, and grounded/ungrounded results.

- [ ] **Step 2: Measure three clocks**

Measure STT, complete RAG, and audio-end-to-final-answer separately. Do not
substitute time-to-first-token for final generation.

- [ ] **Step 3: Run cold, warm, and concurrent benchmarks**

Use one versioned suite and label every run. P100 is the maximum observed
completed request.

- [ ] **Step 4: Publish pass or failure honestly**

State whether complete RAG P100 is strictly below 200 ms. If it misses, preserve
the measurement and identify the bottleneck.

- [ ] **Step 5: Compare optimizations**

Preserve prior runs and compare quality, latency, cost, and failure rate so
speed changes cannot silently degrade answers.

---

### Task 9: Make deployment reproducible and private

**Files:**

- Modify: `08-infrastructure/docker/Dockerfile.api`
- Modify: `08-infrastructure/compose/docker-compose.dev.yml`
- Modify: `08-infrastructure/compose/docker-compose.prod.yml`
- Modify: `08-infrastructure/nginx/nginx.conf`
- Modify: `08-infrastructure/deployment/server-setup.sh`
- Modify: `08-infrastructure/deployment/deploy.sh`
- Modify: `08-infrastructure/deployment/duckdns-update.sh`
- Modify: `notes/production-env-duckdns-digitalocean-vercel.md`
- Create: `07-scripts/build_release.py`

**Interfaces:**

- Vercel serves the frontend.
- Host Nginx terminates HTTPS/WSS.
- API binds to `127.0.0.1:8000` on the Droplet.
- Qdrant stays on the private Compose network with persistent storage.

- [ ] **Step 1: Test builds and configuration**

```powershell
docker build -f 08-infrastructure/docker/Dockerfile.api .
docker compose -f 08-infrastructure/compose/docker-compose.prod.yml config
```

- [ ] **Step 2: Fix Nginx-to-API reachability**

Publish API as `127.0.0.1:8000:8000` for host Nginx. Do not publish Qdrant
port 6333.

- [ ] **Step 3: Add health, persistence, and rollback checks**

Deployment fails on unhealthy readiness; the prior release and Qdrant snapshot
remain recoverable.

- [ ] **Step 4: Build and upload source-only releases**

Create a deterministic release archive and SHA-256 manifest without `.env`,
checkpoints, datasets, indexes, weights, caches, or generated results. Upload
the backend archive directly to DigitalOcean and deploy the frontend with
Vercel CLI; do not use a GitHub integration.

- [ ] **Step 5: Configure public endpoints**

Provision Reserved IP, DuckDNS, Nginx, Certbot, exact Vercel origin, HTTPS/WSS,
and certificate renewal.

- [ ] **Step 6: Run external smoke tests**

Verify health, readiness, HTTP, WSS audio, restart persistence, private Qdrant,
and the Vercel flow from outside the Droplet.

---

### Task 10: Final security and release audit

**Files:**

- Modify: `README.md`
- Modify: `09-docs/architecture/architecture.md`
- Modify: `09-docs/api/api.md`
- Modify: `.claude/worktrees/utkarsh-rag-tasklist/notes/CURRENT-TASKS.md`

**Interfaces:**

- Produces: a reproducible release candidate and evidence-backed submission.

- [ ] **Step 1: Scan working tree and history**

Find credentials, debug values, accidental datasets, weights, indexes, and
caches. Rotate any exposed credential.

- [ ] **Step 2: Run the complete local matrix**

```powershell
python 07-scripts/validate_contracts.py
python -m unittest discover -s 03-ai-rag-engine/tests -v
python -m unittest discover -s 01-backend-api/tests -v
python -m unittest discover -s 04-external-services/tests -v
python -m compileall -q 01-backend-api 03-ai-rag-engine 04-external-services 06-evaluation 07-scripts
Set-Location 02-frontend
npm ci
npm run test
npm run typecheck
npm run build
```

- [ ] **Step 3: Run deployment verification**

Build images, validate Compose/Nginx, deploy, check readiness, exercise HTTPS and
WSS, restart, and prove Qdrant persistence.

- [ ] **Step 4: Run eleven-locale live demonstrations**

For every locale, capture audio, obtain one final transcript, retrieve evidence,
generate in the same language, display grounding/sources, and record failures.

- [ ] **Step 5: Freeze submission evidence**

Record release archive SHA-256, source-manifest hash, URLs, configuration
versions, corpus/index manifest,
P50/P70/P100, quality metrics, known limitations, and rollback procedure. Mark
complete only when every required check has direct evidence.

---

## Execution Order

```text
Experimental baseline and checkpoint
  -> Contracts and configuration
  -> Dataset and index decisions
  -> RAG providers
  -> FastAPI, STT, and WebSocket
  -> Frontend
  -> Evaluation
  -> Deployment
  -> Security and release audit
```

Parallel implementation begins only after Task 1 produces a checkpointed green
baseline. Create another checkpoint before and after every later task. Dataset
benchmarking can then overlap with fixture backend/frontend work, but production
provider wiring must consume the benchmark-selected model and collection
configuration.
