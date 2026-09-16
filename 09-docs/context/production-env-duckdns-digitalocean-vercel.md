# Production Environment Setup

This is the environment-variable guide for the planned deployment:

```text
Frontend       Vercel
Backend/RAG    DigitalOcean Droplet
Reverse proxy  Nginx
TLS            Let's Encrypt via Certbot
Hostname       DuckDNS subdomain
Vector DB      Qdrant, private Docker service on the Droplet
```

> **Current status:** this is a preparation guide for the finished application. The repository is still incomplete, so this document does not claim that the current build is production-ready. Do not create production secrets or run the final deploy until the deployment gates near the end of this file are cleared.

> **Scope of this task:** only this guide is being prepared. No backend, frontend, RAG, or infrastructure code is changed by following this documentation review.

The frontend must call an HTTPS API and a WSS WebSocket. A browser page served by Vercel over HTTPS cannot reliably call `http://DROPLET_IP` or `ws://DROPLET_IP`.

The names below match the current backend settings and deployment scripts. The repository `.env.example` files are templates only; do not commit real values to this repository. Use this guide as the source of truth for `DUCKDNS_DOMAIN`: the update script requires the short label, such as `echoquery-api`, not the full `.duckdns.org` hostname.

## Replacement Map

These are the values that must eventually be replaced with real deployment values. Everything beginning with `REPLACE_` or `VERIFY_` is intentionally unresolved.

| Variable | Where it belongs | Replace it with | Where to get it |
| --- | --- | --- | --- |
| `DROPLET_RESERVED_IP` | Droplet operator environment | DigitalOcean Reserved IPv4 address | DigitalOcean Control Panel -> Networking -> Reserved IPs. Attach it to the Droplet first. |
| `DUCKDNS_DOMAIN` | Droplet operator environment | Short label, for example `echoquery-api` | The subdomain you create at DuckDNS. Do not include `.duckdns.org`. |
| `DUCKDNS_TOKEN` | Droplet operator environment, secret | DuckDNS account token | The token shown after signing in at DuckDNS. |
| `API_HOSTNAME` | Droplet operator environment | Full hostname, for example `echoquery-api.duckdns.org` | Combine the DuckDNS label with `.duckdns.org`. |
| `LETSENCRYPT_EMAIL` | Droplet operator environment | A real monitored email address | Your own email; Let's Encrypt uses it for certificate notices. |
| `VERCEL_ORIGIN` | Used to derive backend allowlists | Exact production URL, for example `https://echoquery.vercel.app` | Vercel project -> Deployments -> production deployment. Copy the URL without a trailing slash. |
| `SARVAM_API_KEY` | Backend API environment, secret | Real Sarvam API key | Sarvam developer dashboard/API-key page. |
| `SARVAM_LLM_MODEL` | Backend API environment | Exact supported model ID | Sarvam's current model documentation or dashboard; do not guess it. |
| `EMBEDDING_MODEL` | Backend and indexer environments | Benchmark-selected multilingual embedding model | The project's multilingual quality/latency benchmark. This is not decided safely yet. |
| `EMBEDDING_DIMENSION` | Backend and indexer environments | Output dimension of the selected embedding model | The selected model's documentation/configuration. Rebuild Qdrant whenever this changes. |
| `RERANKER_MODEL` | Backend and indexer environments | Benchmark-selected reranker, or an empty value | The project's retrieval quality/latency benchmark. Leave empty if it cannot fit the latency budget. |

The public Vercel variables are derived rather than independently purchased or generated:

```text
VITE_API_BASE_URL=https://API_HOSTNAME
VITE_WS_URL=wss://API_HOSTNAME/ws
```

## 1. Values To Obtain First

### DigitalOcean

1. Create the Droplet in the region closest to the users and the model provider. Bangalore is preferred when available.
2. Reserve a DigitalOcean Reserved IP and attach it to the Droplet. Use the Reserved IP, not the temporary Droplet IP, for DNS.
3. Record:

```text
DROPLET_RESERVED_IP=your IPv4 address from DigitalOcean
```

4. In the DigitalOcean firewall, allow only TCP `22`, `80`, and `443`. Restrict SSH (`22`) to your own public IP when possible. Do not expose Qdrant `6333`.

### DuckDNS

