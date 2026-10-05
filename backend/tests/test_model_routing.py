"""
Per-role model routing: which provider and model each role calls, the shared clients, the declared fallback, and what reports the model.
Pure stdlib: runs with the shell python as well as in the backend venv.
"""

import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import metrics.ops as ops_module
from llm import factory
from llm.factory import (
    RoutedChatClient,
    answered_model,
    create_llm_client,
    llm_config_problems,
    llm_configured,
)
from llm.routing import LLMConfigError, Role, Route, Target, parse_spec, resolve_route
from metrics.ops import OpsMetrics
from utils.disclosure import PROVENANCE_GENERATED, disclosure_block


def _settings(**overrides):
    base = dict(
        llm_provider="openai",
        openai_api_key="sk-test",
        anthropic_api_key=None,
        google_api_key=None,
        openai_base_url=None,
        response_model="resp-model",
        profile_model="prof-model",
        context_model="ctx-model",
        llm_timeout_seconds=30.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeSDK:
    """Stand-in for the openai/anthropic packages: records every client built."""

    def __init__(self):
        self.built = []
        sdk = self

        class Client:
            def __init__(self, **kwargs):
                sdk.built.append(kwargs)

        self.Client = Client

    def __enter__(self):
        self._saved = {name: sys.modules.get(name) for name in ("openai", "anthropic")}
        sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=self.Client)
        sys.modules["anthropic"] = types.SimpleNamespace(AsyncAnthropic=self.Client)
        factory._clients.clear()
        return self

    def __exit__(self, *exc):
        factory._clients.clear()
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class _ScriptedLLM:
    def __init__(self, model, text=None, error=None, stream_then_fail=False):
        self.model = model
        self.prompt_cache = "prefix"
        self._text, self._error, self._stream_then_fail = text, error, stream_then_fail
        self.calls = 0

    async def complete_json(self, system, user, json_schema=None):
        self.calls += 1
        if self._error:
            raise self._error
        return self._text

    async def stream_json(self, system, user):
        self.calls += 1
        if self._stream_then_fail:
            yield '{"partial'
            raise RuntimeError("dropped mid-stream")
        if self._error:
            raise self._error
        yield self._text


def _route(fallback=True):
    return Route(
        role=Role.ZONE,
        primary=Target("anthropic", "big-model", "sk-a", None),
        fallback=Target("openai", "small-model", None, "http://vllm:8000/v1") if fallback else None,
        variable="LLM_ZONE",
    )


class MetricsTestCase(unittest.TestCase):
    def setUp(self):
        self._saved_ops = ops_module._ops
        self.ops = ops_module._ops = OpsMetrics(redis_url=None)

    def tearDown(self):
        ops_module._ops = self._saved_ops

    def run_and_scrape(self, coro):
        async def go():
            try:
                return await coro
            finally:
                await asyncio.gather(*self.ops.pending_tasks())

        try:
            result = asyncio.run(go())
        except Exception as e:
            result = e
        return result, asyncio.run(self.ops.render_text())


# (a) without per-role configuration every role resolves to today's provider and model

class TestDefaultsUnchanged(unittest.TestCase):
    def test_each_role_keeps_the_global_provider_and_its_historical_model(self):
        settings = _settings()
        expected = {
            Role.ZONE: "resp-model",
            Role.CHAT: "resp-model",
            Role.PROFILE: "prof-model",
            Role.BEHAVIOR: "prof-model",
            Role.SUMMARY: "prof-model",
            Role.CONTEXT: "ctx-model",
        }
        self.assertEqual(set(expected), set(Role))
        for role, model in expected.items():
            route = resolve_route(role, settings)
            self.assertEqual((route.primary.provider, route.primary.model), ("openai", model))
            self.assertEqual(route.primary.api_key, "sk-test")
            self.assertIsNone(route.fallback)

    def test_a_historical_model_with_a_colon_is_still_a_model(self):
        route = resolve_route(Role.PROFILE, _settings(profile_model="qwen3:8b", openai_base_url="http://ollama:11434/v1"))
        self.assertEqual((route.primary.provider, route.primary.model), ("openai", "qwen3:8b"))

    def test_roles_are_a_closed_set(self):
        with self.assertRaises(ValueError):
            resolve_route("render", _settings())


