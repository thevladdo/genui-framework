"""
Per-role routing seen from the app: /ready names the role that cannot be called, and the model that answered reaches the disclosure and the render audit.
Needs the backend venv (agents, FastAPI).
"""

import asyncio
import json
import unittest
from unittest import mock

import metrics.ops as ops_module
from llm.factory import RoutedChatClient
from llm.routing import Role, Route, Target
from metrics.ops import OpsMetrics

from memory_stores import use_memory_stores

try:
    from fastapi.testclient import TestClient

    import api.main as main
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from agents.response_agent import ResponseAgent
    from agents.zone_agent import ZoneAgent, ZoneRenderRequest as AgentZoneRequest
    from auth.keys import AuthContext
    from config import settings

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def setUpModule():
    use_memory_stores()


_ENVELOPE = {
    "components": [{"type": "text", "data": {"content": "A sentence the model wrote."}}],
    "personalization_applied": False,
    "confidence": 0.8,
    "reasoning": "r",
    "profile_factors": [],
}

_CHAT_ENVELOPE = {
    "text_response": "An answer.",
    "components": [],
    "sources": [],
    "confidence": 0.7,
    "suggested_actions": [],
}


class _Down:
    model = "big-model"
    prompt_cache = "explicit"

    async def complete_json(self, *args, **kwargs):
        raise RuntimeError("provider down")

    async def complete_json_with_tools(self, *args, **kwargs):
        raise RuntimeError("provider down")

    async def stream_json(self, system, user):
        raise RuntimeError("provider down")
        yield  # pragma: no cover


class _Replays:
    model = "small-model"
    prompt_cache = "prefix"

    def __init__(self, envelope):
        self._text = json.dumps(envelope)

    async def complete_json(self, *args, **kwargs):
        return self._text

    async def complete_json_with_tools(self, *args, **kwargs):
        return self._text

    async def stream_json(self, system, user):
        yield self._text[:10]
        yield self._text[10:]


class _EmptyStore:
    async def search_async(self, *args, **kwargs):
        return []


def _routed(role, envelope):
    route = Route(
        role,
        Target("anthropic", "big-model", "k", None),
        Target("openai", "small-model", None, "http://vllm:8000/v1"),
        f"LLM_{role.value.upper()}",
    )
    return RoutedChatClient(route, _Down(), _Replays(envelope))


def _request():
    return AgentZoneRequest(
        zone_id="hero", base_prompt="Write something.", context_prompt=None,
        pinned_content=[], preferred_component_type=None, max_items=6,
        user_profile=None, behavior_data=None, current_page="/",
        page_metadata={}, tenant="acme",
    )


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class AppTestCase(unittest.TestCase):
    def setUp(self):
        saved_ops = ops_module._ops
        ops_module._ops = OpsMetrics(redis_url=None)
        self.addCleanup(setattr, ops_module, "_ops", saved_ops)
        for name, value in [("genui_disclosure_off", False), ("disclosure_expose_model", True)]:
            self.addCleanup(setattr, settings, name, getattr(settings, name))
            setattr(settings, name, value)


class TestReadyPerRole(AppTestCase):
    def test_role_on_a_provider_without_key_fails_ready_naming_role_and_variable(self):
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", "sk-test"), \
             mock.patch.object(settings, "anthropic_api_key", None), \
             mock.patch.object(settings, "llm_zone", "anthropic:claude-big"):
            response = TestClient(main.app).get("/ready")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["llm"], "unconfigured")
        self.assertEqual(body["llm_unconfigured"], ["zone (LLM_ZONE)"])
        self.assertNotIn("ANTHROPIC", response.text)

    def test_two_roles_on_two_configured_providers_are_ready(self):
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", None), \
             mock.patch.object(settings, "openai_base_url", "http://vllm.internal:8000/v1"), \
             mock.patch.object(settings, "anthropic_api_key", "sk-ant"), \
             mock.patch.object(settings, "llm_zone", "anthropic:claude-big"), \
             mock.patch("llm.routing.importlib.util.find_spec", return_value=object()):
            response = TestClient(main.app).get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["llm_unconfigured"], [])


