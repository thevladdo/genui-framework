# GenUI AI Act Statement

**Audience**: the legal or compliance team of an entity putting a GenUI deployment into service. This document is written to be attached to a contract.

**This is engineering documentation, not legal advice.** It describes mechanisms that exist in the code, names the symbol that implements each one and the test that proves it, and states where the mechanism stops. It does not certify anything, and nothing in it says a deployment is compliant. That assessment belongs to the entity putting the system into service, made by its own counsel on its own facts. What this document is for is making that assessment a review of a written artifact instead of a reading of a codebase.

**Scope**: one GenUI deployment serving generated UI (`/zone/render`, `/zone/render/stream`, `/zone/batch-render`, warmup, background refreshes) and chat answers (`/query`), with the React library rendering them.

**As of**: 2026-07-27. References name the file and the symbol, never a line number: a line number is wrong as soon as anything above it moves, and a reader who follows a stale one lands on unrelated code. Re-verify any row with `grep -n "<symbol>" <file>`. `backend/tests/test_deploy_docs.py` fails when a named file or symbol disappears, and when a line number reappears.

## Who answers for what

| AI Act role | Who that is, for a GenUI deployment | What lands on them |
| --- | --- | --- |
| **Provider** (Art. 3(3)) | The customer. They integrate GenUI and put the resulting system into service on their own site under their own name. | Art. 50(1) inform that the user is interacting with an AI system; Art. 50(2) mark synthetic output in a machine-readable format. |
| **Deployer** (Art. 3(4)) | The same customer, using the system under their own authority. On-prem, provider and deployer are the same legal person. | Art. 50(4) disclose generated text published to inform the public on matters of public interest, unless it underwent human review with a natural person holding editorial responsibility. |
| **Component supplier** | The author of the open source framework. Does not place a system on the market and does not operate a service. | No direct Art. 50 obligation until they put a system of their own into service. The obligation the framework carries is practical, not legal: without these mechanisms no EU provider can use it. |

**The open source exception does not move this.** Art. 2(12) excludes AI systems released under free and open source licences from the Regulation, *except* where they are high-risk, fall under Art. 5, or **fall under Art. 50**. Releasing under Apache 2.0 changes nothing about the transparency obligations: it only means they sit with the provider, which is the customer.

**Penalties** (Art. 99): infringement of the Art. 50 transparency obligations is subject to fines up to **EUR 15,000,000 or 3% of total worldwide annual turnover**, whichever is higher (for SMEs and startups, whichever is lower). Art. 50 and Annex III apply from **2 August 2026**.

## Obligation by obligation

