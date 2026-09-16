# EchoQuery Evaluation Results

This file contains observed results only. Every number names the path and environment it measures.

## Offline Fixture End-To-End

Run date: 2026-08-24

Path measured:

```text
Query -> deterministic hashing embedder -> in-memory vector search
      -> fixture generation -> lexical grounding -> Answer serialization
```

The run used 100 identical English fixture queries, one indexed fixture chunk, `top_k=1`, `fetch_k=1`, and a local Python process. It did not use Sarvam, a live Qdrant server, a DigitalOcean Droplet, Nginx, or Vercel.

| Metric | Observed |
| --- | ---: |
| Queries | 100 |
| Errors | 0 |
| Grounded answers | 100 |
| P50 total RAG wall-clock | 0.142 ms |
| P70 total RAG wall-clock | 0.144 ms |
| P95 total RAG wall-clock | 0.155 ms |
| P100 total RAG wall-clock | 0.412 ms |

The report came from `06-evaluation/benchmarks/end_to_end.py` and is labeled `measured local benchmark; not production evidence`. These figures do not establish the production `<200 ms` requirement because provider network latency, model inference, live Qdrant, TLS, and DigitalOcean hardware are absent.

## Required Production Run

After deployment, run a reasonable multilingual query set through the public HTTPS API and record at least:

- steady-state P50/P70/P95/P100 for total RAG wall-clock through final serialized output;
- separate embedding, vector search, reranking, generation, grounding, and serialization attribution;
- cold-start measurements separately from warm steady-state measurements;
- monolingual and cross-lingual retrieval quality separately, with all eleven locales and Odia named explicitly;
- grounded-false rate per locale;
- concurrency level, Droplet size/region, model IDs/dimensions, Qdrant collection name, and benchmark revision.

The production pass/fail rule is `P100 total RAG wall-clock < 200 ms`. A fixture result, retrieval-only result, P95-only result, or generation-excluded result cannot be used as a pass claim.

## Deployment Contract

- Frontend: Vercel.
- Backend/RAG: DigitalOcean Droplet.
- Public backend hostname: DuckDNS subdomain pointing to a DigitalOcean Reserved IP.
- TLS and reverse proxy: Nginx with Certbot/Let's Encrypt.
- Browser URLs: `https://...` for HTTP and `wss://.../ws` for WebSocket.
- Qdrant: private Docker service; port `6333` is not publicly exposed.

The variable-by-variable setup is documented in [`notes/production-env-duckdns-digitalocean-vercel.md`](../../notes/production-env-duckdns-digitalocean-vercel.md).
