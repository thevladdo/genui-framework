"""
LIVE verification of the /query chat stack against the real LLM provider.

OPT-IN on purpose: the default suite must stay pure/mocked (no key, no
network, no cost). Run explicitly from backend/ with the venv python so
backend/.env (OPENAI_API_KEY) is picked up:

    GENUI_LIVE_LLM=1 ./venv/bin/python -m unittest tests.test_live_llm -v

What only a real call can verify (everything else is covered mocked in
test_query_isolation.py):
- the provider accepts our tools payload together with
  response_format json_object;
- the tool-call round trip (assistant tool_calls -> role:"tool" message
  -> final answer) is threaded correctly for the real API;
- the end-to-end ResponseAgent pipeline (pre-fetch, tool handler on the
  active loop, validation, URL whitelist) holds with real model output.
"""

import asyncio
import json
import os
import re
import unittest

LIVE = os.environ.get("GENUI_LIVE_LLM") == "1"

if LIVE:
    from config import settings
    from llm import create_llm_client
    from agents.response_agent import ResponseAgent

KB_URL = "https://kb.acme.example/plans"
KB_PASSAGE = (
    "AcmeCorp offers the Starter plan at 9 euro per month and the Scale "
    f"plan at 49 euro per month. Full details: {KB_URL}"
)

FALLBACK_TEXT = "I couldn't process your request right now."


class LiveFakeStore:
    """Real LLM, fake KB: empty pre-fetch, content only via the tool."""

    def __init__(self):
        self.calls = []

    async def search_async(self, query=None, top_k=None, score_threshold=None,
                           filters=None, tenant=None):
        self.calls.append({"query": query, "tenant": tenant})
        if len(self.calls) == 1:  # pre-fetch with the raw user query
            return []

        class R:
            content = KB_PASSAGE
            score = 0.9
            chunk_id = "c1"
            metadata = {"source_document": "plans.md", "url": KB_URL}

        return [R()]


@unittest.skipUnless(LIVE, "live LLM check: set GENUI_LIVE_LLM=1 (needs OPENAI_API_KEY)")
class LiveToolLoopTest(unittest.TestCase):
    def test_tool_loop_against_real_api(self):
        """Forced tool call: verifies tools + json_object and the
        round-trip threading against the real endpoint."""
        client = create_llm_client(settings.response_model)
        invocations = []

        async def handler(name, arguments):
            invocations.append((name, arguments))
            return KB_PASSAGE

        result = asyncio.run(client.complete_json_with_tools(
            system=(
                "You are a JSON API. You MUST call the search_documents tool "
                "exactly once before answering. Then respond with a JSON "
                'object: {"answer": "<one sentence>"}.'
            ),
            user="What does the Starter plan cost?",
            tools=[ResponseAgent.SEARCH_TOOL],
            tool_handler=handler,
        ))

        self.assertGreaterEqual(len(invocations), 1)
        name, arguments = invocations[0]
        self.assertEqual(name, "search_documents")
        self.assertTrue(str(arguments.get("query", "")).strip())
        parsed = json.loads(result)
        self.assertIn("answer", parsed)
        print(f"\n[live] tool query={arguments.get('query')!r} "
              f"answer={parsed.get('answer')!r}")

    def test_response_agent_end_to_end_live(self):
        """Full pipeline on a real call: no silent fallback, whitelist
        holds on real model output, tenant scoping on every search."""
        store = LiveFakeStore()
        agent = ResponseAgent(vector_store=store, llm_client=None)  # real client

        response = asyncio.run(agent.process_query_async(
            query="What plans does AcmeCorp offer and at what price?",
            tenant="live-tenant",
        ))

        # The old stack died here (RuntimeError -> silent fallback)
        self.assertNotEqual(response.text_response, FALLBACK_TEXT)
        self.assertTrue(response.text_response.strip())

        # Every search (pre-fetch + any tool call) carried the request tenant
        self.assertTrue(all(c["tenant"] == "live-tenant" for c in store.calls))

        # No invented URLs survive: whatever the model emitted, only input
        # URLs may appear in components and sources
        serialized = json.dumps([c.to_dict() for c in response.components])
        for url in re.findall(r"https?://[^\s\"'<>)]+", serialized):
            self.assertTrue(url.startswith(KB_URL), f"non-input URL survived: {url}")
        for source in response.sources:
            if source.get("url"):
                self.assertTrue(source["url"].startswith(KB_URL), source["url"])

        tool_used = len(store.calls) > 1
        print(f"\n[live] tool_used={tool_used} searches={len(store.calls)} "
              f"components={len(response.components)} "
              f"text={response.text_response[:120]!r}")


if __name__ == "__main__":
    unittest.main()
