"""
Tests for /query chat isolation (roadmap/fondamenta/03).

The invariant: NO conversational state survives a single request or
crosses users/tenants. Historically the agents sat on a datapizza
Agent whose memory semantics depended on a 0.x library default
(stateless=False replays user A's turns to user B), and the RAG tool
was sync and called asyncio.run() on the active event loop
(RuntimeError -> silent fallback). The agents now talk to the internal
llm/ abstraction: state is per-request by construction, the search
tool is an async closure carrying the request's tenant.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The agent tests need the app deps (backend venv); they skip in the
pure-stdlib shell interpreter. The llm/ tool-loop tests run anywhere.
"""

import asyncio
import json
import unittest
from types import SimpleNamespace

from llm.base import LLMChatClient
from llm.openai_client import OpenAIChatClient

try:  # app-level deps: available in the backend venv, not in the shell python
    from agents.response_agent import ResponseAgent
    from agents.profile_agent import ProfileAgent
    from agents.behave_agent import BehaveAgent
    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


VALID_PAYLOAD = json.dumps({
    "text_response": "ok",
    "components": [],
    "sources": [],
    "confidence": 0.9,
    "suggested_actions": [],
})


class RecordingLLM(LLMChatClient):
    """Captures exactly what reaches the model, call by call."""

    def __init__(self, payload=VALID_PAYLOAD):
        self.payload = payload
        self.calls = []

    async def complete_json(self, system, user, json_schema=None):
        self.calls.append({"system": system, "user": user, "tools": None})
        return self.payload

    async def complete_json_with_tools(self, system, user, tools, tool_handler,
                                       max_tool_rounds=3):
        self.calls.append({"system": system, "user": user, "tools": tools})
        return self.payload

    async def stream_json(self, system, user):
        yield self.payload


class ToolCallingLLM(RecordingLLM):
    """Simulates a model that decides to search before answering."""

    def __init__(self, payload=VALID_PAYLOAD, tool_query="reformulated query"):
        super().__init__(payload)
        self.tool_query = tool_query
        self.tool_results = []

    async def complete_json_with_tools(self, system, user, tools, tool_handler,
                                       max_tool_rounds=3):
        self.calls.append({"system": system, "user": user, "tools": tools})
        # The handler runs on the ACTIVE event loop, like in production:
        # the old sync tool died here with "asyncio.run() cannot be
        # called from a running event loop".
        result = await tool_handler("search_documents", {"query": self.tool_query})
        self.tool_results.append(result)
        return self.payload


class FakeResult:
    """RetrievalResult stand-in for build_context_from_results."""

    def __init__(self, content, url=""):
        self.content = content
        self.score = 0.9
        self.chunk_id = "c1"
        self.metadata = {"source_document": "kb.md", "url": url}


class FakeVectorStore:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    async def search_async(self, query=None, top_k=None, score_threshold=None,
                           filters=None, tenant=None):
        self.calls.append({"query": query, "top_k": top_k, "tenant": tenant})
        return list(self.results)