class TestSpecParsing(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_spec("anthropic:claude-x", "openai"), ("anthropic", "claude-x"))
        self.assertEqual(parse_spec("openai:qwen3:8b", "anthropic"), ("openai", "qwen3:8b"))
        self.assertEqual(parse_spec("gpt-4o-mini", "anthropic"), ("anthropic", "gpt-4o-mini"))
        self.assertEqual(parse_spec("Gemini:gemini-2.5-flash", "openai"), ("gemini", "gemini-2.5-flash"))

    def test_a_misspelt_provider_is_an_error_naming_role_and_variable(self):
        with self.assertRaises(LLMConfigError) as caught:
            resolve_route(Role.ZONE, _settings(llm_zone="antropic:claude-x"))
        self.assertIn("zone", str(caught.exception))
        self.assertIn("LLM_ZONE", str(caught.exception))

    def test_a_misspelt_fallback_names_the_fallback_variable(self):
        with self.assertRaises(LLMConfigError) as caught:
            resolve_route(Role.CHAT, _settings(llm_chat_fallback="opanai:gpt"))
        self.assertIn("LLM_CHAT_FALLBACK", str(caught.exception))

    def test_unknown_global_provider_is_an_error_not_openai(self):
        with self.assertRaises(LLMConfigError):
            resolve_route(Role.ZONE, _settings(llm_provider="hal9000"))


# (b) one role on anthropic and one on a local endpoint: different clients; equal roles share one

class TestFactory(MetricsTestCase):
    def test_roles_on_different_providers_get_different_clients_and_equal_ones_share(self):
        settings = _settings(
            anthropic_api_key="sk-ant",
            openai_api_key=None,
            openai_base_url="http://vllm.internal:8000/v1",
            llm_zone="anthropic:claude-big",
            llm_chat="anthropic:claude-big",
            llm_profile="openai:qwen3:8b",
        )
        with _FakeSDK() as sdk:
            zone = create_llm_client(Role.ZONE, settings)
            chat = create_llm_client(Role.CHAT, settings)
            profile = create_llm_client(Role.PROFILE, settings)

            self.assertEqual(type(zone._primary).__name__, "AnthropicChatClient")
            self.assertEqual(type(profile._primary).__name__, "OpenAIChatClient")
            self.assertEqual(profile._primary.model, "qwen3:8b")
            self.assertIs(zone._primary, chat._primary)
            self.assertIsNot(zone._primary, profile._primary)
            self.assertEqual(len(sdk.built), 2)
            local = [kw for kw in sdk.built if kw.get("base_url")]
            self.assertEqual(local[0]["base_url"], "http://vllm.internal:8000/v1")
            self.assertEqual(sdk.built[0]["timeout"], 30.0)

    def test_same_provider_different_models_do_not_share(self):
        with _FakeSDK():
            zone = create_llm_client(Role.ZONE, _settings())
            profile = create_llm_client(Role.PROFILE, _settings())
        self.assertIsNot(zone._primary, profile._primary)
        self.assertEqual((zone._primary.model, profile._primary.model), ("resp-model", "prof-model"))

    def test_an_unresolvable_role_fails_when_its_client_is_made(self):
        with _FakeSDK(), self.assertRaises(LLMConfigError):
            create_llm_client(Role.ZONE, _settings(llm_zone="nope:model"))


# (c) a role on a provider without a key: not configured, and the message names the role

class TestConfigured(unittest.TestCase):
    def test_default_configuration_is_configured(self):
        self.assertTrue(llm_configured(_settings()))
        self.assertTrue(llm_configured(_settings(openai_api_key=None, openai_base_url="http://vllm:8000/v1")))

    def test_role_on_provider_without_key(self):
        settings = _settings(llm_zone="anthropic:claude-big")
        self.assertFalse(llm_configured(settings))
        problems = llm_config_problems(settings)
        self.assertEqual(len(problems), 1)
        where, why = problems[0]
        self.assertEqual(where, "zone (LLM_ZONE)")
        self.assertIn("ANTHROPIC_API_KEY", why)
        self.assertNotIn("anthropic", where)

    def test_anthropic_role_without_its_package_is_not_configured(self):
        settings = _settings(anthropic_api_key="sk-ant", llm_zone="anthropic:claude-big")
        with mock.patch("llm.routing.importlib.util.find_spec", return_value=None):
            where, why = llm_config_problems(settings)[0]
        self.assertEqual(where, "zone (LLM_ZONE)")
        self.assertIn("'anthropic' package", why)
        with mock.patch("llm.routing.importlib.util.find_spec", return_value=object()):
            self.assertTrue(llm_configured(settings))

    def test_fallback_without_key_counts(self):
        problems = llm_config_problems(_settings(llm_summary_fallback="gemini:flash"))
        self.assertEqual(problems[0][0], "summary (LLM_SUMMARY_FALLBACK)")
        self.assertIn("GOOGLE_API_KEY", problems[0][1])

    def test_a_missing_global_key_reads_as_one_problem_per_setting(self):
        problems = llm_config_problems(_settings(openai_api_key=None))
        self.assertEqual(
            sorted(where for where, _ in problems),
            [
                "context (LLM_PROVIDER/CONTEXT_MODEL)",
                "profile, behavior, summary (LLM_PROVIDER/PROFILE_MODEL)",
                "zone, chat (LLM_PROVIDER/RESPONSE_MODEL)",
            ],
        )

    def test_misspelt_provider_is_reported_not_raised(self):
        where, why = llm_config_problems(_settings(llm_behavior="antropic:x"))[0]
        self.assertEqual(where, "behavior (LLM_BEHAVIOR)")
        self.assertIn("not a provider", why)