| Obligation | Who answers for it | Mechanism in the system | Where | Test |
| --- | --- | --- | --- | --- |
| **Art. 50(1)** the user must be informed they are interacting with an AI system, at the latest at the first interaction | Provider (customer) | The chat hook returns the interaction notice before any answer exists, from the first paint, because the obligation falls due before there is output to label. `disclosure.aiInteraction` is true whenever answers come from a model; `disclosure.notice` is ready-to-render wording the host overrides with `disclosureText`, since the formulation is a legal choice. `/query` answers additionally carry `meta.disclosure`. | `useGenUI` (`frontend/src/hooks/useGenUI.ts`); `DEFAULT_CHAT_DISCLOSURE_TEXT`, `PENDING_DISCLOSURE` (`frontend/src/utils/disclosure.ts`); backend side `disclosure_block` wired at `backend/agents/response_agent.py` | `frontend/tests/disclosure.test.tsx`, `backend/tests/test_disclosure.py` |
| **Art. 50(2)** output must be marked as artificially generated in a machine-readable format | Provider (customer) | Every served payload carries a `disclosure` block: `ai_generated`, `provenance`, `generated_at`, `system`. It is computed inside the agent, at generation time, and written into the payload that goes to cache, so a render served for a whole stale window repeats the timestamp of the generation that actually happened. It is on every serving path: sync, SSE `complete`, batch, warmup, every cache hit, and `/query`. | `disclosure_block` (`backend/utils/disclosure.py`); computed by `_disclosure_for` (`backend/agents/zone_agent.py`); written into the cacheable payload by `_payload_from_result` (`backend/api/zone_router.py`) | `backend/tests/test_disclosure.py` |
| **Art. 50(2)** the marking must be readable by a third party, not only by our own API | Provider (customer) | The zone root carries `data-ai-generated` and `data-ai-provenance`, plus a JSON-LD block using the IPTC `digitalSourceType` vocabulary (`trainedAlgorithmicMedia` for generated content), which is the vocabulary C2PA also uses. No effect is involved, so the markup is in the server-rendered HTML and in the first paint of a streamed render. | `disclosureJsonLd`, `digitalSourceType` (`frontend/src/utils/disclosure.ts`); emitted at `frontend/src/components/GenUIZone.tsx` | `frontend/tests/disclosure.test.tsx`, `frontend/tests/ssr.test.ts` |
| **Art. 50(2)** a render that no model wrote must not be marked as generated | Provider (customer) | A fallback render is assembled from the operator's own pinned content after a generation failure. It reports `ai_generated: false` and provenance `not-generated`. Marking the operator's own content as AI-written would be a false marking in exactly the direction the obligation exists to prevent. | `_fallback_render` (`backend/agents/zone_agent.py`), which writes the block itself | `backend/tests/test_disclosure.py` |
| **Art. 50(4)** deployer disclosure of generated text published to inform the public on matters of public interest | Deployer (customer) | Partial, and the boundary is in the section below: the zone config registry gives draft and approve with an admin identity on the **configuration**. The generated **text** is not what gets approved. What the system does provide for the text is the audit trail of what was actually shown, which is evidence of publication, not review. | `approve_zone_config` (`backend/api/zone_config_router.py`); `ZoneConfigStore.get_approved` (`backend/zones/registry.py`); audit `AuditLogger.log` (`backend/utils/audit.py`) | `backend/tests/test_zone_governance.py`, `backend/tests/test_rate_limit_audit.py` |
| **Art. 50(5)** the information must be clear and distinguishable at the latest at the first interaction or exposure, and conform to accessibility requirements | Provider and deployer (customer) | A visible line of text, on by default whenever the content is generated, rendered as text and never as a CSS value, styled with the `--genui-*` tokens so it carries a value in both colour modes, with no information conveyed by colour alone. Wording and position are host-configurable because the formulation is the customer's legal choice. Size and opacity are clamped at both ends in the library and in the store that persists them: the notice can be made discreet, never unreadable. It is available as a standalone component for hosts that render components themselves. | `GenUIDisclosureNotice` (`frontend/src/components/DisclosureNotice.tsx`); `noticeComesFirst` (`frontend/src/utils/disclosure.ts`); theme persistence in `backend/utils/theme_store.py` | `frontend/tests/disclosure.test.tsx`, `backend/tests/test_theme_store.py` |
| **Default posture** | Provider (customer) | Disclosure is on unless it is explicitly turned off. `GENUI_DISCLOSURE_OFF=1` removes the block from every payload and, with it, the library's markup and notice; setting it is a declaration that the transparency information is provided elsewhere in the product. It is logged as a warning at every startup, so an operator who inherits a deployment reads the posture off the logs. | `genui_disclosure_off` (`backend/config/settings.py`); startup warning in `lifespan` (`backend/api/main.py`) | `backend/tests/test_disclosure.py` |

The model name is **not** in the marking by default (`DISCLOSURE_EXPOSE_MODEL=false`). What the obligation asks is that the reader knows the content is artificially generated, not which model wrote it; naming it publishes an attack target and the operator's vendor choice at the same time. Turning it on is one env var.

## The Art. 50(2) exemption: what the system gives you, and what it does not

Art. 50(2) does not apply where the AI system performs an assistive function for standard editing or does not substantially alter the input data provided by the deployer or their semantics.

This deployment can produce **evidence** relevant to that assessment, which is unusual, because the output guarantee chain already knows exactly which URLs and which numbers came from the input corpus. The same corpus is reused to compute the `provenance` field:

- `generated`: a model wrote original text.
- `verbatim-from-input`: a model ran, and every visible string in the component data appears verbatim in the input corpus.
- `not-generated`: no model output is being served.

`content_provenance` (`backend/utils/disclosure.py`) computes it by comparing every string in every component's `data` against the normalised input corpus. Matching is substring-based on lowercased, whitespace-collapsed text.

