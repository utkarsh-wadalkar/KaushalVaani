# EchoQuery Implementation Evidence Ledger (Historical Snapshot)

> **Superseded by the 2026-09-05 audit.** Do not use the completion claims below
> as current repository evidence. See `CURRENT-TASKS.md` for the verified
> checklist and `plan.md` for the recovery-first implementation plan.

The content below is retained only as historical context. It must not override
`CURRENT-TASKS.md` or `plan.md`.

## Current milestone

**Phase 1 implementation has started after Phase 0 reconciliation.** The earlier documents described a RAG-only assignment and overstated production readiness. They now track the whole application and the selected deployment: Vercel frontend; DigitalOcean backend/RAG; Nginx; Certbot; DuckDNS; private self-hosted Qdrant.

## Verified locally

- [x] Contract v1.1 examples: five valid documents accepted and five invalid documents rejected.
- [x] RAG/core unit suite: 88 tests pass; two `pyarrow`-dependent ingestion tests are skipped in the current interpreter.
- [x] Python compilation succeeds for backend, RAG, external-service, evaluation, and script source roots.
- [x] Ingestion supports streaming parquet validation, deterministic IDs, Unicode NFC, metadata preservation, deterministic JSONL, and exact-duplicate reporting in fixture tests.
- [x] Fixed-size, sentence-aware, and semantic chunk candidates share one metadata-preserving offline interface.
- [x] Fixture embedding, atomic/resumable local snapshots, deterministic Qdrant point IDs, retrieval, optional reranking, and retrieval quality metrics are implemented.
- [x] Query/Answer models, same-language/context-only prompt, fixture generation, relevance guard, unsafe-input guard, grounding result, and typed pipeline errors are implemented.
- [x] Fixture evaluation reports Recall@k, MRR@k, nDCG@k, grounding precision/recall/F1, P50/P70/P95/P100, and cold-start versus steady-state results.
- [x] FastAPI, WebSocket, frontend, Compose, Nginx, Certbot, DuckDNS, and Vercel configuration scaffolds exist.
- [x] Production environment guide exists at `notes/production-env-duckdns-digitalocean-vercel.md`.

## In progress: code exists but is not complete

- [~] Runtime pipeline selection: production currently still constructs a hashing embedder, local snapshot/in-memory store, and FixtureLLM instead of configured Qdrant/embedding/Sarvam providers.
- [~] RAG deadline: `RAG_TOTAL_DEADLINE_MS` is configured but is not enforced through final serialization.
- [~] Latency boundary: pipeline `total_ms` is calculated before backend serialization; context construction and serialization are not separately attributed.
- [~] FastAPI integration: routes exist, but logging/error middleware is not registered, readiness is not dependency-aware, and backend integration tests are absent.
- [~] Sarvam STT: provider files are empty; WebSocket runtime hard-codes FixtureSTT.
- [~] WebSocket: transcript data currently includes fields forbidden by the server event schema, RAG stages are discarded, and audio/session limits and timeout behavior are incomplete.
- [~] Frontend: text querying works at scaffold level, but the microphone button does not request/capture/send audio, no `audio_end` is sent, and transcript/answer WebSocket events are ignored.
- [~] Latency analytics: fixture percentile helpers exist, but there is no live aggregation/dashboard and no unified STT/RAG/E2E benchmark command.
- [~] Docker/deployment: private Qdrant scaffolding exists, but production host Nginx proxies to `127.0.0.1:8000` while Compose only `expose`s API port 8000, so the current deployment path is unreachable.
- [~] Frontend build reproducibility: no `package-lock.json` exists while `Dockerfile.web` uses `npm ci`; `vite-env.d.ts` and verified production build evidence are missing.
- [~] Environment template: `DUCKDNS_DOMAIN` must be the short DuckDNS label, and unused metrics flags must not imply an exporter exists.

## Pending evidence-driven decisions

- [?] ADR 0002: multilingual embedding model, dimension, and distance metric.
- [?] ADR 0003: production chunking strategy selected from real-corpus quality and latency.
- [?] ADR 0004: keep/drop production reranker based on per-locale gain and hot-path latency.
- [?] ADR 0005: Qdrant collection layout and payload/filter strategy.
- [?] Calibrated relevance/off-topic threshold and acceptable worst-locale retrieval floor.

## External or credential-owned gates

- [!] Review MSMARCO-XI license/access, download the real corpus, characterize all eleven locales, and create the held-out evaluation split.
- [!] Supply the benchmark-selected embedding/reranker models or approve their measured selection.
- [!] Supply Sarvam API credentials and current STT/105B model identifiers; run live eleven-locale checks.
- [!] Provision a DigitalOcean Droplet and Reserved IP.
- [!] Create/update the DuckDNS record and supply its token.
- [!] Issue and dry-run renew the Let's Encrypt certificate with Certbot.
- [!] Deploy the Vercel frontend and provide its exact production origin.
- [!] Install the production Qdrant collection/index artifacts without copying the raw corpus to the server.
- [!] Run external HTTPS/WSS and production latency/quality tests.

## Phase status

| Phase | Status | Next proof required |
| --- | --- | --- |
| 0. Reconciliation | Completed locally | 88 tests pass with two expected skips; contracts and compilation pass; all three documents are synchronized. |
| 1. Dataset/offline artifacts | Partially verified | Real corpus, provenance, held-out split, real multilingual chunk benchmark. |
| 2. Embeddings/retrieval | Partially verified | Production provider factory, live Qdrant, multilingual ADR evidence. |
| 3. Generation/guardrails/orchestration | Partially verified | Sarvam HTTP client, full deadline/serialization timing, locale/provider tests. |
| 4. FastAPI | Scaffold only | Fixture integration tests, lifecycle, middleware, readiness. |
| 5. STT | Fixture only | Sarvam adapter tests and live provider evidence. |
| 6. WebSocket | Contract shell | Validated audio-to-answer fixture integration test. |
| 7. Frontend | Visual/text scaffold | Real microphone/audio flow, event rendering, build verification. |
| 8. Deployment | Scaffold only | Corrected Compose/Nginx connectivity, image/Compose validation, live deploy. |
| 9. Evaluation | Fixture harness | Unified STT/RAG/E2E and stage report over realistic multilingual queries. |
| 10. Security/E2E | Pending | Secret scan, limits/timeouts/persistence checks, full fixture and live demo. |

## Latency truth

- The `<200 ms` requirement applies only to complete RAG wall-clock time, from RAG request entry through final serialization.
- STT latency is separate; end-to-end is audio through final answer.
- Required percentiles are P50/P70/P95/P100 for STT, RAG, and E2E, plus internal RAG stages.
- Existing sub-millisecond fixture results are useful regression data only. They are not production evidence and do not satisfy the SLO.

## Deployment truth

- Frontend: Vercel.
- Backend/RAG: DigitalOcean Droplet.
- Public backend hostname: DuckDNS label mapped to a DigitalOcean Reserved IP.
- Edge server: host Nginx with HTTPS/WSS certificates from Certbot/Let's Encrypt.
- Vector database: Qdrant on a private Docker network with persistent storage; port 6333 is not public.
- Production receives selected index artifacts, not the raw MSMARCO-XI dataset.

## Next execution task

Implement Task 1 from the execution plan: failing tests and fixes for the full RAG deadline, final serialization timing, and stage observability. After verification, update all three documents with the exact test output and remaining gates.
