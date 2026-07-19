# GenUI Deployment

GenUI ships on-prem: **one full deployment per customer**, on the customer's VM, with the customer's LLM key. This is not a plain "docker up" for three reasons, and each one shapes what is in this folder:

1. **Volume.** Target portals serve ~10^5 users/day: the backend runs multiple worker processes, and everything that must be consistent across processes (profiles, rate limits, LLM budget, the single-flight render lock) lives in Redis. Redis is a hard dependency here, not a cache.
2. **Multi-tenant _inside_ the deployment.** A tenant is the customer's access architecture: insurance (`agente` vs `assicurato`), enterprise (`dipendente` vs `cliente`). Tenants share the process but never the data: [TENANT-ISOLATION.md](TENANT-ISOLATION.md) is the written guarantee.
3. **BYOK.** The engine (LLM + embeddings) is the customer's own and is selected entirely via env; see the matrix below. The deployment must protect that key from public traffic (budget, rate limits, admin-only live renders).

If the deployment is the product, the deployment must be reproducible and its
guarantees written. That is all this folder is.

## Bring-up

```bash
cd deploy
cp customer.env.example customer.env   # edit: engine key, tenants, budget, CORS
docker compose up -d --build
./smoke.sh                             # liveness, health, fail-closed, per-tenant scoping
```

What comes up:

| Service   | Image                  | Exposed       | State                       |
| --------- | ---------------------- | ------------- | --------------------------- |
| `backend` | built from `backend/`  | `:8000`       | stateless (all state below) |
| `redis`   | `redis:7-alpine` (AOF) | internal only | volume `redis_data`         |
| `qdrant`  | `qdrant/qdrant` pinned | internal only | volume `qdrant_storage`     |

Redis and Qdrant are **not** published on the host: the backend is the single entry point. Terminate TLS in front of `:8000` with the proxy you already run (nginx/traefik/caddy); the compose deliberately does not ship one.

Per-customer parametrization is exactly one file: `customer.env`. A new customer deployment = this folder + their `customer.env` on their VM. Nothing else varies.

## Declaring tenants

A tenant is **declared by appearing in three env vars**, there is no separate registry to administer:

```bash
CLIENT_API_KEYS=pk_A:agente,pk_B:assicurato    # browser keys → tenant identity
ADMIN_API_KEYS=sk_A:agente,sk_B:assicurato     # server-to-server keys, per tenant
USER_TOKEN_SECRETS=s1:agente,s2:assicurato     # HMAC secrets for signed user identity
```

The tenant of every request is resolved **server-side from the presented key**, never from the request body. From that single fact, each tenant automatically gets its own:

| Per tenant               | How it attaches                                                                 |
| ------------------------ | ------------------------------------------------------------------------------- |
| Knowledge base (RAG)     | documents uploaded with tenant A's admin key are stamped and filtered to A      |
| User profiles + identity | stored under the tenant, guarded by that tenant's `USER_TOKEN_SECRETS` entry    |
| Render cache             | cache keys are namespaced by tenant (+ zone config + segment)                   |
| Zone config (registry)   | governed config is keyed `(tenant, zone_id)` (see README §Zone Config Registry) |
| Metrics, audit, uplift   | every counter and audit record carries the tenant                               |
| LLM budget + rate limits | `LLM_BUDGET_PER_HOUR` is counted per tenant; rate limits per key                |

**Adding a tenant** = add its entries to the three vars, then `docker compose up -d` (recreates the backend; keys are read at process start). Give the new tenant's `sk_` key to whoever ingests its documents, the `pk_` key to its frontend, and its user-token secret to the host backend that signs logins.