**This is evidence. It is not an exemption, and the system does not treat it as one.**

A zone can take every URL and every number from the operator's input and still be pure synthetic prose. "Carbon neutral since 2019, and not slowing down" invents no fact, cites no invented link, contains no ungrounded number, and a model still wrote that sentence. New copy alters the semantics of the input, so the exemption does not reach it. That is why:

- the default is `generated`, in every case where the comparison cannot be made with certainty;
- the comparison is deliberately strict, and every one of its known failure modes fails towards `generated` (a string the model reflowed or re-punctuated reads as generated; so does a quoted string whose input copy lives inside a JSON-encoded field);
- `verbatim-from-input` requires **every** displayed string to match, not most of them.

The narrow case the evidence actually supports is a zone that reorders and re-presents pinned content verbatim. Whether that case reaches the Art. 50(2) exemption is the provider's call, on their own configuration, with their own counsel. The system hands them the fact; it never draws the conclusion, and the marking does not disappear on its own when the value is `verbatim-from-input`.

## Art. 50(4): what the approval covers, honestly

The zone config registry implements draft and approve. An admin edits a zone's configuration, it is saved as a draft, production keeps serving the previously approved version, and an explicit approve promotes it. Every render path reads only approved entries (`get_approved`, `backend/zones/registry.py`).

**What that approval covers**: the configuration. The base prompt, the context prompt, the pinned content, the allowed component types, the component budget, the cache strategy. A named admin identity approved that configuration, and the change is recorded.

**What that approval does not cover**: the text the model then generates from it. Approving a prompt is not reviewing an output. The same approved configuration produces different copy on every cold generation, and no human sees any of it before it reaches a page.

Presenting the first as the second would be the single most damaging sentence this document could contain, so it is stated the other way round: **the registry is human control over the configuration, and there is no human-in-the-loop review of generated text in this system.** The audit trail records what was shown, after it was shown.

If a deployment falls under Art. 50(4) and intends to rely on the human review exemption, that review has to exist outside GenUI, on the generated text, with a natural person holding editorial responsibility. The mechanisms that make that possible with what is here today: pin the text that must be exact (pinned content is operator-authored and is enforced into the output, `deploy/OUTPUT-GUARANTEES.md` row 5), or gate publication in the host application. Neither is automatic, and neither is claimed to be.

## Use boundaries: where this system must not be wired

GenUI curates presentation. It selects, orders and phrases what is shown in a band of a page. It does not decide prices, eligibility, coverage, hiring or creditworthiness, and it has no mechanism that would make it safe to.

Wiring its output into one of those decisions moves the resulting system into Annex III, and the regime changes entirely: technical documentation (Art. 11), risk management (Art. 9), data governance (Art. 10), human oversight (Art. 14), and for the deployer a fundamental rights impact assessment (Art. 27). Nothing in this repository is built for that regime, and nothing in this document should be read as support for it.

The Annex III points the target verticals actually come near:

| Annex III point | The realistic way a deployment drifts into it | What is here that helps | What is not here |
| --- | --- | --- | --- |
| **4(a)** recruitment: targeted job advertisements, filtering applications, evaluating candidates | An enterprise portal renders a "jobs for you" zone whose selection is driven by the visitor's profile. Targeted placement of job advertisements is named in the point. | The segment is a deterministic function of coarse dimensions, computed with no model in the loop, and is logged in clear text in the audit trail with what was shown: an assessment can read what drove a placement. `compute_segment` (`backend/segmentation/segmenter.py`); audit `summarize_shown_components` (`backend/utils/audit.py`) | No mechanism prevents an operator from feeding a candidate-scoring signal into `pageMetadata` or the profile. The dimensions are fixed, the values in them are the host's. |
| **5(b)** creditworthiness evaluation and credit scoring | A banking portal renders offers whose composition is a function of a profile that already encodes a risk signal, and the zone becomes the visible face of a scoring decision. | Numbers displayed as content must trace verbatim to the input (`NumericGuard`, `backend/utils/numeric_guard.py`), so the model cannot invent a rate or a limit. Per-tenant banned terms are enforced post-generation (`effective_policy`, `backend/utils/content_policy_store.py`). | Neither of those stops an operator from computing the score elsewhere and passing it in. The guard proves the number came from the input; it says nothing about how the input was produced. |
| **5(c)** risk assessment and pricing in life and health insurance | The insurance vertical this deployment model targets. A "your quote" zone that renders a premium derived from the visitor is pricing, not presentation. | Same two mechanisms as above, plus pinned content, which is the supported way to put an exact figure on a page: it is operator-authored and enforced into the output rather than generated. | No mechanism refuses to render a price. The boundary here is a deployment decision, not a code path. |