@unittest.skipUnless(HAVE_APP_DEPS, "requires backend venv (rag/config deps)")
class ResponseAgentIsolationTest(unittest.TestCase):
    """DoD: two sequential /query must not share context, ever."""

    def test_sequential_queries_share_nothing(self):
        llm = RecordingLLM()
        agent = ResponseAgent(vector_store=FakeVectorStore(), llm_client=llm)

        asyncio.run(agent.process_query_async(
            query="What is the SECRET-ALPHA project?",
            user_profile={
                "userId": "user-a",
                "demographic": {"name": {"value": "AlphaUser", "confidence": 1.0}},
            },
            conversation_history=[{"role": "user", "content": "alpha-history-marker"}],
            tenant="tenant-a",
        ))
        asyncio.run(agent.process_query_async(
            query="Tell me about pricing", tenant="tenant-b",
        ))

        self.assertEqual(len(llm.calls), 2)
        second_prompt = llm.calls[1]["user"]
        self.assertIn("pricing", second_prompt)
        # Nothing of user A may reach user B's model call
        for marker in ("SECRET-ALPHA", "AlphaUser", "alpha-history-marker", "user-a"):
            self.assertNotIn(marker, second_prompt)
        self.assertNotIn("tenant-a", second_prompt)

    def test_tenant_scoped_per_request(self):
        store = FakeVectorStore()
        agent = ResponseAgent(vector_store=store, llm_client=RecordingLLM())

        asyncio.run(agent.process_query_async(query="q1", tenant="acme"))
        asyncio.run(agent.process_query_async(query="q2", tenant="globex"))
        asyncio.run(agent.process_query_async(query="q3"))  # anonymous/default

        tenants = [c["tenant"] for c in store.calls]
        self.assertEqual(tenants, ["acme", "globex", None])

    def test_rag_tool_runs_on_active_loop_and_stays_tenant_scoped(self):
        """DoD: the model-invoked RAG tool works (no RuntimeError) and
        searches the requesting tenant only."""
        store = FakeVectorStore(results=[FakeResult("Passage about plans.")])
        llm = ToolCallingLLM(tool_query="pricing plans enterprise")
        agent = ResponseAgent(vector_store=store, llm_client=llm)

        response = asyncio.run(agent.process_query_async(
            query="what about pricing?", tenant="acme",
        ))

        # Not the fallback: the flow survived the tool invocation
        self.assertEqual(response.text_response, "ok")
        self.assertEqual(len(llm.tool_results), 1)
        self.assertIn("Passage about plans.", llm.tool_results[0])
        # Pre-fetch + tool search: both scoped to the request tenant
        self.assertEqual(len(store.calls), 2)
        self.assertEqual(store.calls[1]["query"], "pricing plans enterprise")
        self.assertTrue(all(c["tenant"] == "acme" for c in store.calls))

    def test_tool_results_feed_url_whitelist(self):
        """URLs surfaced by the tool are legitimate input URLs; URLs the
        model invents are still stripped."""
        store = FakeVectorStore(
            results=[FakeResult("See https://kb.example.com/doc1 for details.")]
        )
        payload = json.dumps({
            "text_response": "ok",
            "components": [{
                "type": "buttons",
                "data": {"buttons": [
                    {"label": "Docs", "url": "https://kb.example.com/doc1", "style": "primary"},
                    {"label": "Evil", "url": "https://evil.example.com/x", "style": "primary"},
                ]},
            }],
            "sources": [],
            "confidence": 0.9,
            "suggested_actions": [],
        })
        agent = ResponseAgent(vector_store=store, llm_client=ToolCallingLLM(payload=payload))

        response = asyncio.run(agent.process_query_async(query="q", tenant="t"))

        serialized = json.dumps([c.to_dict() for c in response.components])
        self.assertIn("https://kb.example.com/doc1", serialized)
        self.assertNotIn("evil.example.com", serialized)


@unittest.skipUnless(HAVE_APP_DEPS, "requires backend venv (rag/config deps)")
class SupportAgentsMigrationTest(unittest.TestCase):
    """Profile/Behave agents: stateless per-call prompts over llm/."""

    def test_profile_agent_prompt_is_per_call(self):
        llm = RecordingLLM(payload=json.dumps({
            "has_profile_info": True,
            "updates": [{"field": "demographic.role", "value": "dev", "confidence": 0.9}],
            "interaction_type": "statement",
            "topics": ["work"],
            "sentiment": "neutral",
        }))
        agent = ProfileAgent(llm_client=llm)

        first = asyncio.run(agent.analyze_message_async("I am a developer FIRST-MARKER"))
        asyncio.run(agent.analyze_message_async("what is the weather"))

        self.assertTrue(first.has_profile_info)
        self.assertEqual(first.updates[0].value, "dev")
        self.assertEqual(len(llm.calls), 2)
        self.assertNotIn("FIRST-MARKER", llm.calls[1]["user"])

    def test_behave_agent_over_llm(self):
        llm = RecordingLLM(payload=json.dumps({
            "insights": [],
            "profile_updates": [],
            "engagement_score": 0.7,
            "user_type": "focused",
            "session_summary": "s",
            "recommended_ui_adjustments": [],
        }))
        agent = BehaveAgent(llm_client=llm)

        result = asyncio.run(agent.analyze_behavior_async(
            {"duration": 61000, "clickCount": 4, "maxScrollDepth": 70},
        ))

        self.assertEqual(result.user_type, "focused")
        self.assertIn("Session Duration", llm.calls[0]["user"])



