# Changelog

All notable changes to the GenUI framework, in [Keep a Changelog](https://keepachangelog.com/) shape: everything lands under **[Unreleased]** until a release exists.

No release has been cut yet - no npm/PyPI publish, no git tag (the Zenodo DOI is a frozen master thesis snapshot, not a package release).

The entire history lives below, newest first.

## [Unreleased]

### Three editorial components: case studies, quote, logo wall

Added for studio / agency / editorial zones, where the existing catalog leaned SaaS. Same token system, same validation and guarantee pipeline, no new dependencies (the shadcn/lucide/react-countup/framer references in the design inspiration were re-implemented with CSS tokens, emoji/SVG, and a vanilla count-up).

- **`case_studies`**: projects with an optional image, an optional named reference, and optional result metrics, in an editorial layout: [media + body] divided from the figures by a vertical rule, alternating sides case by case, generous spacing. Metric values are numeric-grounded like `stats_banner` (an invented figure is dropped, the case survives on its text); they count up on scroll into view, static under SSR or `prefers-reduced-motion`, and the settle value is the input string verbatim (no locale reformatting). No image → the case is text-first and the grid reflows (`:has()`), no metrics → the rule and figures column are dropped.
- **`quote`**: a single large editorial quote / manifesto. Author, role, avatar and the top logo are each optional and simply omitted when absent — no initials fallback, the statement is the point. The logo label is never printed beside a logo image (most logo files are already wordmarks); it becomes the image alt, and renders as a text wordmark only on its own.
- **`logo_wall`**: a grid of logos (clients, technologies, partners — the heading names what it shows, it is not client-specific). A logo with no usable image is dropped; the grid centers and wraps; the hover reveal appears only when a real overall cta link is given, otherwise it is a plain static wall.

All three are exported from the package, registered in `ComponentRenderer`, in `BUILTIN_TYPES`, and in the zone prompt catalog. The URL guard now also classifies `logo_url` / `*_logo` as image fields (a link can't fill a logo). The Theme Playground shows each with a full and a degraded example.

### Zone component budget (enforced, default 2)

A zone is one band of a host page — typically sitting between CMS-built sections — not a page. Left unbounded, the model would happily emit five or six components per zone (bento + text + buttons + quote + tabs + steps), wrecking the host page's rhythm. Now every zone render has a component budget:

- **`ZONE_MAX_COMPONENTS`** (default **2**) is the deployment default; `max_components` on the request or in the zone config registry overrides it per zone (1-10). The budget is part of the zone cache config, so changing it invalidates cached renders.
- The model is told the budget (and the "one band, not a page" principle) in the prompt; `apply_component_budget` then **enforces** it after validation on both the sync and SSE paths — extra components are cut in order (first ones win) and reported in `meta.sanitization.dropped_components` as "over the zone component budget".
- Pinned enforcement runs after the budget on purpose: the pinned-content guarantee may exceed the budget rather than be silently dropped.

**Behavior change**: zones that previously rendered 3+ components now render at most 2 by default. Raise `ZONE_MAX_COMPONENTS` or set `max_components` per zone to opt out. Cached renders are invalidated once on deploy (config hash change).

### Degradation audit: every component renders only what it has

Systematic pass over all 14 components for every optional-field subset and cardinality (0/1/2/N items). Most already degraded by design (hero CTAs are conditional, a single tab drops the tab bar, autoplay needs 2+ steps, single testimonial drops arrows/dots, grids cap columns by item count). Three gaps fixed:

- **`pricing_cards`**: a plan with no features no longer renders an empty list; `variant: "detailed"` with a single plan degrades to plain cards (a comparison table of one compares nothing).
- **`quote`**: an avatar without an author is not rendered — an anonymous face attributes nothing.
- **Prompt rule 10 "omit what you do not have"**: the model is told every optional field is genuinely optional (one CTA or none, no figures, no author, two stats instead of four) and that components are designed to degrade — padding a component to look complete is worse than leaving fields out.

Pinned by a dedicated degradation test suite (hero 0/1 CTA, pricing empty features and single-plan detailed, orphan avatar, single tab).

### Images can no longer come from link URLs (enforced)

A zone rendered with a single pinned link would reuse that link everywhere it needed a URL, including as an `<img src>` — a page URL pointed at by an `<img>` renders as a broken image. Root cause: the URL guard kept one whitelist for every URL field, so a link URL satisfied an image `src` just as well as an `href`. Now:

- **Separate image and link whitelists** (`utils/url_guard.py`): image fields (`src`, `image`, `image_url`, `avatar_url`, …) accept only URLs that genuinely came from an image source — a pinned item declared `type: "image"`, RAG `metadata.image`, an image-named page-metadata key, or any URL with an image file extension. A plain link never satisfies an `<img src>` and is stripped. Link fields (`href`, `url`, `link`) are unchanged. The image whitelist is a strict subset of the link whitelist (an image can also be a link, not vice versa).
- **Variant re-coherence after stripping** (`schemas/components.py` `downgrade_image_variants`): when an image is removed from a component that required one, the component degrades to its text-only form instead of leaving an image-shaped hole — hero `split` → `centered`, and `with-image` → `text-only` for steps, tabs and content-grid (per item/tab). Runs after the guard on both the sync and SSE paths. This also fixes a latent bug where an _invented_ image URL was stripped and left the same hole.
- **Prompt reinforcement**: rules that a link is never an image (choose an image variant only when the input has an image URL), and that not every card/CTA needs a link — with one link, use it once where it matters rather than pointing every element at the same URL. Best-effort, the guard is the guarantee.

### Text component no longer invited to explain itself

The `text` component was described in the prompt as "Introductory or explanatory text", which contradicted the rule against page meta-commentary (added the day before) and led the model to emit reasoning as content ("Simple, focused, and easy to scan"). Its description is now "short body copy the visitor reads … never a description of the page, the audience, or your choices", and the style enum is clarified as purely visual. Prompt-level and best-effort — natural-language meta-commentary is a judgment call, not mechanically enforceable like URLs or numbers.

### Container-responsive zones

Every component breakpoint was viewport-based (`@media`), so a zone embedded in a narrow container of a wide page (sidebar, column, preview panel) laid out as if it owned the whole viewport: 3-column bento grids squeezed into 400px, hero headlines at 52px inside a card. Zones are embeddable fragments, so they now respond to their own width:

- `.genui-section` (the wrapper every `GenUIZone`/`GenUISection` renders) is a size container (`container-type: inline-size`), and the viewport grid rules gained `@container` mirrors at the same thresholds, measured on the zone instead of the window. The `@media` rules remain as the fallback for browsers without container queries. `.genui-layout-complex` (host opt-in class, never emitted by a zone render) is deliberately not mirrored.
- In narrow containers the hero headline scales with the zone (`cqw`), bento cards drop the 320px forced min-height to 220px, and long single words in bento titles/hero headlines wrap instead of clipping.
- **Fixed (grid columns, all sibling components)**: a grid with more columns than items squeezed each card into a fraction of the zone. `BentoComponent` emitted the LLM-requested column count even with fewer cards (`genui-bento--cols-1` now styled explicitly); `ContentGrid` did the same with its default of 3; `StatsBanner` capped only when no column count was given, so an explicit model-sent `columns: 4` with 2 stats left empty cells. All three now cap columns by item count (as `PricingCards` already did).
- **Fixed (title clipping, all headings)**: `overflow-wrap: anywhere` now applies to every heading a zone renders (bento, hero, content grid, pricing, stats, testimonials, tabs, steps, chart), so a long single word wraps instead of clipping or overflowing in a narrow column, not just on the two headings where it first surfaced.

Additive: full-width zones on wide viewports render identically to before.

### Zone copy voice and bento caption polish

- **Prompt rule (backend, quality lever)**: the ZoneAgent was free to emit meta-commentary as visible content ("Built for a developer audience...", cards badged "Pinned"): a description of the curation instead of page copy. New system rule 8 "write as the page, not about the page": audience/layout/strategy talk and internal labels are banned from components; selection logic goes only in the `reasoning` field. Prompt-level (best effort, like tone), not mechanically enforceable.
- **Fixed (CSS)**: `.genui-bento-card__content` carried the photo-caption scrim (dark background, blur, top border) into text-only cards, painting a visible box whose backdrop-filter layer ignored the card's border radius (WebKit/Blink compositing). Text-only content is now transparent; the with-image caption bar rounds its own bottom corners (`border-bottom-*-radius: inherit`) so the blur layer follows the card shape.

### Frontend/Backend contract fidelity

Cross-cutting audit of the FE/BE contract (`roadmap/incongruenze-fe-be/`): three cases where the backend produced data the frontend type declared but the runtime silently dropped, never rendered, or mutated.

#### Fixed: `useGenUI` no longer discards `meta.behavior`

The backend orchestrator attaches behavior analysis to `/query` responses (`engagement_score`, `user_type`, `session_summary`, `insights_count`, `ui_adjustments`) and `ResponseMeta.behavior` declared it, but the hand-built meta mapping skipped it, so it was always `undefined`. It is now mapped to typed camelCase `BehaviorMeta` at the same choke point as `meta.sanitization`. Additive: still `undefined` when the backend omits it.

#### Fixed: `BentoCard.action` renders

The backend schema emits an optional per-card action button (`CardAction`: `label` + `url`) and the CSS for `.genui-bento-card__action` already existed, but `BentoComponent` never rendered it: a card action disappeared silently. It now renders as a link button (URL through `sanitizeUrl`; an action whose URL is dropped as unsafe renders nothing rather than a dead button). When both `link` and `action` are present the action wins and the card-level link wrapper is skipped, because nested anchors are invalid HTML and SSR parsers split them.

#### Fixed: card `metadata` is no longer camelized

`normalizeData` recursively camelized every nested key, including `BentoCard.metadata`, which the contract declares as opaque pass-through: a host key like `external_id` arrived mutated to `externalId`. `metadata` values are now copied verbatim (same reasoning as custom components, which already skip normalization entirely). The FE `BentoCard` type now also declares `metadata`.

### Output guarantees: numeric grounding & content policy

#### Added: numeric grounding (enforced, on by default)

"Never invent numbers" was a prompt instruction; now it is enforced like the URL whitelist. A number displayed _as_ the content (a `stats_banner` value, a `pricing_cards` price, a `chart` data point) survives only if its digits trace to a number present in the input (pinned content, prompts, RAG documents, page context; verbatim modulo formatting, no magnitude conversion). Ungrounded stats/plans are removed and reported in `meta.sanitization.removed_numbers`; one ungrounded chart point drops the whole chart. Applies on sync, SSE and `/query`, always before caching. **Behavior change**: zones whose stats/prices/charts relied on model-known numbers not present in any input will lose those items. Put real figures in the prompt/pinned/RAG (where they should have come from), or set `NUMERIC_GROUNDING_ENABLED=false` to opt out. Numbers inside prose are deliberately not checked.

#### Added: per-tenant content policy (banned terms)

`CONTENT_POLICY` (JSON env, per tenant plus `"*"`) declares banned terms enforced post-generation: a component containing one is dropped, chat `text_response` is redacted, hits land in `meta.sanitization.policy_violations`. Matching is lexical (case-insensitive, word-boundary, phrase-aware); tone stays prompt-level best-effort and is documented as such. Invalid policy JSON fails loudly instead of silently disabling. Off when unset.

#### Fixed: `/query` chat prose was never link-stripped

The URL whitelist covered components but not the chat `text_response`: an invented markdown link in the prose reached the client intact. The chat text now gets the same treatment as text components (non-input links collapse to their text). `/query` responses also gained `meta.sanitization` (same shape as zone renders).

#### Added: the guarantees as a contract document

`deploy/OUTPUT-GUARANTEES.md`: every output guarantee with its enforcing code reference, its test, and its honest limits (enforce vs best-effort), written for a customer's legal/compliance team. The golden harness now also asserts numeric grounding (invariant + adversarial invented-price fixture).

#### Added: frontend: `meta.sanitization` exposed by the hooks

`useZone` and `useGenUI` previously discarded the backend's sanitization report while mapping `meta`; it is now exposed as typed camelCase `meta.sanitization` (`SanitizationReport`: `removedUrls`, `droppedComponents`, `removedNumbers`, `policyViolations`) on both zone renders and `/query` responses. Additive: `undefined` on older backends.

### Deployment & tenant topology

#### Added: reproducible per-customer deployment (`deploy/`)

One GenUI deployment per customer is now a product artifact instead of a manual procedure: `deploy/docker-compose.yml` brings up the backend (multi-worker uvicorn, `backend/Dockerfile`, non-root, stateless) + Redis (AOF) + Qdrant (pinned) with one command, parametrized by a single per-customer `customer.env` (engine BYOK, tenant declaration, budgets, CORS, retention). Redis and Qdrant are not published on the host; the backend is the single entry point. `deploy/smoke.sh` is the post-bring-up acceptance check (liveness, healthy status, fail-closed auth, per-tenant scoping of every declared admin key). Docs: `deploy/README.md` (bring-up, tenant declaration model, engine/embedding BYOK matrix, ops notes) and `deploy/TENANT-ISOLATION.md`, the per-data-type isolation statement with code references, for the customer's security team. New `tests/test_kb_tenant_filter.py` pins the Qdrant tenant filter shape the isolation document cites. `backend/docker-compose.yml` stays as the dev helper.

#### Fixed: multi-worker boot race creating the Qdrant collection

On a fresh Qdrant, several uvicorn workers booting together all saw the collection as absent and all tried to create it: one won, the others got a 409 and failed their vector-store/orchestrator init (health reported `qdrant_connected: false` until those workers were recycled). Losing the create race is now treated as "collection exists" and validated like any other boot (`rag/vector_store.py::_ensure_collection`). Single-worker dev setups never hit this.

### Zone config registry

#### Added: config as data (server-side zone config registry)

Zone configuration (prompts, pinned content, rendering constraints) can now live server-side as a versioned, per-`(tenant, zone_id)` registry entry (`zones.ZoneConfigStore`, Redis or in-memory like the other stores). When an **approved** entry exists, every render path (sync, streaming, batch, warmup) serves exactly that config and ignores the host props for the governed fields; without an entry, props work exactly as before: no behavior change for existing integrations. Entries carry `version` and `status` (`draft` entries are stored but never served), and approving a new version invalidates cached renders automatically. Management is Python-level for now; CRUD/approval endpoints and Studio UI are the next phases of `roadmap/strategiche/01`. See README § Zone Config Registry.

### Frontend distribution

#### Fixed: `require('genui-framework')` no longer throws ERR_REQUIRE_ESM

`package.json` now has a proper `exports` map with dual builds: `import` resolves the ESM entry (`dist/index.esm.js`), `require` resolves a real CJS entry (`dist/index.cjs`, new extension because the package is `"type": "module"`). Jest, Next.js pages router and other CJS toolchains can now load the package. If you deep-imported `genui-framework/dist/index.js`, switch to the package root (the old path no longer exists); `genui-framework/dist/styles.css` keeps working (also available as `genui-framework/styles.css`). `sideEffects` is declared so the CSS import survives tree-shaking.

#### Changed: bundle: charts lazy, framer-motion removed

- **recharts moved to a lazy chunk** loaded on first chart render. Entry bundle (ESM, gzip): **460 KB → ~134 KB (-71%)**; the chart chunk (~232 KB) is only downloaded by pages that actually render a chart. `<ChartComponent />` API is unchanged (built-in Suspense boundary; a skeleton shows while the chunk loads).
- **framer-motion is no longer a dependency**: the bento hover scale is now plain CSS (visually identical, and it finally respects `prefers-reduced-motion`).

#### Changed: SSR renders the loading skeleton

`renderToString` of a zone with `loadOnMount` (the default) now emits the loading skeleton instead of **empty HTML**: stable server markup, no CLS, hydration-consistent. With `loadOnMount={false}` the server still renders nothing.

#### Changed: zone props are reactive

Changing `zoneId`/`userId`/`basePrompt`/any request-shaping prop on a mounted zone now **refetches automatically**, aborting the inflight request (last issued wins). Previously the zone fetched only on mount and went stale across SPA route reuse. Props are compared by value, so inline object literals don't cause fetch loops. If you relied on the old "fetch once, ignore prop changes" behavior, mount the zone with a stable `key` and fixed props.

#### Changed: unknown component types degrade silently in production

An unknown component type (typically an old bundle talking to a newer backend) renders **nothing** in production builds (`console.warn` only) instead of printing "Unknown component type" into the end user's page. Dev builds still show the inline error box. Same rule for unknown chart types.

#### Added

- **`contract_version`** field on zone render and `/query` responses (exposed as `meta.contractVersion` / `contractVersion`), so deployed bundles can detect a newer backend contract.
- **Accessibility**: tabs follow the WAI-ARIA pattern (roving tabindex, arrow/Home/End keys, `aria-controls`/`aria-labelledby`); the testimonial carousel pauses autoplay on hover/focus and announces quote changes (`aria-live`); a global `prefers-reduced-motion` CSS block stops all infinite genui animations.
- **Frontend test suite on vitest** (`cd frontend && npm test`): packaging boundary (real-Node `require`/`import` subprocesses), SSR skeleton, reactive-props refetch/abort, plus the privacy filter contract migrated from node:test (same 18 tests, no tsc pre-build step).

#### Changed: observability: /health no longer exposes collection internals

- **`GET /health` returns dependency statuses only** (`status`, `qdrant_connected`, `redis`, and the new `llm: "configured" | "unconfigured"`). The unauthenticated `collection_stats` payload is gone; point counts and index state live behind the admin key at `GET /api/v1/documents/stats`. Update anything that parsed `collection_stats` from `/health`.
- The audit file sink (`AUDIT_LOG_PATH`) now **rotates by size** (`AUDIT_LOG_MAX_BYTES`, default 50 MB, `AUDIT_LOG_BACKUP_COUNT`, default 5) instead of growing unbounded. Set `AUDIT_LOG_MAX_BYTES=0` for the old append-forever behavior.

#### Added: observability

- `GET /ready` (load balancers: 503 only when the LLM provider is unconfigured and nothing can be served) and `GET /live` (process liveness).
- `GET /metrics` (admin key): Prometheus text format with HTTP request counts/latency per route, zone renders per cache outcome (`fresh|stale|miss|coalesced|bypass`), LLM generations and latency per tenant/op/outcome, and dependency gauges. Counters are shared across workers via Redis, so any worker serves a truthful scrape.
- `genui.query` tracing span on `/api/v1/query`, tying the existing `genui.llm.*` client spans to the chat path.
- README "Observability" section: production configuration for health, metrics scraping, the audit sink and tracing.

#### Changed: cost controls: public keys can no longer trigger unbounded LLM spend

With BYOK the LLM bill is on the operator's key, and the client `pk_` key is public. Three request-side amplifiers are closed (backend only, no frontend API change):

- **`cache_strategy: "live"` now requires an admin key.** Client keys sending it receive a **403** and should use the segment cache. If your integration set `cacheStrategy="live"` on a browser zone, remove the prop or move that render behind a server-side proxy with an admin key.
- **`/zone/batch-render` is capped** at `ZONE_BATCH_MAX` zones (default 10, 413 above) and a batch of N zones now consumes N rate-limit slots instead of 1.
- **Cold cache misses are single-flight**: concurrent requests for the same (zone, config, segment) coalesce on one generation and report `meta.cache.status: "coalesced"`. Previously each concurrent request paid its own identical LLM call.

#### Added

- `LLM_BUDGET_PER_HOUR`: per-tenant hourly cap on LLM generations, consistent across workers (shares the rate-limit Redis store). Over the cap, cached renders keep being served (stale entries stop refreshing) and new generations return 429. Disabled by default; set it in production.
- `LLM_TIMEOUT_SECONDS` (default 60): explicit timeout on every LLM and embedding provider call, replacing the SDK default of 10 minutes.
- `ZONE_BATCH_MAX` (default 10): batch-render size cap.

### Behavior tracking privacy

#### Changed: behavior tracker default is no longer "capture everything"

The frontend behavior tracker now has a **privacy filter with a safe default** (`privacy: 'balanced'`). This changes what leaves the browser for existing integrations, without changing the API shape:

- Clicked element text, page titles, referrers, link hrefs and navigation paths are **PII-redacted** (emails, IBANs, Italian codici fiscali, 8+ digit runs) before being stored or sent.
- Form field content (`<input>`, `<textarea>`, `<select>`, contenteditable) is **never captured**, at any level.
- `navigator.doNotTrack` and Global Privacy Control are **honored** (tracker does not start), unless `privacy: 'off'`.
- `enableBehaviorTracking` still defaults to `true`.

To restore the previous raw capture, opt out explicitly: `useGenUI({ privacy: 'off' })`.

#### Added

- `data-genui-private` (never record the subtree) and `data-genui-redact` (record shape, never content) DOM attributes, respected at every privacy level.
- `privacy: 'strict' | 'balanced' | 'off'` and `consent: boolean` options on `useGenUI` and `BehaviorTrackerOptions` (exported `PrivacyLevel` type). `consent: false` blocks tracking entirely; `consent: true` records the host CMP's explicit grant and overrides DNT/GPC.
- The auto-captured `current_page` sent by `useZone` follows the tracker's privacy level.
- Capture contract documented per level in the README ("Behavior Tracking & Privacy") for DPO sign-off.
- Frontend test harness seed: `cd frontend && npm test` (node:test + tsc, no new dependencies) covering the privacy filter contract.
