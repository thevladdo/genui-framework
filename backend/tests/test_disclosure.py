"""
Tests for the AI content disclosure.

The rule the tests defend: a marking that lies is worse than no marking.
So every path that serves a payload carries the block, the block says
"not generated" exactly when no model wrote the content, the timestamp
is the one of the generation and not of the delivery, and the
provenance falls back to "generated" whenever the verbatim case is not
provable.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The router/agent tests need fastapi (backend venv); they skip in the
pure-stdlib shell interpreter.
"""

import asyncio
import json
import unittest

from utils.disclosure import (
    PROVENANCE_GENERATED,
    PROVENANCE_NONE,
    PROVENANCE_VERBATIM,
    content_provenance,
    disclosure_block,
)

try:
    from agents.response_agent import ResponseAgent
    from agents.zone_agent import ZoneAgent, ZoneRenderRequest as AgentZoneRequest
    from api.zone_router import ZoneRenderRequest as ApiZoneRequest
    import api.zone_router as zone_router
    from auth.keys import AuthContext
    from config import settings
    from utils.rate_limit import RateLimiter
    from utils.zone_cache import ZoneRenderCache
    import auth.dependencies as auth_deps

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


CORPUS = (
    "Our sustainability report is at https://example.com/sustainability. "
    "Carbon neutral since 2019."
)


class TestContentProvenance(unittest.TestCase):
    """Same input, two outputs: only one of them is the input."""

    def test_verbatim_output_is_recognized(self):
        components = [{
            "type": "bento",
            "data": {
                "cards": [{
                    "title": "Our sustainability report",
                    "link": "https://example.com/sustainability",
                }],
                "columns": 1,
            },
        }]
        self.assertEqual(
            content_provenance(components, CORPUS), PROVENANCE_VERBATIM
        )

    def test_original_prose_is_generated_even_with_grounded_facts(self):
        """
        Every URL comes from the input, every number comes from the
        input, and the sentence is still written by the model. The
        guards prove nothing was invented, never that nothing was
        written.
        """
        components = [{
            "type": "hero_banner",
            "data": {
                "variant": "centered",
                "headline": "Carbon neutral since 2019, and not slowing down",
                "primary_cta": {
                    "label": "Read the report",
                    "url": "https://example.com/sustainability",
                },
            },
        }]
        self.assertEqual(
            content_provenance(components, CORPUS), PROVENANCE_GENERATED
        )

    def test_one_unmatched_string_is_enough(self):
        components = [{
            "type": "bento",
            "data": {"cards": [
                {"title": "Our sustainability report"},
                {"title": "Why it matters to you"},
            ]},
        }]
        self.assertEqual(
            content_provenance(components, CORPUS), PROVENANCE_GENERATED
        )

    def test_empty_render_proves_nothing(self):
        self.assertEqual(content_provenance([], CORPUS), PROVENANCE_GENERATED)

    def test_case_and_whitespace_tolerated_nothing_else(self):
        components = [{"data": {"title": "  OUR   sustainability\nreport "}}]
        self.assertEqual(
            content_provenance(components, CORPUS), PROVENANCE_VERBATIM
        )


class TestDisclosureBlock(unittest.TestCase):
    def test_default_hides_the_model_name(self):
        block = disclosure_block(True, PROVENANCE_GENERATED, model="gpt-4o-mini")
        self.assertTrue(block["ai_generated"])
        self.assertEqual(block["provenance"], PROVENANCE_GENERATED)
        self.assertEqual(block["system"], "genui")
        self.assertNotIn("model", block)

    def test_model_exposed_on_request(self):
        block = disclosure_block(
            True, PROVENANCE_GENERATED, model="gpt-4o-mini", expose_model=True
        )
        self.assertEqual(block["model"], "gpt-4o-mini")

    def test_not_generated_forces_the_provenance(self):
        block = disclosure_block(False, PROVENANCE_VERBATIM)
        self.assertFalse(block["ai_generated"])
        self.assertEqual(block["provenance"], PROVENANCE_NONE)

    def test_disabled_emits_nothing(self):
        self.assertIsNone(
            disclosure_block(True, PROVENANCE_GENERATED, enabled=False)
        )

    def test_generation_timestamp_is_kept_verbatim(self):
        block = disclosure_block(
            True, PROVENANCE_GENERATED, generated_at="2026-07-27T09:00:00+00:00"
        )
        self.assertEqual(block["generated_at"], "2026-07-27T09:00:00+00:00")