**Per tenant vs per deployment.** The LLM engine and its key are **per-deployment** (the operator's BYOK, D5): tenants inside a deployment share the engine, and the per-tenant budget separates their spend. If two audiences must not even share an engine key or a failure domain, run two deployments. This folder makes that cheap by design.

What the boundary guarantees, with the code that enforces it: **[TENANT-ISOLATION.md](TENANT-ISOLATION.md)**.

## Engine BYOK matrix

Selected entirely in `customer.env`. Misconfiguration fails loudly at startup or on `/ready`, never a silent fallback to another provider.

### LLM engine

| Engine                                                        | Config                                                                      | Notes                                                                                                                              |
| ------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| OpenAI                                                        | `LLM_PROVIDER=openai` + `OPENAI_API_KEY`                                    | default                                                                                                                            |
| Azure OpenAI / vLLM / Ollama / RunPod / any OpenAI-compatible | `LLM_PROVIDER=openai` + `OPENAI_BASE_URL` (+ key if the endpoint wants one) | fully local engines stay local                                                                                                     |
| Anthropic                                                     | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`                              | add `anthropic` to the image (see `backend/Dockerfile`); `/query`'s RAG tool degrades to pre-fetched context (documented fallback) |
| Google Gemini                                                 | `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY`                                    | via Gemini's OpenAI-compatible API, no extra package                                                                               |

Models: `RESPONSE_MODEL`, `PROFILE_MODEL`.

### Embeddings (independent of the LLM choice)

| Engine                                      | Config                                                 | Notes                                                                                            |
| ------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| OpenAI                                      | `EMBEDDING_MODEL` (default `text-embedding-3-small`)   | key inherits `OPENAI_API_KEY`                                                                    |
| vLLM / Ollama / TEI / any OpenAI-compatible | `EMBEDDING_BASE_URL` (+ `EMBEDDING_API_KEY` if needed) | inherits `OPENAI_BASE_URL`: an all-local deployment keeps documents local with zero extra config |
| Google Gemini                               | `EMBEDDING_PROVIDER=gemini`                            | key inherits `GOOGLE_API_KEY`                                                                    |

Vector size follows the model (`EMBEDDING_DIMENSIONS` to override, e.g. unknown self-hosted models). Changing embedding model over an existing index fails with instructions, it never corrupts the collection. Unknown provider = startup error by design: a typo must not send the customer's documents to a third party.

### Document extraction (uploads)

| Backend                 | Config                                         | Notes                                        |
| ----------------------- | ---------------------------------------------- | -------------------------------------------- |
| `local` (default)       | nothing                                        | pypdf/docx/bs4, data never leaves            |
| `docling`               | `EXTRACTOR_BACKEND=docling` + package in image | better tables/layout, still local            |
| `glmocr` self-hosted    | `EXTRACTOR_BACKEND=glmocr` + `GLMOCR_BASE_URL` | scans/images, data stays in-house            |
| `glmocr` via Z.ai cloud | `GLMOCR_API_KEY`                               | documents LEAVE the infra, opt-in knowingly  |

## Operating notes

- **Sizing.** `WORKERS=4` handles ~10^5 users/day comfortably in front of the segment cache (most requests are cache hits; LLM generations are per-segment, not per-user). Scale `WORKERS` with CPU count; Redis and Qdrant sizes are driven by profiles and KB size, not by traffic.
- **Warmup is recommended ops** after deploy or zone-config changes: `POST /api/v1/zone/warmup` with the tenant's admin key pre-generates popular segments so first visitors hit the cache.
- **Health**: `GET /health` (public, degraded/healthy + redis/llm status), `/live`, `/ready`. **Metrics**: `GET /metrics` (Prometheus text, admin key; see main README §Observability for the scrape config and PromQL).
- **Audit** goes to the `genui.audit` logger by default → `docker compose logs` → ship with the log pipeline the VM already has. Per-tenant, append-only, "what was shown to whom".
- **Backup** = the two volumes (`redis_data`, `qdrant_storage`) plus `customer.env`. The backend container is disposable.
- **Upgrade** = `git pull && docker compose up -d --build` (config and data live outside the image). Roll back by checking out the previous tag and rebuilding. **Exception, the Qdrant image**: its storage format only supports stepping ONE minor version at a time on an existing volume (v1.12 → v1.18 directly = crash loop at boot). Step through minors, or re-index the KB into a fresh volume.
- **Kubernetes**: not needed for the one-VM-per-customer model this ships. When a customer really requires it, the container is already stateless behind `:8000`: a Deployment + two StatefulSets is a direct translation. Until then, compose on a VM is the supported, tested path.
