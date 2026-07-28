# GenUI Data Protection Statement

**Audience**: the data protection officer of an entity running a GenUI deployment. This document is written to be attached to a contract and to be usable as an input to a records-of-processing entry and a DPIA.

**This is engineering documentation, not legal advice.** It says what the code does, names the symbol that does it and the test that proves it, and says where it stops. It does not certify anything, and nothing here says a deployment is compliant. Every determination reserved to the controller stays with the controller: the lawful basis, the consent mechanism, the content of the DPIA, the retention numbers, the sub-processor contracts.

**Roles.** The customer running the deployment is the **controller**: they decide the purposes and the means, they own the site, and the personal data is collected from their visitors. The author of the framework is neither controller nor processor: no service is operated, no data is received, the software ships as source. The **LLM and embedding providers are the customer's own choice under BYOK**, so wherever this document mentions a processor or sub-processor, it is one the customer selected and contracts with directly.

**Scope**: one GenUI deployment (backend, Redis, Qdrant) and the React library embedded in the customer's site.

**As of**: 2026-07-27. References name the file and the symbol, never a line number: a line number is wrong as soon as anything above it moves, and a reader who follows a stale one lands on unrelated code. Re-verify any row with `grep -n "<symbol>" <file>`. `backend/tests/test_deploy_docs.py` fails when a named file or symbol disappears, and when a line number reappears.

## Processing activities (Art. 30 starting point)

Pre-filled for the standard deployment. The lawful basis column is the **plausible** one for the described configuration, and it is the controller's to choose and to justify: this table is a starting draft, not a determination.