class TestReadyAfterTheKeyCheck(AppTestCase):
    def test_a_rejected_key_fails_ready_without_saying_why(self):
        from llm import credentials

        self.addCleanup(setattr, credentials, "_problems", credentials._problems)
        credentials._problems = [("zone, chat (OPENAI_API_KEY)", "openai rejected the key")]
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", "sk-looks-fine"), \
             mock.patch.object(settings, "openai_base_url", None):
            response = TestClient(main.app).get("/ready")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["llm"], "rejected")
        self.assertEqual(body["llm_unconfigured"], ["zone, chat (OPENAI_API_KEY)"])
        self.assertNotIn("rejected the key", response.text)


class TestEmbeddingKeyIsDegradationNotOutage(AppTestCase):
    def test_a_rejected_embedding_key_degrades_health_and_keeps_ready(self):
        from llm import credentials

        self.addCleanup(setattr, credentials, "_problems", credentials._problems)
        credentials._problems = [("embeddings (EMBEDDING_API_KEY)", "openai rejected the key")]
        with mock.patch.object(settings, "llm_provider", "openai"), \
             mock.patch.object(settings, "openai_api_key", "sk-good"), \
             mock.patch.object(settings, "openai_base_url", None):
            client = TestClient(main.app)
            ready, health = client.get("/ready"), client.get("/health").json()
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["llm"], "configured")
        self.assertEqual(health["embeddings"], "rejected")
        self.assertEqual(health["status"], "degraded")


class TestAnsweredModelReachesTheMarking(AppTestCase):
    def test_zone_render_from_the_fallback_names_the_fallback(self):
        agent = ZoneAgent(vector_store=_EmptyStore(), llm_client=_routed(Role.ZONE, _ENVELOPE))
        result = asyncio.run(agent.render_zone_async(_request()))
        self.assertTrue(result.disclosure["ai_generated"])
        self.assertEqual(result.disclosure["model"], "small-model")
        self.assertEqual(result.model, "small-model")

    def test_streamed_zone_render_from_the_fallback_names_the_fallback(self):
        agent = ZoneAgent(vector_store=_EmptyStore(), llm_client=_routed(Role.ZONE, _ENVELOPE))

        async def collect():
            return [e async for e in agent.render_zone_stream_async(_request())]

        complete = [e for e in asyncio.run(collect()) if e["type"] == "complete"][-1]
        self.assertEqual(complete["result"].disclosure["model"], "small-model")
        self.assertEqual(complete["result"].model, "small-model")

    def test_chat_answer_from_the_fallback_names_the_fallback(self):
        agent = ResponseAgent(vector_store=_EmptyStore(), llm_client=_routed(Role.CHAT, _CHAT_ENVELOPE))
        response = asyncio.run(agent.process_query_async("what?"))
        self.assertTrue(response.disclosure["ai_generated"])
        self.assertEqual(response.disclosure["model"], "small-model")


class TestRenderAuditCarriesTheModel(AppTestCase):
    def test_audit_has_the_model_and_the_response_does_not(self):
        settings.disclosure_expose_model = False
        agent = ZoneAgent(vector_store=_EmptyStore(), llm_client=_routed(Role.ZONE, _ENVELOPE))
        payload = zone_router._payload_from_result(asyncio.run(agent.render_zone_async(_request())))

        lines = []

        class _Audit:
            def log(self, event, tenant, user_id=None, **fields):
                lines.append(fields)

        saved = auth_deps._audit_logger
        auth_deps._audit_logger = _Audit()
        self.addCleanup(setattr, auth_deps, "_audit_logger", saved)
        auth = AuthContext(tenant="acme", is_admin=False, key_fingerprint="fp")
        request = zone_router.ZoneRenderRequest(zone_id="hero", base_prompt="x")
        zone_router._audit_render(auth, request, payload, {"status": "miss"})

        self.assertEqual(lines[0]["model"], "small-model")
        served = zone_router._build_response("hero", payload, {"status": "miss"}).model_dump_json()
        self.assertNotIn("small-model", served)

    def test_pinned_only_fallback_render_has_no_model(self):
        class _AllDown(_Down):
            pass

        route = Route(Role.ZONE, Target("anthropic", "big-model", "k", None), None, "LLM_ZONE")
        agent = ZoneAgent(vector_store=_EmptyStore(), llm_client=RoutedChatClient(route, _AllDown()))
        result = asyncio.run(agent.render_zone_async(_request()))
        self.assertFalse(result.disclosure["ai_generated"])
        self.assertIsNone(result.model)


if __name__ == "__main__":
    unittest.main()