**Art. 5, prohibited practices.** Purposefully manipulative or deceptive techniques, and exploitation of vulnerabilities due to age, disability or **a specific social or economic situation**, that materially distort behaviour and cause significant harm, are prohibited outright, not merely regulated.

What is here that helps: the segmentation dimensions are **fixed and inspectable**, not learned. There are four of them, and their names are in the source: role, interests, user type, engagement bucket (`compute_segment`, `backend/segmentation/segmenter.py`). None of them is age, disability or socioeconomic status, no model chooses them, and the resulting key is human-readable and logged (`role=developer|int=ai+sustainability|eng=high`). Per-tenant content policy blocks named terms post-generation. The audit trail records what was shown to whom.

What is not here, stated plainly: **the values inside those dimensions are host-supplied free text.** `role`, `interests` and `userType` come from the profile the host writes, and `pageMetadata` is an open dictionary. An operator who writes `role: "over-75"` or `interests: {"debt-relief": ...}` has built a vulnerability-based segmentation, and no code in this repository will notice or refuse. The fixed dimensions bound the *shape* of the segmentation, never its content. There is no protected-attribute detector, and adding one would be a claim this project cannot honour: it would have to be semantic, and semantic detection is exactly what `deploy/OUTPUT-GUARANTEES.md` refuses to promise elsewhere.

## Honest limits

- **Nothing here is signed.** The marking is a declaration, and anyone who controls the response can strip it. C2PA 2.4 can carry a manifest in HTML and defines a `c2pa.ai-disclosure` assertion, which would be the stronger answer, and it is deliberately not implemented: a manifest is worth exactly what its certificate chain is worth, which means a signing identity, key custody and a revocation story, and those belong to the operator's infrastructure rather than to a package that ships as source. The block and the JSON-LD are shaped so a signature can be attached later without moving them. The Code of Practice on marking and labelling of AI-generated content does not mandate a specific technology; it asks for solutions that are effective, interoperable, robust and reliable as far as technically feasible.
- **The provenance check is textual, not semantic.** It proves a string appears verbatim in the input. It cannot prove the wording is the operator's in any deeper sense, and it is wrong only in the direction of over-reporting `generated`.
- **The visible notice can be turned off.** `disclosure={false}` on a zone, `disclosureEnabled: "off"` in a theme, or `GENUI_DISCLOSURE_OFF=1` deployment-wide. The first two keep the machine-readable markup; the third removes everything. All three are deliberate acts by the operator, and the third is logged at every startup, but the library does not and cannot prevent them.
- **There is no human review of generated text**, as stated in the Art. 50(4) section. The registry approves configuration.
- **The use boundaries above are documentation, not enforcement.** No code path refuses to render a price, a score or a job advertisement. Where the boundary is a deployment decision rather than a mechanism, this document says so rather than implying a guard that does not exist.
- **This document covers Art. 50 and the boundaries around it.** It does not address the GPAI obligations of Chapter V, which fall on the provider of the model plugged in through BYOK, not on this system.

## How to re-verify this document

```bash
# The mechanisms above, with their tests:
cd backend && python3 -m unittest discover -s tests

# The references in this file still point at symbols that exist:
cd backend && python3 -m unittest tests.test_deploy_docs -v

# The running deployment's posture matches what this document describes:
cd deploy && ./posture.sh

# Frontend markup and notice:
cd frontend && npm test
```

Related: [OUTPUT-GUARANTEES.md](OUTPUT-GUARANTEES.md) (what is enforced on generated content), [TENANT-ISOLATION.md](TENANT-ISOLATION.md) (the data boundary between tenants), [GDPR.md](GDPR.md) (processing, lawful basis, data subject rights, transfers).