| Processing | Data categories | Purpose | Plausible lawful basis | Retention | Where in the system |
| --- | --- | --- | --- | --- | --- |
| **Anonymous zone rendering** | No identifier. Page URL, host-supplied page metadata, the request itself. The segment collapses to `anon`. | Rendering a page band from a segment archetype | Art. 6(1)(f) legitimate interest, and arguably outside the material scope where no identifier exists at all. No terminal access occurs, so ePrivacy Art. 5(3) is not engaged. | Cached render, per segment, `ZONE_CACHE_STALE_TTL` (24 h) | `ANONYMOUS_SEGMENT`, `compute_segment` (`backend/segmentation/segmenter.py`); `_agent_request` (`backend/api/zone_router.py`) |
| **Identified zone personalization** | `user_id` (a pseudonymous identifier minted by the customer's own backend), profile: role, interests with confidence, user type; behaviour signals: scroll depth, clicks, page views | Personalising which content a known visitor is shown | Consent. Reading and writing the profile in IndexedDB is terminal access under ePrivacy Art. 5(3), and the CJEU has held that for tracking-driven personalisation consent is the correct basis rather than legitimate interest. | Profile: `PROFILE_TTL_SECONDS` (90 days from last write) | `ProfileStore` (`backend/profiles/store.py`); `consentGranted` (`frontend/src/utils/privacy.ts`) |
| **Behaviour capture** | Clicks, scroll depth, page views, dwell, and at the `balanced` level free-text snippets with common PII patterns redacted | Deriving the engagement and interest signals that feed the segment | Consent, same reasoning | Sent with the request, aggregated into the profile; not stored as a separate event log | `BehaviorTracker` (`frontend/src/utils/behaviorTracker.ts`); `redactPII`, `sanitizeText` (`frontend/src/utils/privacy.ts`) |
| **Chat (`/query`)** | The question text (free text, so potentially any category the visitor types, including special categories), the last 5 messages of conversation history, the profile when one applies | Answering the visitor | Controller's choice: consent, or contract where the chat is part of a service the visitor asked for. The question text itself is volunteered by the visitor. | Conversation history lives in the visitor's browser, and only with consent; nothing per-conversation is stored server-side | `_build_query_prompt` (`backend/agents/response_agent.py`) |
| **Audit trail** | `user_id`, tenant, zone, segment key, cache state, timestamps, the titles and links actually shown, what the guarantee chain removed, API key **fingerprint** (never the raw key) | Accountability: answering "why did this person see this content on this date" | Art. 6(1)(c) legal obligation or Art. 6(1)(f), depending on the sector. In regulated deployments this record is often required independently. | File sink: size-bounded rotation. Production sink: the host log pipeline's own retention policy. | `AuditLogger.log` (`backend/utils/audit.py`); `summarize_shown_components` (`backend/utils/audit.py`) |
| **Experiment metrics** | Counters per (tenant, zone, arm). `render_id` identifies a generated variant, not a person. No identifier is stored. | Measuring whether personalisation performs better than the control arm | Art. 6(1)(f), on aggregate data | Kept; aggregate, no identifiers | `MetricsStore` (`backend/metrics/store.py`) |
| **Knowledge base** | Whatever the operator uploads. Determined entirely by the customer. | Grounding chat answers and zone content | The controller's own, per document set | Until deleted by the operator | `backend/rag/vector_store.py` |

Two things this deployment holds that are keyed to a person: **the profile** and **the audit lines that name a user**. Everything else is aggregate, per-segment or operator-level: cached renders belong to a segment, event counters to a zone and an arm, themes and zone configs to the operator. That is why the access export returns exactly those two things.

## Lawful basis, by what is touched

| What is touched | Rule that bites first | Consequence in this system |
| --- | --- | --- |
| **IndexedDB** (profile cache, chat history) | ePrivacy Art. 5(3): storing or gaining access to information in a user's terminal equipment. The provision is written about the terminal, not about cookies, so IndexedDB is squarely inside it. | Nothing is written or read without an explicit `consent={true}`. `consentGranted` returns true only for a literal `true`, never for `undefined`: an integrator who has not wired a consent flow yet gets the anonymous mode, not a quiet write to the visitor's browser. |
| **A persistent identifier in the request** | Same, plus GDPR Art. 6 for the processing that follows | Without consent no `userId` is sent, so no server-side profile is read or created. |
| **Behaviour capture** | Same | Without consent the tracker is never created at all, rather than created and then filtered. |
| **Tracking-driven personalisation** | GDPR Art. 6, read together with the above. Where ePrivacy requires consent for the access to the terminal, a legitimate-interest balancing under the GDPR does not substitute for it, and the CJEU has taken the position that consent is the correct basis for personalisation built on tracking. | The system's degraded mode is designed for exactly this: refused consent takes the path the framework already runs for every visitor nobody logged in, and for the control arm of a holdout. |
| **Server-side state without an identity** | Data minimisation, Art. 5(1)(c) | A request without a usable identity cannot create per-user state. The refusal is at the one place a profile is born, so no route can route around it: `ProfileStore.set` raises rather than storing, and `is_identified` treats blank, whitespace and the client-side placeholders (`anonymous`, `anon`, `undefined`, `null`, `none`) as no identity at all. (`backend/profiles/store.py`) |
| **Ambient browser signals (DNT, GPC)** | ePrivacy and national implementations | Settled by the same switch: nothing runs without an explicit grant, so there is nothing left for those signals to block, and a visitor who answered a consent prompt has made a more specific statement than a browser-wide default. |

**The commercial consequence, stated once because it is a design property and not a marketing line**: with consent refused or never asked, the deployment still personalises. The segment key collapses to `anon`, the render is generated from the segment archetype, nothing is written to the device, no persistent identifier is used, and the page is still curated. Personalisation that needs no banner is a configuration here, not a workaround. `frontend/tests/consent.test.tsx` and `frontend/tests/degradation.test.tsx` hold that behaviour in place.

## Data subject rights: the runbook

All per-user routes require proof of identity: a signed `X-User-Token` whose subject matches the `user_id`, or an admin key. `check_user_access` (`backend/auth/dependencies.py`) and `authorize_user_access` (`backend/auth/identity.py`) are the single guard. An export endpoint with a weak guard is a data breach wearing a compliance label, so the export uses the same guard as everything else, and `GENUI_DEV_OPEN` does not bypass a configured user-token secret.

### Art. 15 access and Art. 20 portability

```bash
curl -H "X-API-Key: $CLIENT_KEY" -H "X-User-Token: $USER_TOKEN" \
  "http://localhost:8000/api/v1/profile/u-42/export"
```

Returns JSON: the stored profile, plus the audit entries naming that user (renders served, queries asked, impressions and clicks, profile syncs, exports and erasures), with `exported_at` and the tenant. The audit side reuses the trail's own read path, so filtering and tenant scoping cannot drift from the audit viewer's. Structured JSON is a commonly used, machine-readable format for the purposes of Art. 20. Paginate with `limit` (max 2000) and `offset`. `export_user_data` (`backend/api/main.py`), test `backend/tests/test_dsar.py`.

**Read the `audit.queryable` field before answering the request.** In the production default the audit lines are emitted on the `genui.audit` logger and live in the host's log pipeline, which this backend cannot query. The export then returns `"queryable": false` with a note pointing there, rather than an empty history that would read as "nothing ever happened". Completing the access request in that configuration means also querying the log pipeline for that `user_id`. Set `AUDIT_LOG_PATH` (single-worker file sink) to make the trail queryable from the API instead.

### Art. 16 rectification

```bash
curl -X POST -H "X-API-Key: $CLIENT_KEY" -H "X-User-Token: $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u-42","profile_data":{"preferences":{"role":{"value":"analyst","confidence":1.0}}}}' \
  http://localhost:8000/api/v1/profile/sync
```

The store merges by confidence, so a correction supplied at confidence `1.0` wins over an inferred entry. There is no free-form field to correct: the profile is a small, typed structure.

### Art. 17 erasure

```bash
curl -X DELETE -H "X-API-Key: $CLIENT_KEY" -H "X-User-Token: $USER_TOKEN" \
  "http://localhost:8000/api/v1/profile/u-42"
```

```json
{ "status": "deleted", "existed": true, "profile_erased": true, "audit_retained": true, "note": "..." }
```

**What goes**: the profile, which is the whole of the personalisation data held about that person. Cached renders are per segment and contain nothing of theirs.

**What stays, and why the response says so instead of reporting a clean "deleted"**: the audit trail. It is append-only by design, because a record of what was shown to whom is worth nothing if the party who showed it can rewrite it afterwards, and in a regulated deployment it is the operator's own evidence. In the production configuration the lines have already left this process for the host's log pipeline, so the backend could not rewrite them if it wanted to. The trail is bounded rather than edited, by rotation on the file sink and by the pipeline's retention policy otherwise, and the erasure itself is recorded in it, so a later export shows when the right was exercised.

Whether that balance holds is the controller's determination, on their own retention numbers and their own Art. 17(3) analysis. The mechanism does not pretend the tension is not there. `delete_profile` (`backend/api/main.py`), test `backend/tests/test_dsar.py`.

**On the visitor's own device**, erasure is separate and is never gated on consent, because withdrawing it is precisely when clearing is needed: `clearProfile()` and `clearHistory()` from `useGenUI` (`frontend/src/hooks/useGenUI.ts`).

### Art. 21 objection and withdrawal of consent

Withdrawal is one prop. Passing `consent={false}` (or removing it) stops the tracker, stops all IndexedDB access, and stops the `userId` from being sent. The visitor keeps a personalised page, served from the anonymous segment. Server-side state already created does not disappear on its own: pair withdrawal with the erasure call above.

### Investigating what a person was shown (controller side)

```bash
curl -H "X-API-Key: $ADMIN_KEY" \
  "http://localhost:8000/api/v1/audit?user_id=u-42&date_from=2026-07-01&date_to=2026-07-27"
```

Admin key only, always scoped to that key's tenant, never to a tenant named in the query. `query_audit` (`backend/api/audit_router.py`).

## Retention

Storage limitation is configuration here. These are the defaults; the numbers a deployment can justify are the controller's.

| Data | Setting | Default | Notes |
| --- | --- | --- | --- |
| Server-side profile | `PROFILE_TTL_SECONDS` | 7776000 (90 days) | Refreshed on every write, so it expires after inactivity. `0` = keep forever, which makes storage limitation a policy you have to justify yourself. Applies to the Redis store; the in-memory fallback is bounded by size and lost on restart. |
| Audit trail, file sink | `AUDIT_LOG_MAX_BYTES` · `AUDIT_LOG_BACKUP_COUNT` | 50 MB × 5 files | Size-bounded, not time-bounded: rotation drops the oldest file. Rotation is per-process, so the file sink is for single-worker runs. |
| Audit trail, production sink | your log pipeline | your policy | Lines are emitted on the `genui.audit` logger and retained wherever they land. This is the one retention number GenUI does not control, and it is the one most likely to be missed. |
| Audit on or off | `AUDIT_LOG_ENABLED` | `true` | Turning it off removes the accountability record and the audit half of the access export. |
| Cached renders | `ZONE_CACHE_STALE_TTL` | 86400 (24 h) | Per segment, never per person |
| Event counters | none | kept | Aggregate per zone and arm, no identifiers |
| IndexedDB profile and history | the visitor | until cleared | Written only with consent; `clearProfile()` / `clearHistory()` erase it |
| Knowledge base documents | none | until deleted | `DELETE /api/v1/documents/{source}`, tenant-scoped |

`backend/config/settings.py` holds these fields; `deploy/customer.env.example` is where a deployment sets them.

## Transfers and sub-processors: what leaves the perimeter, per configuration

The compose publishes only the backend. Redis and Qdrant are internal and reachable by nothing else. Everything below is about what the backend itself sends outward, and all of it is selected in `customer.env`.

| Configuration | What leaves | What it contains |
| --- | --- | --- |
| `LLM_PROVIDER=openai` with `OPENAI_API_KEY` and no base URL | Every generation prompt goes to OpenAI's API | For a **cached/shared** zone render: base prompt, context prompt, pinned content, page URL and host-supplied page metadata, and the **segment archetype** parsed from the cache key, never the requesting visitor's raw profile (`_agent_request`, `backend/api/zone_router.py`). For a **live** render (`cache_strategy="live"` or cache disabled): the individual profile and behaviour data. For `/query`: the visitor's question text, the last 5 conversation messages, the profile when one applies, and the retrieved document chunks. No `user_id` and no API key are ever placed in a prompt. |
| `LLM_PROVIDER=anthropic` / `gemini` | Same content, to that provider | Same as above |
| `LLM_PROVIDER=openai` with `OPENAI_BASE_URL` pointing inside the network (vLLM, Ollama, Azure in-tenant, TEI, RunPod in a private VPC) | Nothing leaves the network | Same payloads, delivered to a host you control |
| Embeddings, default | `EMBEDDING_BASE_URL` falls back to `OPENAI_BASE_URL`, so embeddings follow the LLM by default | **Document chunks at ingest** and **the query text at retrieval time**. The retrieval path means a visitor's chat question reaches the embedding endpoint as well as the LLM. |
| `EMBEDDING_PROVIDER=gemini` | Embeddings go to Google regardless of the LLM choice | Same content |
| `EXTRACTOR_BACKEND=local` (default) or `docling`, or `glmocr` with `GLMOCR_BASE_URL` | Nothing leaves | Uploaded documents are parsed in-process or on a host you run |
| `GLMOCR_API_KEY` set (Z.ai cloud mode) | **Uploaded documents leave the infrastructure** | Whole documents, whatever they contain. This is opt-in and it is the single largest egress in the matrix. |
| `TRACING_ENABLED=true` with `OTLP_ENDPOINT` | Spans go to that collector | The spans this codebase creates carry metadata only: zone id, tenant, provider name, model name, batch size (`span(...)` at `backend/api/zone_router.py`, `backend/llm/openai_client.py`, `backend/llm/embeddings.py`). No prompt content, no profile, no `user_id`. **Honest exception**: FastAPI auto-instrumentation adds HTTP attributes, and the per-user routes carry the `user_id` in the URL path, so a trace of `GET /api/v1/profile/u-42/export` puts that identifier in the collector. Point `OTLP_ENDPOINT` inside the perimeter, or treat the collector as a processor. |
| `TRACING_ENABLED=true` without `OTLP_ENDPOINT` | Nothing leaves | Console exporter: spans go to the container logs |
| Audit sink, production default | The `genui.audit` logger, then wherever the host's log pipeline ships it | `user_id`, tenant, zone, segment, cache state, the titles and links shown. If that pipeline is a hosted service, it is a processor holding personal data, and it is easy to overlook because it is not configured in `customer.env` at all. |

### The configuration where nothing leaves the perimeter

This is the deployment that answers "no transfer" without an asterisk, and it is a `customer.env`, not a fork:

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://vllm.internal:8000/v1   # your own engine, your own network
OPENAI_API_KEY=whatever-your-endpoint-wants

# Embeddings inherit OPENAI_BASE_URL: nothing to set, nothing leaves
EMBEDDING_MODEL=<a model your endpoint serves>

EXTRACTOR_BACKEND=local        # or docling; never set GLMOCR_API_KEY
TRACING_ENABLED=false          # or true with an OTLP_ENDPOINT inside the perimeter
AUDIT_LOG_ENABLED=true         # ship the logger sink to a pipeline you host
PROFILE_TTL_SECONDS=7776000
```

Redis and Qdrant are already internal in the shipped compose. With the above, the entire processing chain (profiles, prompts, generations, embeddings, documents, traces, audit) runs on the customer's own infrastructure, and Chapter V does not enter the analysis. `./posture.sh` prints the egress map for whatever configuration is actually in place, including the uncomfortable answers.

## DPIA support (Art. 35)

**The DPIA is the controller's.** This section is an input to it, not a substitute, and it does not conclude whether one is required.

Systematic profiling on a large scale is one of the criteria that commonly triggers a DPIA, and a portal serving on the order of 10^5 visitors a day with per-visitor content selection sits close to it. The likely honest starting position for a deployment that uses identified personalisation is that a DPIA is required.

**Risk factors that are real in this system**

| Factor | Why it is real here | Measure already present |
| --- | --- | --- |
| Systematic profiling of visitors | The product builds a profile from behaviour and uses it to select content | The profile is small and typed (role, interests with confidence, user type), the segment is a deterministic function of four coarse dimensions with no model in the loop, and both are human-readable and logged. `compute_segment` (`backend/segmentation/segmenter.py`) |
| Terminal access without consent | IndexedDB writes on every visitor would be the default failure mode | Consent-gated at a single choke point; the default with no consent flag is the anonymous mode. `consentGranted` (`frontend/src/utils/privacy.ts`) |
| Free-text capture picking up personal data | Behaviour capture reads text near what the visitor interacts with | Form fields are never captured at any level; `data-genui-private` excludes a subtree entirely, `data-genui-redact` reduces it to shape; the `balanced` level redacts common PII shapes (email, IBAN, codice fiscale, long digit runs); `strict` drops free text altogether. `redactPII` (`frontend/src/utils/privacy.ts`) |
| Special-category data arriving through the chat | The question is free text and a visitor can type anything, including health or financial details | No mechanism prevents it. The mitigation is retention (nothing per-conversation is stored server-side) and the audit trail recording what was shown rather than what was asked. |
| Transfer to an LLM provider | BYOK means prompts reach the provider the controller chose | Shared renders send the segment archetype, not the individual profile. The all-local configuration above removes the transfer entirely. |
| Content the model invents | Wrong information shown to an individual | The post-generation guarantee chain: no invented link, no invented number where the number is the content, banned terms enforced per tenant, pinned content enforced into the output. `deploy/OUTPUT-GUARANTEES.md` |
| Cross-tenant leakage | One deployment serves several audiences | Tenant resolved server-side from the API key and enforced at every storage key and query filter. `deploy/TENANT-ISOLATION.md` |
| Being unable to answer "what did this person see" | Accountability, and Art. 15 in practice | Append-only audit trail with the titles and links actually shown, queryable per user. `AuditLogger.log` (`backend/utils/audit.py`) |
| Automated decisions with legal or similarly significant effect (Art. 22) | Not what this system does, and the boundary matters | GenUI curates presentation. It does not decide prices, eligibility, coverage, hiring or creditworthiness. Wiring it into one of those changes both the GDPR analysis and the AI Act regime: see the use boundaries in [AI-ACT.md](AI-ACT.md). |

**What the controller still has to do**, and no configuration produces it: choose and document the lawful basis, run the consent mechanism (GenUI consumes a consent decision, it does not collect one), sign the processor and sub-processor agreements including with the LLM and embedding providers, write the DPIA and the ROPA entries, set retention numbers they can justify, run the transfer assessment if any of the egress rows above is outside the EEA, and handle the requests this runbook only gives them the mechanics for.

## Honest limits

- **There is no consent management platform here.** GenUI takes a boolean. Collecting, recording, timestamping, proving and re-asking for consent is the controller's CMP, and this system holds no consent record of its own.
- **Erasure does not reach the audit trail.** Stated in full above rather than softened. If the controller's analysis concludes the trail must be erasable, the honest answer today is to turn auditing off, which removes the accountability record and the audit half of the access export.
- **The access export is complete for this deployment, not for the customer's stack.** It returns what GenUI holds. Whatever the host application stores about the same person is theirs to add, and so is whatever a hosted log pipeline still holds.
- **PII redaction is pattern-based.** Email, IBAN, Italian codice fiscale and long digit runs are matched; free-text street addresses are not reliably detectable by regex, which is why `data-genui-private` exists and is documented as the answer for address blocks. Over-redacting a product code is acceptable; the reverse is not.
- **Pseudonymous, not anonymous.** The `user_id` is minted by the customer's backend and is personal data in their hands. The `anon` segment path is genuinely identifier-free; the identified path is pseudonymisation, which is a security measure, not an exit from the Regulation.
- **The in-memory fallback ignores the TTL.** When Redis is unavailable the profile store falls back to bounded per-process memory, which is size-capped and lost on restart rather than expiring on `PROFILE_TTL_SECONDS`. In practice that is shorter retention, not longer, but it is not the configured rule.
- **Nothing here enforces the use boundaries.** No code path refuses to render a price or a job advertisement. See [AI-ACT.md](AI-ACT.md) for where those boundaries are and what the system does and does not do about them.

## How to re-verify this document

```bash
# Rights, identity guards, consent behaviour and retention mechanics:
cd backend && python3 -m unittest discover -s tests
cd frontend && npm test

# The references in this file still point at symbols that exist:
cd backend && python3 -m unittest tests.test_deploy_docs -v

# What this deployment's configuration actually does, egress map included:
cd deploy && ./posture.sh
```

Related: [AI-ACT.md](AI-ACT.md) (transparency obligations and use boundaries), [TENANT-ISOLATION.md](TENANT-ISOLATION.md) (the data boundary between tenants), [OUTPUT-GUARANTEES.md](OUTPUT-GUARANTEES.md) (what is enforced on generated content).