# llm/ tool loop (pure: fake SDK, no network, runs in any interpreter)
def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _sdk_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeSDK:
    """Scripted stand-in for AsyncOpenAI: pops one response per create()."""

    def __init__(self, script):
        self.requests = []
        self._script = list(script)

        async def create(**kwargs):
            self.requests.append(kwargs)
            return self._script.pop(0)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _client_with(script):
    # __new__ skips the lazy AsyncOpenAI import so the loop is testable
    # without the openai package
    client = OpenAIChatClient.__new__(OpenAIChatClient)
    client.model = "test-model"
    client.provider_name = "openai"
    client._supports_json_schema = True
    client._client = FakeSDK(script)
    return client


SEARCH_SPEC = [{
    "name": "search_documents",
    "description": "search",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                   "required": ["query"]},
}]


class OpenAIToolLoopTest(unittest.TestCase):
    def test_tool_round_trip(self):
        client = _client_with([
            _sdk_response(tool_calls=[_tool_call("tc1", "search_documents", '{"query": "x"}')]),
            _sdk_response(content='{"done": true}'),
        ])
        seen = []

        async def handler(name, arguments):
            seen.append((name, arguments))
            return "CTX"

        result = asyncio.run(client.complete_json_with_tools(
            "sys", "user", SEARCH_SPEC, handler,
        ))

        self.assertEqual(result, '{"done": true}')
        self.assertEqual(seen, [("search_documents", {"query": "x"})])
        requests = client._client.requests
        self.assertEqual(requests[0]["tools"][0]["function"]["name"], "search_documents")
        tool_msg = requests[1]["messages"][-1]
        self.assertEqual(tool_msg["role"], "tool")
        self.assertEqual(tool_msg["tool_call_id"], "tc1")
        self.assertEqual(tool_msg["content"], "CTX")
        for request in requests:
            self.assertEqual(request["response_format"], {"type": "json_object"})

    def test_failing_tool_does_not_kill_the_response(self):
        client = _client_with([
            _sdk_response(tool_calls=[_tool_call("tc1", "search_documents", '{"query": "x"}')]),
            _sdk_response(content='{"done": true}'),
        ])

        async def handler(name, arguments):
            raise RuntimeError("qdrant down")

        result = asyncio.run(client.complete_json_with_tools(
            "sys", "user", SEARCH_SPEC, handler,
        ))

        self.assertEqual(result, '{"done": true}')
        tool_msg = client._client.requests[1]["messages"][-1]
        self.assertIn("tool error", tool_msg["content"])
        self.assertIn("qdrant down", tool_msg["content"])

    def test_tool_budget_forces_final_answer(self):
        client = _client_with([
            _sdk_response(tool_calls=[_tool_call("tc1", "search_documents", '{"query": "x"}')]),
            _sdk_response(content='{"done": true}'),
        ])

        async def handler(name, arguments):
            return "CTX"

        result = asyncio.run(client.complete_json_with_tools(
            "sys", "user", SEARCH_SPEC, handler, max_tool_rounds=1,
        ))

        self.assertEqual(result, '{"done": true}')
        # The budget-exhausted final call must not offer tools again
        self.assertNotIn("tools", client._client.requests[1])

    def test_base_fallback_ignores_tools(self):
        class MinimalClient(LLMChatClient):
            async def complete_json(self, system, user, json_schema=None):
                return '{"plain": true}'

            async def stream_json(self, system, user):
                yield '{"plain": true}'

        called = []

        async def handler(name, arguments):
            called.append(name)
            return ""

        result = asyncio.run(MinimalClient().complete_json_with_tools(
            "sys", "user", SEARCH_SPEC, handler,
        ))

        self.assertEqual(result, '{"plain": true}')
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