1. Sign in at [DuckDNS](https://www.duckdns.org/).
2. Create a subdomain, for example `echoquery-api`.
3. Set its IPv4 address to `DROPLET_RESERVED_IP`.
4. Copy the DuckDNS token from the DuckDNS account page. It is a secret and must remain on the server.

Use these values. `API_HOSTNAME` is the public DNS name; `DUCKDNS_DOMAIN` is the short DuckDNS label used by `08-infrastructure/deployment/duckdns-update.sh` and must not include `.duckdns.org`:

```text
DUCKDNS_DOMAIN=echoquery-api
DUCKDNS_TOKEN=replace_with_the_token_from_duckdns
API_HOSTNAME=echoquery-api.duckdns.org
DROPLET_RESERVED_IP=your IPv4 address from DigitalOcean
```

Check DNS from your computer before requesting a certificate:

```powershell
Resolve-DnsName echoquery-api.duckdns.org -Type A
```

The returned address must equal the Reserved IP. If the address changes later, update DuckDNS before renewing TLS:

```bash
curl "https://www.duckdns.org/update?domains=echoquery-api&token=DUCKDNS_TOKEN&ip=DROPLET_RESERVED_IP"
```

Create a server-only operator file for the DuckDNS and certificate scripts:

```bash
sudo install -d -m 700 /etc/echoquery
sudo touch /etc/echoquery/deployment.env
sudo chown root:root /etc/echoquery/deployment.env
sudo chmod 600 /etc/echoquery/deployment.env
sudo nano /etc/echoquery/deployment.env
```

Contents:

```dotenv
API_HOSTNAME=echoquery-api.duckdns.org
LETSENCRYPT_EMAIL=REPLACE_WITH_REAL_EMAIL
DUCKDNS_DOMAIN=echoquery-api
DUCKDNS_TOKEN=REPLACE_WITH_DUCKDNS_TOKEN
DROPLET_RESERVED_IP=REPLACE_WITH_DIGITALOCEAN_RESERVED_IP
```

The deployment scripts read these values from their **process environment**; they do not automatically load this file. When the project is ready, load it explicitly:

```bash
sudo bash -c 'set -a; . /etc/echoquery/deployment.env; set +a; bash /opt/echoquery/08-infrastructure/deployment/duckdns-update.sh'
```

### Vercel

After the frontend is deployed, copy its exact production origin, for example:

```text
VERCEL_ORIGIN=https://echoquery.vercel.app
```

Use the exact origin with no trailing slash. Preview deployments have different origins; add them to the allowlist only when you intentionally want previews to call production.

### Sarvam

Create/copy the API key from the Sarvam developer dashboard. This key belongs only in the DigitalOcean backend environment. Never put it in a Vercel `VITE_*` variable.

```text
SARVAM_API_KEY=replace_with_the_real_sarvam_key
SARVAM_LLM_BASE_URL=https://api.sarvam.ai
SARVAM_LLM_MODEL=VERIFY_CURRENT_MODEL_ID_IN_SARVAM_DASHBOARD
```

The model ID must be copied from Sarvam's current documentation/account. Do not guess it.

## 2. DigitalOcean Backend Environment

Create this file on the Droplet only:

```bash
sudo install -d -m 700 /etc/echoquery
sudo touch /etc/echoquery/api.env
sudo chown root:root /etc/echoquery/api.env
sudo chmod 600 /etc/echoquery/api.env
sudo nano /etc/echoquery/api.env
```

Put the following in `/etc/echoquery/api.env`, replacing every value marked `REPLACE_` or `VERIFY_`:

```dotenv
# Runtime
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_FORMAT=json

# Public browser endpoints. These must match the Nginx certificate hostname.
PUBLIC_API_ORIGIN=https://echoquery-api.duckdns.org
PUBLIC_WS_ORIGIN=wss://echoquery-api.duckdns.org/ws

# Browser security. Use the exact Vercel origin, without a trailing slash.
CORS_ALLOWED_ORIGINS=https://echoquery.vercel.app
WS_ALLOWED_ORIGINS=https://echoquery.vercel.app

# Supported locale contract
SUPPORTED_LOCALES=en-IN,hi-IN,bn-IN,ta-IN,te-IN,kn-IN,ml-IN,mr-IN,gu-IN,pa-IN,od-IN

# Retrieval and latency controls
RAG_TOP_K=5
RAG_FETCH_K=20
RAG_TOTAL_DEADLINE_MS=200
MAX_QUERY_CHARS=2000

# Qdrant is private inside the Docker Compose network. Do not use the public IP.
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=echoquery_chunks_v1
QDRANT_DISTANCE=cosine

# These are selected only after the real multilingual benchmark.
EMBEDDING_MODEL=VERIFY_BENCHMARK_SELECTED_MODEL
EMBEDDING_DIMENSION=VERIFY_BENCHMARK_SELECTED_DIMENSION
RERANKER_MODEL=VERIFY_BENCHMARK_SELECTED_RERANKER_OR_EMPTY

# Sarvam generation
SARVAM_API_KEY=REPLACE_WITH_SARVAM_API_KEY
SARVAM_LLM_BASE_URL=https://api.sarvam.ai
SARVAM_LLM_MODEL=VERIFY_CURRENT_MODEL_ID_IN_SARVAM_DASHBOARD
SARVAM_LLM_TIMEOUT_MS=150
SARVAM_LLM_MAX_RETRIES=0

# Guardrails
GROUNDING_ENABLED=true
GROUNDING_TIMEOUT_MS=25

# The current Settings class does not consume METRICS_ENABLED or PROMETHEUS_ENABLED.
# Do not add those flags expecting them to enable an exporter.
```

`INDEX_SNAPSHOT` is not a secret and is not something you currently need to obtain. The production Compose file injects `INDEX_SNAPSHOT=/app/data/indexes/index.json` directly into the API container. Do not duplicate it in `/etc/echoquery/api.env` unless the container's mounted index path is intentionally changed.

### What each backend value comes from

| Variable | Replace with | How to get it |
| --- | --- | --- |
| `PUBLIC_API_ORIGIN` | `https://API_HOSTNAME` | Build from the DuckDNS hostname after DNS resolves. |
| `PUBLIC_WS_ORIGIN` | `wss://API_HOSTNAME/ws` | Same hostname; use `wss`, not `ws`. |
| `CORS_ALLOWED_ORIGINS` | Vercel production URL | Copy from the Vercel deployment URL. |
| `WS_ALLOWED_ORIGINS` | Vercel production URL | Usually the same value as CORS. |
| `SARVAM_API_KEY` | Secret API key | Sarvam dashboard; keep server-only. |
| `SARVAM_LLM_MODEL` | Current supported model ID | Sarvam model documentation/dashboard. |
| `EMBEDDING_MODEL` | Benchmark winner | Choose only after the multilingual retrieval benchmark. |
| `EMBEDDING_DIMENSION` | Dimension of that winner | Read from the selected embedding model; it must match Qdrant. |
| `RERANKER_MODEL` | Benchmark decision or empty | Keep only if its quality gain fits the latency budget. |
| `QDRANT_COLLECTION` | Versioned index name | Change when vector dimension/model changes, then rebuild the index. |

These values can remain as shown because they are deployment choices rather than secrets: `APP_ENV`, `APP_HOST`, `APP_PORT`, locale list, `RAG_TOP_K`, `RAG_FETCH_K`, timeout controls, logging flags, and the internal Qdrant URL. `METRICS_ENABLED` and `PROMETHEUS_ENABLED` are not current runtime settings; observability is currently emitted through structured logs and latency fields.

Do not claim the 200 ms target from these settings. The full path still needs a real benchmark over a reasonable query set covering preprocessing/chunking where applicable, embedding, Qdrant, reranking, generation, grounding, and final serialization. The required report is P50/P70/P100; P95 may be included as an additional percentile.

## 3. Indexer Environment (Optional)

The current ingestion and index-build scripts take paths and model settings as command-line arguments, not from an automatic `.env` loader. If you keep an operator environment file for repeatable runs, keep it separate from the API file so it cannot accidentally expose index credentials through the API container:

```bash
sudo touch /etc/echoquery/indexer.env
sudo chown root:root /etc/echoquery/indexer.env
sudo chmod 600 /etc/echoquery/indexer.env
sudo nano /etc/echoquery/indexer.env
```

Suggested values:

```dotenv
APP_ENV=production
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=echoquery_chunks_v1
EMBEDDING_MODEL=VERIFY_BENCHMARK_SELECTED_MODEL
EMBEDDING_DIMENSION=VERIFY_BENCHMARK_SELECTED_DIMENSION
DATA_RAW_DIR=/app/data/raw
DATA_PROCESSED_DIR=/app/data/processed
DATA_CHUNKS_DIR=/app/data/chunks
DATA_INDEX_DIR=/app/data/indexes
```

The corpus, selected model artifacts, and index must be installed on the Droplet through the controlled deployment/indexing process. Do not place the raw dataset or generated index in Git. Before using a real embedding model, replace both `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` after the multilingual benchmark and rebuild the versioned Qdrant collection.

`http://qdrant:6333` resolves only inside the Docker Compose network. It will not resolve from the Droplet's normal host shell, and the current production Compose file does not yet define an indexer service. Treat this indexer file as a future operator template until that execution path is implemented; never solve this by exposing Qdrant publicly on `0.0.0.0:6333`.

## 4. Nginx and Certbot Values

Nginx needs the same hostname used by `PUBLIC_API_ORIGIN`. Certbot needs an email for renewal notices. A bare DigitalOcean IP cannot receive a normal Let's Encrypt hostname certificate, so issue the certificate for the DuckDNS name:

```text
API_HOSTNAME=echoquery-api.duckdns.org
LETSENCRYPT_EMAIL=your-real-email@example.com
```

Install the certificate after:

1. DuckDNS A record resolves to the Reserved IP.
2. Nginx is listening on port `80`.
3. The DigitalOcean firewall allows port `80`.

On the Droplet:

```bash
sudo certbot --nginx \
  --domain echoquery-api.duckdns.org \
  --email your-real-email@example.com \
  --agree-tos \
  --no-eff-email \
  --redirect

sudo certbot renew --dry-run
```

Keep port `80` open for the HTTP-01 renewal challenge. Certbot manages the certificate under `/etc/letsencrypt/live/echoquery-api.duckdns.org/`.

When the application and deployment files are ready, the repository deploy script must also receive the operator values in its process environment:

```bash
sudo bash -c 'set -a; . /etc/echoquery/deployment.env; set +a; ENV_FILE=/etc/echoquery/api.env bash /opt/echoquery/08-infrastructure/deployment/deploy.sh /opt/echoquery'
```

Do not run that command against the current incomplete repository until the host-Nginx connectivity gate below is fixed.

## 5. Vercel Environment Variables

Set these in the Vercel project for the Production environment. They are public browser configuration, not secrets:

```dotenv
VITE_API_BASE_URL=https://echoquery-api.duckdns.org
VITE_WS_URL=wss://echoquery-api.duckdns.org/ws
VITE_APP_ENV=production
```

Never set any of these in Vercel frontend variables:

```text
SARVAM_API_KEY
DUCKDNS_TOKEN
QDRANT_URL
QDRANT_API_KEY
SSH_PRIVATE_KEY
EMBEDDING_MODEL credentials
```

If the frontend uses a different build prefix (for example `NEXT_PUBLIC_` instead of `VITE_`), keep the same public values but follow the frontend framework's required prefix. The backend still owns all provider and vector-database secrets.

This repository currently uses Vite, so `VITE_` is the correct prefix. Set the variables in Vercel under **Project Settings -> Environment Variables**, scope them to **Production**, and redeploy after changing them. These variables are visible in the browser bundle and therefore must never contain secrets.

## 6. Current Repository Deployment Gates

Clear these before treating the environment setup as deployable:

- [ ] Select the real multilingual embedding model, its dimension, and the reranker decision through project-specific benchmarks.
- [ ] Complete and verify the production Sarvam, Qdrant, STT, RAG, guardrail, and frontend microphone/WebSocket integrations.
- [ ] Fix API reachability between host Nginx and Docker. The current Nginx upstream is `127.0.0.1:8000`, while the production Compose file only uses `expose: 8000`; `expose` does not publish the container port to the host. A later code change must either bind `127.0.0.1:8000:8000` or place Nginx on the same Docker network and proxy by service name.
- [ ] Verify the frontend production build and dependency lockfile before enabling Vercel deployment.
- [ ] Run a real end-to-end production benchmark and demonstrate full RAG P100 strictly below `200 ms`; setting `RAG_TOTAL_DEADLINE_MS=200` alone is not evidence.
- [ ] Confirm the production health endpoint checks actual dependencies rather than only returning a process-level success response.

## 7. Final Preflight Checklist

- [ ] Reserved IP is attached to the Droplet.
- [ ] DuckDNS A record resolves to that Reserved IP.
- [ ] `/etc/echoquery/api.env`, `/etc/echoquery/deployment.env`, and optional `indexer.env` are mode `600` and not in Git.
- [ ] Nginx uses `API_HOSTNAME` and proxies `/api/`, `/health`, and `/ws` to the API container.
- [ ] Qdrant has no public `6333` port mapping.
- [ ] Certbot issues and renews the certificate successfully.
- [ ] Vercel variables use `https://` and `wss://`.
- [ ] Backend CORS and WebSocket allowlists contain the exact Vercel origin.
- [ ] `https://echoquery-api.duckdns.org/health` succeeds from an external network.
- [ ] A WebSocket connection succeeds from the deployed Vercel frontend.
- [ ] Production P50/P70/P100 latency is measured across a reasonable test set before calling the strict P100-under-200-ms requirement satisfied.
