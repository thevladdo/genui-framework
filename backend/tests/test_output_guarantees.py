"""
S4 output guarantees: numeric grounding + per-tenant content policy.

"Never invent numbers" in the system prompt is an instruction, not a
guarantee: it shifts probability, it bounds nothing. The URL guard is the
model to follow — check the OUTPUT against a whitelist built from the
INPUT, after generation, on every path. These tests pin that extension:

- NumericGuard: numbers displayed AS the content (stats_banner values,
  pricing prices, chart points) must trace to a number present in the
  input; ungrounded ones are removed and reported.
- ContentPolicy: per-tenant banned terms are enforced post-generation
  (component dropped, chat text redacted), outcome in meta.
- The chain applies on BOTH zone paths (sync + SSE) and on /query —
  whose text_response also gets the URL-guard treatment it was missing.
"""

import asyncio
import json
import unittest

from utils.numeric_guard import NumericGuard, extract_numbers
from utils.content_policy import ContentPolicy, ContentPolicyError, policy_for

try:  # app-level deps: available in the backend venv, not in the shell python
    from agents.zone_agent import ZoneAgent, ZoneRenderRequest
    from agents.response_agent import ResponseAgent
    from config import settings
    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False

try:  # fastapi-level deps (router helpers)
    from api.zone_router import _payload_from_result
    HAVE_API_DEPS = True
except ImportError:
    HAVE_API_DEPS = False