# Agent and router paths (venv: app deps required)
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
        yield self._text[:29]
        yield self._text[29:]


class _BrokenLLM:
    """Every call fails: the agent must fall back without the model."""

    async def complete_json(self, system, user, json_schema=None):
        raise RuntimeError("provider down")

    async def complete_json_with_tools(self, system, user, tools=None,
                                       tool_handler=None, **kwargs):
        raise RuntimeError("provider down")

    async def stream_json(self, system, user):
        raise RuntimeError("provider down")
        yield  # pragma: no cover - generator marker


class _EmptyStore:
    async def search_async(self, query=None, top_k=None, tenant=None, **kwargs):
        return []


_PROSE_ENVELOPE = {
    "components": [{
        "type": "text",
        "data": {"content": "A sentence the model wrote by itself."},
    }],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "test envelope",
    "profile_factors": [],
}

_VERBATIM_ENVELOPE = {
    "components": [{
        "type": "bento",
        "data": {"cards": [{
            "title": "Our sustainability report",
            "link": "https://example.com/sustainability",
        }], "columns": 1},
    }],
    "pinned_included": [],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "test envelope",
    "profile_factors": [],
}


def _agent_request():
    return AgentZoneRequest(
        zone_id="zone-1",
        base_prompt=CORPUS,
        context_prompt=None,
        pinned_content=[{
            "type": "link",
            "url": "https://example.com/sustainability",
            "title": "Our sustainability report",
        }],
        preferred_component_type=None,
        max_items=6,
        user_profile=None,
        behavior_data=None,
        current_page="/",
        page_metadata={},
        tenant="acme",
    )


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class TestAgentDisclosure(unittest.TestCase):
    def setUp(self):
        for name, value in [
            ("genui_disclosure_off", False),
            ("disclosure_expose_model", False),
        ]:
            self.addCleanup(setattr, settings, name, getattr(settings, name))
            setattr(settings, name, value)

    def _agent(self, envelope):
        return ZoneAgent(model="test-model", vector_store=_EmptyStore(),
                         llm_client=_FakeLLM(envelope))

    def test_sync_render_is_marked_generated(self):
        result = asyncio.run(self._agent(_PROSE_ENVELOPE).render_zone_async(_agent_request()))
        self.assertTrue(result.disclosure["ai_generated"])
        self.assertEqual(result.disclosure["provenance"], PROVENANCE_GENERATED)
        self.assertTrue(result.disclosure["generated_at"])

    def test_sync_render_of_pure_input_is_marked_verbatim(self):
        result = asyncio.run(
            self._agent(_VERBATIM_ENVELOPE).render_zone_async(_agent_request())
        )
        self.assertTrue(result.disclosure["ai_generated"])
        self.assertEqual(result.disclosure["provenance"], PROVENANCE_VERBATIM)

    def test_stream_complete_carries_the_same_marking(self):
        async def collect(envelope):
            events = []
            async for event in self._agent(envelope).render_zone_stream_async(
                _agent_request()
            ):
                events.append(event)
            return events

        for envelope, expected in [
            (_PROSE_ENVELOPE, PROVENANCE_GENERATED),
            (_VERBATIM_ENVELOPE, PROVENANCE_VERBATIM),
        ]:
            events = asyncio.run(collect(envelope))
            complete = [e for e in events if e["type"] == "complete"][-1]
            disclosure = complete["result"].disclosure
            self.assertTrue(disclosure["ai_generated"])
            self.assertEqual(disclosure["provenance"], expected)

    def test_fallback_render_says_it_is_not_generated(self):
        """No model ran: the cards are the operator's pinned content."""
        agent = ZoneAgent(model="test-model", vector_store=_EmptyStore(),
                          llm_client=_BrokenLLM())
        result = asyncio.run(agent.render_zone_async(_agent_request()))
        self.assertFalse(result.disclosure["ai_generated"])
        self.assertEqual(result.disclosure["provenance"], PROVENANCE_NONE)

    def test_stream_fallback_says_it_is_not_generated(self):
        async def collect():
            agent = ZoneAgent(model="test-model", vector_store=_EmptyStore(),
                              llm_client=_BrokenLLM())
            return [e async for e in agent.render_zone_stream_async(_agent_request())]

        complete = [e for e in asyncio.run(collect()) if e["type"] == "complete"][-1]
        self.assertFalse(complete["result"].disclosure["ai_generated"])

    def test_disclosure_off_emits_no_block(self):
        settings.genui_disclosure_off = True
        result = asyncio.run(self._agent(_PROSE_ENVELOPE).render_zone_async(_agent_request()))
        self.assertIsNone(result.disclosure)

    def test_model_name_only_when_exposed(self):
        settings.disclosure_expose_model = True
        result = asyncio.run(self._agent(_PROSE_ENVELOPE).render_zone_async(_agent_request()))
        self.assertEqual(result.disclosure["model"], "test-model")


