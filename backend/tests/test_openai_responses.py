"""
OpenAI's own endpoint is called through the Responses API, everything else that speaks the OpenAI protocol through chat completions.

Runs without the openai package: the clients are built with __new__ and given a scripted SDK.
"""

import asyncio
import types
import unittest
from types import SimpleNamespace

from llm import factory
from llm.openai_client import OpenAIChatClient, OpenAIResponsesClient
from llm.routing import Role


class _Item(SimpleNamespace):
    def model_dump(self, exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def _response(text="", output=None):
    return SimpleNamespace(output_text=text, output=output or [_Item(type="message", role="assistant", content=text)])


def _call(call_id, name, arguments):
    return _Item(type="function_call", call_id=call_id, name=name, arguments=arguments, id=f"fc_{call_id}")


class _HTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _ScriptedSDK:
    def __init__(self, script):
        self.requests = []
        self._script = list(script)

        async def create(**kwargs):
            self.requests.append(kwargs)
            step = self._script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step

        self.responses = SimpleNamespace(create=create)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _client(cls, script):
    client = cls.__new__(cls)
    client.model = "test-model"
    client.provider_name = "openai"
    client._supports_json_schema = True
    client._client = _ScriptedSDK(script)
    return client


SEARCH = [{"name": "search_documents", "description": "search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}]


class TestCompleteJson(unittest.TestCase):
    def test_system_input_schema_and_no_storage(self):
        client = _client(OpenAIResponsesClient, [_response('{"ok": true}')])
        text = asyncio.run(client.complete_json("sys", "user", {"type": "object"}))

        self.assertEqual(text, '{"ok": true}')
        request = client._client.requests[0]
        self.assertEqual(request["input"], [{"role": "developer", "content": "sys"}, {"role": "user", "content": "user"}])
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertEqual(request["text"]["format"]["schema"], {"type": "object"})
        self.assertIs(request["store"], False)

    def test_a_rejected_schema_falls_back_to_json_object_once(self):
        client = _client(OpenAIResponsesClient, [_HTTPError(400), _response("{}"), _response("{}")])
        asyncio.run(client.complete_json("sys", "user", {"type": "object"}))
        asyncio.run(client.complete_json("sys", "user", {"type": "object"}))

        formats = [r["text"]["format"]["type"] for r in client._client.requests]
        self.assertEqual(formats, ["json_schema", "json_object", "json_object"])

    def test_any_other_error_is_not_retried(self):
        for cls in (OpenAIResponsesClient, OpenAIChatClient):
            client = _client(cls, [_HTTPError(404), _response("{}")])
            with self.assertRaises(_HTTPError):
                asyncio.run(client.complete_json("sys", "user", {"type": "object"}))
            self.assertEqual(len(client._client.requests), 1, cls.__name__)
            self.assertTrue(client._supports_json_schema)


class TestToolLoop(unittest.TestCase):
    def test_round_trip_passes_the_items_back_with_the_output(self):
        reasoning = _Item(type="reasoning", id="rs_1", encrypted_content="opaque", summary=[])
        client = _client(OpenAIResponsesClient, [
            _response(output=[reasoning, _call("c1", "search_documents", '{"query": "x"}')]),
            _response('{"done": true}'),
        ])
        seen = []

        async def handler(name, arguments):
            seen.append((name, arguments))
            return "CTX"

        text = asyncio.run(client.complete_json_with_tools("sys", "user", SEARCH, handler))

        self.assertEqual(text, '{"done": true}')
        self.assertEqual(seen, [("search_documents", {"query": "x"})])
        first, second = client._client.requests
        self.assertEqual(first["tools"][0]["name"], "search_documents")
        self.assertIs(first["tools"][0]["strict"], False)
        self.assertIn("reasoning.encrypted_content", first["include"])
        self.assertIs(first["store"], False)
        items = second["input"]
        self.assertEqual(items[:2], [{"role": "developer", "content": "sys"}, {"role": "user", "content": "user"}])
        self.assertEqual(items[2]["type"], "reasoning")
        self.assertEqual(items[2]["encrypted_content"], "opaque")
        self.assertEqual(items[3]["call_id"], "c1")
        self.assertEqual(items[4], {"type": "function_call_output", "call_id": "c1", "output": "CTX"})

    def test_failing_tool_is_reported_to_the_model(self):
        client = _client(OpenAIResponsesClient, [
            _response(output=[_call("c1", "search_documents", "{}")]),
            _response("{}"),
        ])

        async def handler(name, arguments):
            raise RuntimeError("qdrant down")

        asyncio.run(client.complete_json_with_tools("sys", "user", SEARCH, handler))
        output = client._client.requests[1]["input"][-1]["output"]
        self.assertIn("search_documents failed", output)
        self.assertNotIn("qdrant down", output)

    def test_exhausted_rounds_force_an_answer_without_tools(self):
        loop = _response(output=[_call("c1", "search_documents", "{}")])
        client = _client(OpenAIResponsesClient, [loop, loop, _response('{"final": 1}')])

        async def handler(name, arguments):
            return "CTX"

        text = asyncio.run(client.complete_json_with_tools("sys", "user", SEARCH, handler, max_tool_rounds=2))
        self.assertEqual(text, '{"final": 1}')
        self.assertEqual(client._client.requests[-1]["tool_choice"], "none")


class _Events:
    def __init__(self, events):
        self._events = list(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


class TestStream(unittest.TestCase):
    def collect(self, events):
        client = _client(OpenAIResponsesClient, [_Events(events)])

        async def run():
            return [d async for d in client.stream_json("sys", "user")]

        return client, asyncio.run(run())

    def test_text_deltas_are_yielded(self):
        client, deltas = self.collect([
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta='{"a"'),
            SimpleNamespace(type="response.output_text.delta", delta=": 1}"),
            SimpleNamespace(type="response.completed"),
        ])
        self.assertEqual("".join(deltas), '{"a": 1}')
        self.assertIs(client._client.requests[0]["stream"], True)
        self.assertIs(client._client.requests[0]["store"], False)

    def test_a_failed_stream_raises(self):
        with self.assertRaises(RuntimeError):
            self.collect([
                SimpleNamespace(type="response.output_text.delta", delta='{"a"'),
                SimpleNamespace(type="response.failed", response=SimpleNamespace(error=SimpleNamespace(message="boom"), incomplete_details=None)),
            ])

    def test_a_truncated_stream_raises(self):
        with self.assertRaises(RuntimeError):
            self.collect([
                SimpleNamespace(type="response.output_text.delta", delta='{"a"'),
                SimpleNamespace(type="response.incomplete", response=SimpleNamespace(error=None, incomplete_details=SimpleNamespace(reason="max_output_tokens"))),
            ])


class TestWhichAPI(unittest.TestCase):
    def build(self, **overrides):
        settings = SimpleNamespace(
            llm_provider="openai", openai_api_key="sk", anthropic_api_key=None, google_api_key="g",
            openai_base_url=None, response_model="m", profile_model="m", context_model="m", llm_timeout_seconds=None,
        )
        for k, v in overrides.items():
            setattr(settings, k, v)
        import sys
        saved = sys.modules.get("openai")
        sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=lambda **kwargs: SimpleNamespace(**kwargs))
        factory._clients.clear()
        try:
            return type(factory.create_llm_client(Role.CHAT, settings)._primary)
        finally:
            factory._clients.clear()
            if saved is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = saved

    def test_openai_endpoint_uses_responses(self):
        self.assertIs(self.build(), OpenAIResponsesClient)

    def test_compatible_endpoints_keep_chat_completions(self):
        self.assertIs(self.build(openai_base_url="http://vllm.internal:8000/v1"), OpenAIChatClient)
        self.assertIs(self.build(llm_provider="gemini"), OpenAIChatClient)


if __name__ == "__main__":
    unittest.main()