# (d) provider error: without a fallback it is an error, with one the fallback answers and is counted

class TestFallback(MetricsTestCase):
    def test_no_fallback_configured_means_the_error_propagates(self):
        primary = _ScriptedLLM("big-model", error=RuntimeError("provider down"))
        client = RoutedChatClient(_route(fallback=False), primary)
        result, text = self.run_and_scrape(client.complete_json("s", "u"))
        self.assertIsInstance(result, RuntimeError)
        self.assertNotIn("genui_llm_fallbacks_total", text)
        self.assertIn(
            'genui_llm_model_calls_total{model="big-model",outcome="error",provider="anthropic",role="zone"} 1',
            text,
        )

    def test_declared_fallback_answers_is_counted_and_is_the_answered_model(self):
        primary = _ScriptedLLM("big-model", error=RuntimeError("provider down"))
        fallback = _ScriptedLLM("small-model", text='{"ok": true}')
        client = RoutedChatClient(_route(), primary, fallback)

        async def call():
            text = await client.complete_json("s", "u")
            return text, answered_model(client)

        (text, model), scrape = self.run_and_scrape(call())
        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(model, "small-model")
        self.assertIn(
            'genui_llm_fallbacks_total{from_model="big-model",role="zone",to_model="small-model"} 1',
            scrape,
        )
        block = disclosure_block(True, PROVENANCE_GENERATED, model=model, expose_model=True)
        self.assertEqual(block["model"], "small-model")

    def test_primary_success_does_not_touch_the_fallback(self):
        primary = _ScriptedLLM("big-model", text="{}")
        fallback = _ScriptedLLM("small-model", text="{}")
        client = RoutedChatClient(_route(), primary, fallback)

        async def call():
            await client.complete_json("s", "u")
            return answered_model(client)

        model, scrape = self.run_and_scrape(call())
        self.assertEqual(model, "big-model")
        self.assertEqual(fallback.calls, 0)
        self.assertNotIn("genui_llm_fallbacks_total", scrape)

    def test_stream_falls_back_only_before_the_first_delta(self):
        primary = _ScriptedLLM("big-model", error=RuntimeError("down"))
        fallback = _ScriptedLLM("small-model", text='{"components": []}')
        client = RoutedChatClient(_route(), primary, fallback)

        async def consume():
            text = "".join([d async for d in client.stream_json("s", "u")])
            return text, answered_model(client)

        (text, model), scrape = self.run_and_scrape(consume())
        self.assertEqual((text, model), ('{"components": []}', "small-model"))
        self.assertIn("genui_llm_fallbacks_total", scrape)

        broken = RoutedChatClient(_route(), _ScriptedLLM("big-model", stream_then_fail=True), fallback)

        async def consume_broken():
            return "".join([d async for d in broken.stream_json("s", "u")])

        result, _ = self.run_and_scrape(consume_broken())
        self.assertIsInstance(result, RuntimeError)

    def test_answered_model_is_per_task(self):
        primary = _ScriptedLLM("big-model", error=RuntimeError("down"))
        fallback = _ScriptedLLM("small-model", text="{}")
        failing = RoutedChatClient(_route(), primary, fallback)
        healthy = RoutedChatClient(_route(), _ScriptedLLM("big-model", text="{}"), fallback)

        async def one(client):
            await client.complete_json("s", "u")
            await asyncio.sleep(0)
            return answered_model(client)

        async def both():
            return await asyncio.gather(one(failing), one(healthy))

        models, _ = self.run_and_scrape(both())
        self.assertEqual(models, ["small-model", "big-model"])


# (e) the metrics of a generation carry role and model

class TestCallMetrics(MetricsTestCase):
    def test_every_call_is_labelled_with_role_provider_and_model(self):
        client = RoutedChatClient(_route(fallback=False), _ScriptedLLM("big-model", text="{}"))
        _, text = self.run_and_scrape(client.complete_json("s", "u"))
        self.assertIn(
            'genui_llm_model_calls_total{model="big-model",outcome="ok",provider="anthropic",role="zone"} 1',
            text,
        )
        self.assertIn('genui_llm_model_call_seconds_count{model="big-model",role="zone"} 1', text)


if __name__ == "__main__":
    unittest.main()