_CHAT_ENVELOPE = {
    "text_response": "Here is what the report says, in short.",
    "components": [],
    "sources": [],
    "confidence": 0.7,
    "suggested_actions": [],
}


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class TestChatDisclosure(unittest.TestCase):
    """The chat answer is marked too: it is the other served surface."""

    def setUp(self):
        self.addCleanup(setattr, settings, "genui_disclosure_off",
                        settings.genui_disclosure_off)
        settings.genui_disclosure_off = False

    def _answer(self, llm):
        agent = ResponseAgent(model="test-model", vector_store=_EmptyStore(),
                              llm_client=llm)
        return asyncio.run(agent.process_query_async("what does the report say?"))

    def test_answer_is_marked_generated(self):
        response = self._answer(_FakeLLM(_CHAT_ENVELOPE))
        self.assertTrue(response.disclosure["ai_generated"])
        self.assertEqual(response.disclosure["provenance"], PROVENANCE_GENERATED)

    def test_fallback_answer_says_it_is_not_generated(self):
        response = self._answer(_BrokenLLM())
        self.assertFalse(response.disclosure["ai_generated"])
        self.assertEqual(response.disclosure["provenance"], PROVENANCE_NONE)


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestServingPathsDisclosure(unittest.TestCase):
    """Every way a payload reaches a user carries the marking."""

    @classmethod
    def setUpClass(cls):
        cls.CLIENT = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        cls.ADMIN = AuthContext(tenant="acme", is_admin=True, key_fingerprint="afp")

    def setUp(self):
        self._saved = (
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
            settings.llm_budget_per_hour,
        )
        zone_router._zone_cache = ZoneRenderCache()  # fresh, in-memory
        zone_router._llm_budget = None
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        settings.zone_cache_enabled = True
        settings.holdout_percent = 0.0
        settings.redis_url = None
        settings.llm_budget_per_hour = 0

        self.addCleanup(setattr, settings, "genui_disclosure_off",
                        settings.genui_disclosure_off)
        settings.genui_disclosure_off = False

        # The real payload builder, fed by a stubbed agent: the marking
        # must survive the trip through the cache, not just the agent.
        self._orig_agent = zone_router.get_zone_agent
        agent = ZoneAgent(model="test-model", vector_store=_EmptyStore(),
                          llm_client=_FakeLLM(_PROSE_ENVELOPE))
        zone_router.get_zone_agent = lambda: agent

    def tearDown(self):
        zone_router.get_zone_agent = self._orig_agent
        (
            zone_router._zone_cache,
            zone_router._llm_budget,
            auth_deps._rate_limiter,
            settings.zone_cache_enabled,
            settings.holdout_percent,
            settings.redis_url,
            settings.llm_budget_per_hour,
        ) = self._saved

    def _request(self, zone_id="zone-1", **kwargs):
        return ApiZoneRequest(zone_id=zone_id, base_prompt=CORPUS, **kwargs)

    def _assert_generated(self, meta, path):
        self.assertIn("disclosure", meta, f"{path} serves no disclosure")
        self.assertTrue(meta["disclosure"]["ai_generated"], path)
        self.assertTrue(meta["disclosure"]["generated_at"], path)

    def test_sync_cold_miss_and_cache_hit(self):
        async def scenario():
            first = await zone_router._handle_render(self._request(), self.CLIENT)
            second = await zone_router._handle_render(self._request(), self.CLIENT)
            return first, second

        first, second = asyncio.run(scenario())
        self.assertEqual(first.meta["cache"]["status"], "miss")
        self.assertEqual(second.meta["cache"]["status"], "fresh")
        self._assert_generated(first.meta, "cold miss")
        self._assert_generated(second.meta, "cache hit")

    def test_cache_hit_keeps_the_generation_timestamp(self):
        """
        A cached render is served for the whole stale window: it must
        keep saying when it was generated, not when it was handed out.
        """
        async def scenario():
            first = await zone_router._handle_render(self._request(), self.CLIENT)
            await asyncio.sleep(0.05)
            second = await zone_router._handle_render(self._request(), self.CLIENT)
            return first, second

        first, second = asyncio.run(scenario())
        self.assertEqual(
            first.meta["disclosure"]["generated_at"],
            second.meta["disclosure"]["generated_at"],
        )
        # And it is the moment of the generation, not of this response
        self.assertLess(
            second.meta["disclosure"]["generated_at"], second.rendered_at
        )

    def test_live_bypass(self):
        response = asyncio.run(zone_router._handle_render(
            self._request(cache_strategy="live"), self.ADMIN
        ))
        self.assertEqual(response.meta["cache"]["status"], "bypass")
        self._assert_generated(response.meta, "bypass")

    def test_batch_render(self):
        results = asyncio.run(zone_router.batch_render_zones(
            [self._request("a"), self._request("b")], self.CLIENT, None
        ))
        for entry in results["results"]:
            self.assertTrue(entry["success"], entry)
            self._assert_generated(entry["data"]["meta"], "batch")

    def test_warmup_then_served_from_cache(self):
        async def scenario():
            await zone_router.warmup_zones(
                zone_router.ZoneWarmupRequest(zones=[self._request()]), self.ADMIN
            )
            return await zone_router._handle_render(self._request(), self.CLIENT)

        response = asyncio.run(scenario())
        self.assertEqual(response.meta["cache"]["status"], "fresh")
        self._assert_generated(response.meta, "warmup")

    def test_sse_stream_complete_event(self):
        async def scenario():
            stream = await zone_router.render_zone_stream(self._request(), self.CLIENT, None)
            chunks = []
            async for chunk in stream.body_iterator:
                chunks.append(chunk)
            return "".join(chunks)

        raw = asyncio.run(scenario())
        complete = [
            line for line in raw.splitlines()
            if line.startswith("data: ") and "\"components\"" in line
        ][-1]
        meta = json.loads(complete[len("data: "):])["meta"]
        self._assert_generated(meta, "sse complete")

    def test_disclosure_off_removes_the_block_everywhere(self):
        settings.genui_disclosure_off = True
        response = asyncio.run(zone_router._handle_render(self._request(), self.CLIENT))
        self.assertNotIn("disclosure", response.meta)


if __name__ == "__main__":
    unittest.main()