# NumericGuard (pure)
class TestNumericGuard(unittest.TestCase):
    def _guard(self, *texts):
        guard = NumericGuard()
        for text in texts:
            guard.allow_from_text(text)
        return guard

    def test_extracts_and_normalizes_input_numbers(self):
        numbers = extract_numbers("10,000 customers in 24 countries, 99.9% uptime")
        self.assertIn("10000", numbers)
        self.assertIn("24", numbers)
        self.assertIn("99.9", numbers)

    def test_ungrounded_stat_is_removed_and_reported(self):
        guard = self._guard("We serve 120 countries")
        components = [{"type": "stats_banner", "data": {"stats": [
            {"value": "120", "label": "Countries"},
            {"value": "98%", "label": "Satisfaction"},
        ]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual([s["value"] for s in kept[0]["data"]["stats"]], ["120"])
        self.assertEqual(removed, ["98%"])

    def test_component_dropped_when_no_stat_survives(self):
        guard = self._guard("no digits here")
        components = [{"type": "stats_banner",
                       "data": {"stats": [{"value": "42", "label": "x"}]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(kept, [])
        self.assertEqual(removed, ["42"])

    def test_value_without_digits_is_kept(self):
        guard = self._guard("nothing numeric at all")
        components = [{"type": "stats_banner",
                       "data": {"stats": [{"value": "Free", "label": "Tier"}]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])

    def test_separator_formatting_is_tolerated(self):
        guard = self._guard("over 1200 integrations")
        components = [{"type": "stats_banner",
                       "data": {"stats": [{"value": "1,200+", "label": "Integrations"}]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])

    def test_magnitude_conversion_is_not_attempted(self):
        # Honest limit, pinned: "10M" does NOT trace to "10,000,000".
        guard = self._guard("10,000,000 requests")
        components = [{"type": "stats_banner",
                       "data": {"stats": [{"value": "10M", "label": "Requests"}]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(kept, [])
        self.assertEqual(removed, ["10M"])

    def test_invented_price_drops_the_plan(self):
        guard = self._guard("Starter is $29/month, Scale is $99/month")
        components = [{"type": "pricing_cards", "data": {"variant": "compact", "plans": [
            {"name": "Starter", "price": "$29"},
            {"name": "Enterprise", "price": "$499"},
        ]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual([p["name"] for p in kept[0]["data"]["plans"]], ["Starter"])
        self.assertEqual(removed, ["$499"])

    def test_chart_with_invented_point_is_dropped_whole(self):
        # A series missing one bar misleads: one invented point kills the chart
        guard = self._guard("Q1 40, Q2 60")
        components = [{"type": "chart", "data": {"chart_type": "bar", "data": [
            {"label": "Q1", "value": 40},
            {"label": "Q2", "value": 60},
            {"label": "Q3", "value": 95},
        ]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(kept, [])
        self.assertEqual(removed, ["95"])

    def test_prose_numbers_are_not_checked(self):
        # Descriptions/labels/text stay best-effort by design: stripping
        # digits from sentences would mangle legitimate prose
        guard = self._guard("nothing numeric")
        components = [{"type": "text", "data": {"content": "Founded in 2001, we ship daily."}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])

    def test_disabled_guard_keeps_everything(self):
        guard = NumericGuard(enforce=False)
        components = [{"type": "stats_banner",
                       "data": {"stats": [{"value": "42", "label": "x"}]}}]
        kept, removed = guard.sanitize_components(components)
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])



# ContentPolicy (pure)
class TestContentPolicy(unittest.TestCase):
    def test_word_boundary_case_insensitive(self):
        policy = ContentPolicy(["Crypto"])
        self.assertEqual(policy.matches("Invest in CRYPTO today"), ["Crypto"])
        self.assertEqual(policy.matches("a cryptography lecture"), [])

    def test_component_with_banned_term_is_dropped(self):
        policy = ContentPolicy(["guaranteed returns"])
        components = [
            {"type": "text", "data": {"content": "A safe product"}},
            {"type": "bento", "data": {"cards": [
                {"title": "Guaranteed RETURNS!", "description": "x"}]}},
        ]
        kept, violations = policy.sanitize_components(components)
        self.assertEqual([c["type"] for c in kept], ["text"])
        self.assertEqual(violations, ["guaranteed returns"])

    def test_redact_text(self):
        policy = ContentPolicy(["miracle cure"])
        text, matched = policy.redact("Try our Miracle Cure now")
        self.assertNotIn("miracle cure", text.lower())
        self.assertEqual(matched, ["miracle cure"])

    def test_policy_for_merges_star_and_tenant(self):
        raw = json.dumps({
            "*": {"banned_terms": ["spam"]},
            "acme": {"banned_terms": ["rival"]},
        })
        self.assertEqual(policy_for("acme", raw).banned_terms, ["spam", "rival"])
        self.assertEqual(policy_for("globex", raw).banned_terms, ["spam"])
        self.assertFalse(policy_for("acme", ""))

    def test_invalid_config_fails_loudly(self):
        # A typo must never silently disable a compliance feature
        with self.assertRaises(ContentPolicyError):
            policy_for("acme", "{not json")
        with self.assertRaises(ContentPolicyError):
            policy_for("acme", json.dumps({"acme": {"banned_terms": "spam"}}))



# The chain, on every path (venv: app deps required)
class _FakeLLM:
    """Replays a recorded envelope on every completion style."""

    def __init__(self, envelope):
        self._text = json.dumps(envelope)

    async def complete_json(self, system, user, json_schema=None):
        return self._text

    async def complete_json_with_tools(self, system, user, tools=None,
                                       tool_handler=None, **kwargs):
        return self._text

    async def stream_json(self, system, user):
        # Arbitrary split: the stream parser must not care
        yield self._text[:37]
        yield self._text[37:]


class _EmptyStore:
    async def search_async(self, query=None, top_k=None, tenant=None, **kwargs):
        return []


# base_prompt grounds 120 and 99.9; "5M" and the banned term are invented
_ZONE_ENVELOPE = {
    "components": [
        {"type": "stats_banner", "data": {"stats": [
            {"value": "120", "label": "Countries"},
            {"value": "5M", "label": "Users"},
        ]}},
        {"type": "text", "data": {"content": "Deposit now for guaranteed returns."}},
    ],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "test envelope",
    "profile_factors": [],
}


# One piece of information spread over three elements: two CTAs to the
# same place, then a card repeating the primary CTA verbatim
_REDUNDANT_ENVELOPE = {
    "components": [
        {"type": "hero_banner", "data": {
            "variant": "centered",
            "headline": "Build faster with a clearer workflow",
            "primary_cta": {"label": "See pricing", "url": "https://example.com/pricing"},
            "secondary_cta": {"label": "Explore", "url": "https://example.com/pricing"},
        }},
        {"type": "bento", "data": {"cards": [
            {"title": "See pricing", "description": "Compare plans and pick the right fit.",
             "link": "https://example.com/pricing"},
        ], "columns": 1}},
    ],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "redundant envelope",
    "profile_factors": [],
}


# The pinned link used ONCE, as the hero's single CTA: what the prompt asks for
_HERO_CTA_ENVELOPE = {
    "components": [
        {"type": "hero_banner", "data": {
            "variant": "centered",
            "headline": "Build faster with a clearer workflow",
            "primary_cta": {"label": "See pricing", "url": "https://example.com/pricing"},
        }},
    ],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.9,
    "reasoning": "hero envelope",
    "profile_factors": [],
}


def _zone_request(tenant="acme"):
    return ZoneRenderRequest(
        zone_id="stats-zone",
        base_prompt="Show company proof points. We serve 120 countries with 99.9% uptime.",
        context_prompt=None,
        pinned_content=[],
        preferred_component_type=None,
        max_items=6,
        user_profile=None,
        behavior_data=None,
        current_page="/about",
        page_metadata={},
        tenant=tenant,
    )


def _redundant_request(tenant="acme"):
    # The URL is grounded in the prompt, so the URL guard keeps it. What gets removed here is the repetition.
    return ZoneRenderRequest(
        zone_id="hero-zone",
        base_prompt="Introduce the product. Pricing lives at https://example.com/pricing",
        context_prompt=None,
        pinned_content=[],
        preferred_component_type=None,
        max_items=6,
        user_profile=None,
        behavior_data=None,
        current_page="/",
        page_metadata={},
        tenant=tenant,
    )


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class TestZoneChain(unittest.TestCase):
    def setUp(self):
        for name, value in [
            ("numeric_grounding_enabled", True),
            ("url_whitelist_enabled", True),
            ("content_policy", json.dumps(
                {"acme": {"banned_terms": ["guaranteed returns"]}})),
        ]:
            self.addCleanup(setattr, settings, name, getattr(settings, name))
            setattr(settings, name, value)

    def _agent(self):
        return ZoneAgent(model="test", vector_store=_EmptyStore(),
                         llm_client=_FakeLLM(_ZONE_ENVELOPE))

    def test_sync_path_enforces_grounding_and_policy(self):
        result = asyncio.run(self._agent().render_zone_async(_zone_request()))
        stats_banners = [c for c in result.components if c["type"] == "stats_banner"]
        self.assertEqual(len(stats_banners), 1)
        self.assertEqual(
            [s["value"] for s in stats_banners[0]["data"]["stats"]], ["120"])
        self.assertEqual(result.removed_numbers, ["5M"])
        self.assertFalse([c for c in result.components if c["type"] == "text"])
        self.assertEqual(result.policy_violations, ["guaranteed returns"])

    def test_sse_path_enforces_the_same_chain(self):
        async def collect():
            events = []
            async for event in self._agent().render_zone_stream_async(_zone_request()):
                events.append(event)
            return events

        events = asyncio.run(collect())
        streamed = [e["component"] for e in events if e["type"] == "component"]
        # No invented number and no banned term ever crosses the wire
        self.assertNotIn("5M", json.dumps(streamed))
        self.assertNotIn("guaranteed returns", json.dumps(streamed).lower())
        self.assertEqual(
            [s["value"] for c in streamed if c["type"] == "stats_banner"
             for s in c["data"]["stats"]],
            ["120"])

        result = events[-1]["result"]
        self.assertEqual(result.removed_numbers, ["5M"])
        self.assertEqual(result.policy_violations, ["guaranteed returns"])

    def test_policy_is_per_tenant(self):
        result = asyncio.run(self._agent().render_zone_async(_zone_request(tenant="globex")))
        self.assertTrue([c for c in result.components if c["type"] == "text"])
        self.assertEqual(result.policy_violations, [])

    def test_sync_path_removes_a_zone_that_says_the_same_thing_twice(self):
        agent = ZoneAgent(model="test", vector_store=_EmptyStore(),
                          llm_client=_FakeLLM(_REDUNDANT_ENVELOPE))
        result = asyncio.run(agent.render_zone_async(_redundant_request()))

        # The hero keeps obe cta, and the card that only echoed it is gone
        self.assertEqual([c["type"] for c in result.components], ["hero_banner"])
        hero = result.components[0]["data"]
        self.assertIn("primary_cta", hero)
        self.assertNotIn("secondary_cta", hero)
        self.assertEqual(len(result.dropped_components), 2)

    def test_sse_path_removes_the_same_redundancy(self):
        agent = ZoneAgent(model="test", vector_store=_EmptyStore(),
                          llm_client=_FakeLLM(_REDUNDANT_ENVELOPE))

        async def collect():
            return [e async for e in agent.render_zone_stream_async(_redundant_request())]

        events = asyncio.run(collect())
        streamed = [e["component"] for e in events if e["type"] == "component"]
        self.assertEqual([c["type"] for c in streamed], ["hero_banner"])
        self.assertNotIn("secondary_cta", streamed[0]["data"])

    def test_pinned_used_as_a_hero_cta_is_not_appended_again(self):
        agent = ZoneAgent(model="test", vector_store=_EmptyStore(),
                          llm_client=_FakeLLM(_HERO_CTA_ENVELOPE))
        request = _redundant_request()
        request.pinned_content = [
            {"title": "See pricing", "url": "https://example.com/pricing"}
        ]
        result = asyncio.run(agent.render_zone_async(request))

        self.assertEqual([c["type"] for c in result.components], ["hero_banner"])
        self.assertEqual(result.pinned_content_included, ["https://example.com/pricing"])

    def test_pinned_still_appended_when_the_output_ignores_it(self):
        agent = ZoneAgent(model="test", vector_store=_EmptyStore(),
                          llm_client=_FakeLLM(_HERO_CTA_ENVELOPE))
        request = _redundant_request()
        request.pinned_content = [
            {"title": "Security whitepaper", "url": "https://example.com/security"}
        ]
        result = asyncio.run(agent.render_zone_async(request))

        self.assertEqual([c["type"] for c in result.components], ["hero_banner", "bento"])
        cards = result.components[1]["data"]["cards"]
        self.assertEqual([c["title"] for c in cards], ["Security whitepaper"])

    @unittest.skipUnless(HAVE_API_DEPS, "requires fastapi (backend venv)")
    def test_outcome_lands_in_meta_sanitization(self):
        result = asyncio.run(self._agent().render_zone_async(_zone_request()))
        sanitization = _payload_from_result(result)["meta"]["sanitization"]
        self.assertEqual(sanitization["removed_numbers"], ["5M"])
        self.assertEqual(sanitization["policy_violations"], ["guaranteed returns"])


_QUERY_ENVELOPE = {
    "text_response": (
        "See the [docs](https://ok.example/docs) or this "
        "[limited deal](https://evil.example/phish). "
        "Deposit now for guaranteed returns."
    ),
    "components": [
        {"type": "stats_banner", "data": {"stats": [
            {"value": "99.9", "label": "Uptime"},
            {"value": "5M", "label": "Users"},
        ]}},
    ],
    "sources": [],
    "confidence": 0.7,
    "suggested_actions": [],
}


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class TestQueryChain(unittest.TestCase):
    def setUp(self):
        for name, value in [
            ("numeric_grounding_enabled", True),
            ("url_whitelist_enabled", True),
            ("content_policy", json.dumps(
                {"acme": {"banned_terms": ["guaranteed returns"]}})),
        ]:
            self.addCleanup(setattr, settings, name, getattr(settings, name))
            setattr(settings, name, value)

    def _response(self, tenant="acme"):
        agent = ResponseAgent(model="test", vector_store=_EmptyStore(),
                              llm_client=_FakeLLM(_QUERY_ENVELOPE))
        return asyncio.run(agent.process_query_async(
            "Is https://ok.example/docs right about the 99.9 uptime?",
            tenant=tenant,
        ))

    def test_text_response_gets_the_url_guard_treatment(self):
        # The forgotten path: chat prose was never link-stripped
        response = self._response()
        self.assertIn("https://ok.example/docs", response.text_response)
        self.assertNotIn("evil.example", response.text_response)
        self.assertIn("limited deal", response.text_response)  # text survives, link dies

    def test_text_response_banned_term_is_redacted(self):
        response = self._response()
        self.assertNotIn("guaranteed returns", response.text_response.lower())
        self.assertIn("guaranteed returns", response.sanitization["policy_violations"])

    def test_component_numbers_are_grounded(self):
        response = self._response()
        stats = [s for c in response.components if c.type == "stats_banner"
                 for s in c.data["stats"]]
        self.assertEqual([s["value"] for s in stats], ["99.9"])
        self.assertEqual(response.sanitization["removed_numbers"], ["5M"])

    def test_policy_is_per_tenant(self):
        response = self._response(tenant="globex")
        self.assertIn("guaranteed returns", response.text_response.lower())
        self.assertEqual(response.sanitization["policy_violations"], [])


if __name__ == "__main__":
    unittest.main()
