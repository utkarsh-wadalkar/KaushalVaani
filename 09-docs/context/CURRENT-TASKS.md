# EchoQuery Current Task Ledger

**Audit date:** 2026-09-05

**Readiness verdict:** **Not complete and not deployable.**

This file is the current evidence ledger. `plan.md` defines the execution
order. The older `AI-RAG-TASKS.md` and `Utkarsh-TASK.md` are retained as
historical snapshots. By user decision, all implementation remains inside the
ignored experimental workspace and is not committed or pushed to GitHub.

## Verified repository reality

- [x] The registered Git worktree is the repository root at
  `D:/ALL Programming/0-WebDev/Hacker_House/EchoQuery-RAG-based-STT`.
- [x] `.claude/worktrees/utkarsh-rag-tasklist` has no `.git` marker and is
  not listed by `git worktree list`.
- [x] Everything under `.claude/` is ignored by the retained `.gitignore`
  rule, so the nested implementation is not part of a commit or deployable
  checkout.
- [x] The tracked backend, RAG, STT, evaluation, and infrastructure source files
  are empty placeholders; the tracked frontend has no `package.json`.
- [x] The tracked root has no `pyproject.toml`.
- [x] The nested staging directory contains substantive RAG, evaluation, script,
  and infrastructure code, but no complete backend or frontend implementation.
- [x] The nested Sarvam adapter files are empty.
- [x] The tracked contracts contain no `00-contracts/examples/` fixtures.
- [x] A staged test run executed 93 tests: 90 passed, one contract test errored,
  and two ingestion tests skipped because `pyarrow` is not installed.
- [x] The contract error is a missing-file failure: the staged test assumes
  contracts exist inside the ignored staging directory.
- [x] `.env.example` and `.gitignore` have current uncommitted changes.

## Experimental workspace baseline

- [x] The user confirmed that the nested implementation is the experimental
  baseline and must not be committed or pushed.
- [ ] Create a local `.checkpoints/` directory inside the experimental workspace.
- [ ] Create a timestamped source archive and SHA-256 manifest before each phase.
- [ ] Record every checkpoint, test result, and restoration command in
  `notes/checkpoint-log.md`.
- [ ] Copy the canonical contracts and environment template into the experiment
  so its tests and local builds are self-contained.
- [ ] Repair test paths so they resolve the experimental contract copies.
- [ ] Reconcile `pyproject.toml` with actual imports and install dependencies.
- [ ] Run the complete experimental suite and record exact counts before feature
  work.

## Contract and architecture gates

- [ ] Repair the WebSocket server schema composition so
  `additionalProperties: false` does not reject base event fields.
- [ ] Add valid and invalid examples for every contract.
- [ ] Define `latency.total_ms` as finalized transcript/query entry through
  final serialized answer.
- [ ] Report STT and voice end-to-end latency separately without excluding them
  from the published analytics.
- [ ] Trigger RAG only once for a nonempty finalized Saaras v3 utterance.
- [ ] Preserve all eleven supported locales with no translation layer.
- [ ] Treat `grounded: false` as a successful low-evidence answer.

## Application implementation gates

- [ ] Implement production-configured multilingual embeddings.
- [ ] Implement Qdrant collection validation, indexing, and retrieval.
- [ ] Benchmark and decide whether production reranking remains enabled.
- [ ] Implement Sarvam-105B generation with timeout, bounded retry, response
  validation, and sanitized errors.
- [ ] Implement the Saaras v3 streaming adapter and final transcript
  normalization.
- [ ] Implement FastAPI lifecycle, dependencies, health, readiness, HTTP query,
  and WebSocket routes.
- [ ] Implement browser microphone capture, binary audio frames, `audio_end`,
  cancellation, transcript display, processing stages, grounded answers, and
  evidence display.
- [ ] Add backend, STT, WebSocket, and frontend integration tests.

## Dataset and evaluation gates

- [ ] Review MSMARCO-XI usage terms and record the exact dataset revision.
- [ ] Select a disk-conscious multilingual subset covering all eleven locales.
- [ ] Create a held-out evaluation split excluded from the Qdrant collection.
- [ ] Benchmark fixed, sentence-aware, and semantic chunking.
- [ ] Benchmark multilingual embedding candidates on retrieval quality and
  latency.
- [ ] Record chunking, embedding, collection-layout, and reranker decisions in
  ADRs.
- [ ] Measure P50, P70, and P100 for STT, complete RAG, and voice end-to-end.
- [ ] Demonstrate complete RAG P100 strictly below 200 ms or report the miss and
  bottleneck honestly.

## Deployment gates

- [ ] Add reproducible Python and frontend lockfiles.
- [ ] Make API and frontend production builds pass from clean installs.
- [ ] Build a source-only release archive with a SHA-256 manifest; exclude
  secrets, checkpoints, datasets, indexes, caches, and test output.
- [ ] Build and scan Docker images.
- [ ] Keep Qdrant private with persistent storage and readiness checks.
- [ ] Make host Nginx reach the API through a loopback-only published port.
- [ ] Validate Compose, Nginx, deployment, rollback, and backup procedures.
- [ ] Deploy the frontend with Vercel CLI and upload the backend release archive
  to DigitalOcean without using GitHub.
- [ ] Configure DuckDNS, HTTPS/WSS, Certbot renewal, exact CORS origins, and
  firewall rules.
- [ ] Run external health, readiness, HTTP, WebSocket, persistence, and
  multilingual smoke tests.

## Manual input required from the user

### Required before implementation takeover

- [x] Keep all work in the ignored experimental workspace with no commits or
  pushes unless the user later requests promotion.
- [ ] Confirm that local Docker Qdrant is acceptable for development. This is
  the default plan and requires no Qdrant Cloud account.
- [ ] State the available disk budget for MSMARCO-XI. The published dataset is
  large, so the first real benchmark will use a deterministic subset across all
  eleven locales rather than downloading everything blindly.

### Required before live provider verification

- [ ] Create a Sarvam account and place `SARVAM_API_KEY` in the local `.env`.
  Do not paste the key into chat or commit it.
- [ ] Confirm the account can call both Saaras v3 and `sarvam-105b`.

### Required only before public deployment

- [ ] Provide access to or create the DigitalOcean, Vercel, and DuckDNS
  resources described in
  `production-env-duckdns-digitalocean-vercel.md`.
- [ ] Supply the final hostname, Vercel origin, certificate email, and deployment
  region through private environment configuration.

## Definition of complete

EchoQuery is complete only when a source-only experimental release archive can
be restored into an empty directory, install, test, build, ingest the approved
multilingual corpus subset, build or restore Qdrant, start the production stack,
accept browser microphone audio, obtain one finalized Saaras v3 transcript,
return a grounded Sarvam-105B answer with sources, and reproduce the submitted
P50/P70/P100 measurements. Promotion to GitHub remains a separate explicit user
decision.
