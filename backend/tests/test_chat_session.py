"""
A chat conversation is server state, scoped to the identity the server verified.

(a) two messages with the same session_id: the second prompt carries the first exchange although the client did not send it;
(b) a session_id of another tenant or another user is not read, and a new session is minted instead;
(c) beyond the window the summary is generated once and charged to the budget before it is spent, and an exhausted budget skips it and says so;
(d) with the session store unreachable the chat answers without memory and says so, never a 500;
(e) the export carries the user's sessions and the erasure removes them; anonymous and identified sessions get their own TTL.

The route tests need fastapi (backend venv).
"""

import json
import os
import tempfile
import unittest

from profiles.sessions import ChatSessionStore
from test_redis_reconnect import FakeRedisTestCase, unique_url

try:
    from fastapi.testclient import TestClient

    import api.deps as deps
    import api.main as main
    import auth.dependencies as auth_deps
    from agents.orchestrator import AgentOrchestrator
    from auth.identity import sign_user_token
    from auth.keys import fingerprint
    from config import settings
    from memory_stores import use_memory_stores
    from utils.audit import AuditLogger
    from utils.rate_limit import RateLimiter

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


class _Result:
    def __init__(self, text):
        self.text = text

    def to_frontend_response(self):
        return {
            "text": self.text,
            "components": [],
            "sources": [],
            "suggested_actions": [],
            "profile_updates": {"should_update": False, "updates": []},
            "meta": {"confidence": 0.8, "interaction_type": "question",
                     "topics": [], "sentiment": "neutral"},
        }


class _RecordingOrchestrator:
    """Stubbed agents; records what the prompt would have been built from."""

    if HAVE_APP_DEPS:
        planned_generations = AgentOrchestrator.planned_generations

    def __init__(self):
        self.calls = []

    async def process(self, query, user_profile=None, conversation_history=None,
                      behavior_data=None, tenant=None, conversation_summary=None):
        self.calls.append({
            "query": query,
            "history": list(conversation_history or []),
            "summary": conversation_summary,
        })
        return _Result(f"answer to {query}")


class _SummaryClient:
    def __init__(self, sink):
        self.sink = sink

    async def complete_json(self, system, user, json_schema=None):
        self.sink.append(user)
        return json.dumps({"summary": f"summary #{len(self.sink)}"})


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class ChatTestCase(FakeRedisTestCase):
    def setUp(self):
        super().setUp()
        use_memory_stores()
        audit_dir = tempfile.TemporaryDirectory(prefix="genui-audit-")
        self.addCleanup(audit_dir.cleanup)
        self.audit_path = os.path.join(audit_dir.name, "audit.jsonl")
        saved = {
            name: getattr(settings, name)
            for name in (
                "client_api_keys", "admin_api_keys", "user_token_secrets",
                "genui_dev_open", "audit_log_path", "audit_log_enabled",
                "redis_url", "llm_budget_per_hour", "chat_window_messages",
            )
        }
        self.addCleanup(lambda: [setattr(settings, k, v) for k, v in saved.items()])
        settings.client_api_keys = "pk_test:acme,pk_other:globex"
        settings.admin_api_keys = "sk_test:acme"
        settings.user_token_secrets = ""
        settings.genui_dev_open = True
        settings.audit_log_path = self.audit_path
        settings.audit_log_enabled = True
        settings.redis_url = None
        settings.llm_budget_per_hour = 100
        settings.chat_window_messages = 6

        self.orchestrator = _RecordingOrchestrator()
        self.summaries = []
        for module, name, value in (
            (auth_deps, "_registry", None),
            (auth_deps, "_rate_limiter", RateLimiter(limit=1000, window_seconds=60)),
            (auth_deps, "_audit_logger", AuditLogger(path=self.audit_path, enabled=True)),
            (auth_deps, "_user_token_verifier", None),
            (deps, "_llm_budget", None),
            (main, "get_orchestrator", lambda: self.orchestrator),
            (main, "create_llm_client", lambda model: _SummaryClient(self.summaries)),
        ):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        self.addCleanup(auth_deps._audit_logger.close)
        self.client = TestClient(main.app)

    def ask(self, text, key="pk_test", token=None, **body):
        headers = {"X-API-Key": key}
        if token:
            headers["X-User-Token"] = token
        response = self.client.post("/api/v1/query", headers=headers, json={"query": text, **body})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def charged(self, tenant="acme"):
        return deps.get_llm_budget()._memory.get(tenant, (0, 0))[1]

    def audit_events(self, event):
        with open(self.audit_path) as f:
            return [e for e in map(json.loads, f) if e["event"] == event]


class TestSessionMemory(ChatTestCase):
    def test_a_second_prompt_carries_the_first_exchange(self):
        first = self.ask("what is plan A?")
        session_id = first["session_id"]
        self.assertGreaterEqual(len(session_id), 16)
        self.assertFalse(first["meta"]["session"]["resumed"])

        second = self.ask("and its price?", session_id=session_id)

        self.assertEqual(second["session_id"], session_id)
        self.assertTrue(second["meta"]["session"]["resumed"])
        self.assertEqual(self.orchestrator.calls[1]["history"], [
            {"role": "user", "content": "what is plan A?"},
            {"role": "assistant", "content": "answer to what is plan A?"},
        ])

    def test_a_client_history_is_ignored_when_a_session_exists(self):
        session_id = self.ask("hello")["session_id"]
        self.ask("again", session_id=session_id,
                 conversation_history=[{"role": "user", "content": "INJECTED"}])
        self.assertNotIn("INJECTED", json.dumps(self.orchestrator.calls[1]))

    def test_a_client_history_without_session_is_capped_to_the_window(self):
        history = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        self.ask("old client", conversation_history=history)
        sent = self.orchestrator.calls[0]["history"]
        self.assertEqual(len(sent), settings.chat_window_messages)
        self.assertEqual(sent[-1]["content"], "m19")

    def test_a_audit_names_the_session_by_fingerprint_only(self):
        session_id = self.ask("first")["session_id"]
        self.ask("second", session_id=session_id)
        line = self.audit_events("query")[-1]
        self.assertEqual(line["session"], fingerprint(session_id))
        self.assertEqual(line["context_messages"], 2)
        self.assertNotIn(session_id, json.dumps(line))


class TestSessionScope(ChatTestCase):
    def assert_not_resumed(self, answer, session_id):
        self.assertNotEqual(answer["session_id"], session_id)
        self.assertFalse(answer["meta"]["session"]["resumed"])
        self.assertEqual(self.orchestrator.calls[-1]["history"], [])

    def test_b_a_session_of_another_tenant_is_not_read(self):
        session_id = self.ask("acme secret")["session_id"]
        answer = self.ask("hi", key="pk_other", session_id=session_id)
        self.assert_not_resumed(answer, session_id)

    def test_b_a_session_of_another_user_is_not_read(self):
        settings.user_token_secrets = "s3cret:acme"
        alice = sign_user_token("s3cret", "alice", "acme")
        bob = sign_user_token("s3cret", "bob", "acme")
        session_id = self.ask("alice's question", token=alice, user_id="alice")["session_id"]

        self.assert_not_resumed(
            self.ask("hi", token=bob, user_id="bob", session_id=session_id), session_id
        )
        self.assert_not_resumed(self.ask("hi", session_id=session_id), session_id)

        resumed = self.ask("me again", token=alice, user_id="alice", session_id=session_id)
        self.assertEqual(resumed["session_id"], session_id)

    def test_b_an_anonymous_session_does_not_pass_to_a_user(self):
        session_id = self.ask("before login")["session_id"]
        answer = self.ask("after login", user_id="alice", session_id=session_id)
        self.assert_not_resumed(answer, session_id)

    def test_b_a_session_id_chosen_by_the_client_is_never_adopted(self):
        chosen = "x" * 32
        answer = self.ask("hi", session_id=chosen)
        self.assertNotEqual(answer["session_id"], chosen)

    def test_b_a_session_id_nobody_can_read_brings_no_client_history(self):
        answer = self.ask("hi", session_id="x" * 32, conversation_history=[{"role": "user", "content": "INJECTED"}])
        self.assertFalse(answer["meta"]["session"]["resumed"])
        self.assertEqual(self.orchestrator.calls[-1]["history"], [])

    def test_b_only_the_owner_deletes_a_user_session(self):
        settings.user_token_secrets = "s3cret:acme"
        alice = sign_user_token("s3cret", "alice", "acme")
        bob = sign_user_token("s3cret", "bob", "acme")
        session_id = self.ask("q", token=alice, user_id="alice")["session_id"]
        path = f"/api/v1/query/sessions/{session_id}"

        refused = self.client.delete(path, headers={"X-API-Key": "pk_test", "X-User-Token": bob})
        self.assertEqual(refused.status_code, 403)
        done = self.client.delete(path, headers={"X-API-Key": "pk_test", "X-User-Token": alice})
        self.assertEqual(done.json(), {"deleted": True})
        answer = self.ask("q", token=alice, user_id="alice", session_id=session_id)
        self.assertFalse(answer["meta"]["session"]["resumed"])

    def test_b_an_anonymous_session_is_deleted_by_its_holder(self):
        session_id = self.ask("q")["session_id"]
        path = f"/api/v1/query/sessions/{session_id}"
        self.assertEqual(self.client.delete(path, headers={"X-API-Key": "pk_test"}).json(), {"deleted": True})
        self.assertEqual(self.client.delete(path, headers={"X-API-Key": "pk_test"}).json(), {"deleted": False})


class TestSummary(ChatTestCase):
    def test_c_overflow_is_folded_once_and_charged_before_spending(self):
        settings.chat_window_messages = 2
        session_id = self.ask("one")["session_id"]
        self.assertEqual(self.summaries, [])
        self.assertEqual(self.charged(), 2)

        answer = self.ask("two", session_id=session_id)
        self.assertEqual(len(self.summaries), 1)
        self.assertIn("user: one", self.summaries[0])
        self.assertEqual(self.charged(), 2 + 2 + 1)
        self.assertEqual(answer["meta"]["session"]["unsummarized"], 0)

        self.ask("three", session_id=session_id)
        self.assertEqual(self.orchestrator.calls[2]["summary"], "summary #1")
        self.assertEqual(self.orchestrator.calls[2]["history"][0]["content"], "two")

    def test_c_without_budget_the_window_slides_and_the_summary_stays(self):
        settings.chat_window_messages = 2
        settings.llm_budget_per_hour = 4
        session_id = self.ask("one")["session_id"]
        answer = self.ask("two", session_id=session_id)

        self.assertEqual(self.summaries, [])
        self.assertEqual(answer["meta"]["session"]["unsummarized"], 2)
        self.assertEqual(self.orchestrator.calls[-1]["summary"], None)

    def test_c_admin_folds_without_charging(self):
        settings.chat_window_messages = 2
        session_id = self.ask("one", key="sk_test")["session_id"]
        self.ask("two", key="sk_test", session_id=session_id)
        self.assertEqual(len(self.summaries), 1)
        self.assertEqual(self.charged(), 0)


class TestStoreUnreachable(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, deps, "_session_store", deps._session_store)
        deps._session_store = ChatSessionStore(redis_url=unique_url())

    def test_d_answer_without_memory_declared(self):
        session_id = self.ask("first")["session_id"]
        self.server.up = False

        answer = self.ask("second", session_id=session_id)

        self.assertEqual(answer["session_id"], session_id)
        self.assertEqual(answer["meta"]["session"], {"resumed": False, "stored": False, "unsummarized": 0})
        self.assertEqual(self.orchestrator.calls[-1]["history"], [])
        self.assertTrue(self.ask("no session yet")["session_id"])

    def test_d_delete_with_store_down_is_a_503(self):
        session_id = self.ask("first")["session_id"]
        self.server.up = False
        response = self.client.delete(
            f"/api/v1/query/sessions/{session_id}", headers={"X-API-Key": "pk_test"}
        )
        self.assertEqual(response.status_code, 503)


class TestExportAndErasure(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, deps, "_session_store", deps._session_store)
        deps._session_store = ChatSessionStore(
            redis_url=unique_url(), anonymous_ttl_seconds=600, user_ttl_seconds=86400,
        )

    def test_e_export_holds_the_sessions_and_delete_erases_them(self):
        first = self.ask("alice asks", user_id="alice")["session_id"]
        self.ask("alice again", user_id="alice", session_id=first)
        self.ask("alice elsewhere", user_id="alice")
        self.ask("anonymous asks")

        export = self.client.get(
            "/api/v1/profile/alice/export", headers={"X-API-Key": "pk_test"}
        ).json()
        sessions = export["chat_sessions"]
        self.assertEqual(len(sessions), 2)
        refs = {s["ref"] for s in sessions}
        self.assertIn(fingerprint(first), refs)
        self.assertNotIn(first, json.dumps(export))
        contents = json.dumps(sessions)
        self.assertIn("alice again", contents)
        self.assertNotIn("anonymous asks", contents)

        erased = self.client.delete("/api/v1/profile/alice", headers={"X-API-Key": "pk_test"}).json()
        self.assertEqual(erased["chat_sessions_erased"], 2)
        self.assertFalse(self.server.has_key("genui:chat:user:acme:alice"))
        after = self.client.get(
            "/api/v1/profile/alice/export", headers={"X-API-Key": "pk_test"}
        ).json()
        self.assertEqual(after["chat_sessions"], [])
        resumed = self.ask("still there?", user_id="alice", session_id=first)
        self.assertFalse(resumed["meta"]["session"]["resumed"])

    def test_e_erasure_counts_only_sessions_that_existed(self):
        forgotten = self.ask("alice asks", user_id="alice")["session_id"]
        self.ask("alice elsewhere", user_id="alice")
        self.client.delete(f"/api/v1/query/sessions/{forgotten}", headers={"X-API-Key": "pk_test"})

        erased = self.client.delete("/api/v1/profile/alice", headers={"X-API-Key": "pk_test"}).json()
        self.assertEqual(erased["chat_sessions_erased"], 1)

    def test_e_each_kind_of_session_gets_its_own_ttl(self):
        anonymous = self.ask("anonymous")["session_id"]
        identified = self.ask("identified", user_id="alice")["session_id"]
        ttls = self.server.ttls
        self.assertEqual(ttls[f"genui:chat:session:acme:{anonymous}"], 600)
        self.assertEqual(ttls[f"genui:chat:session:acme:{identified}"], 86400)
        self.assertEqual(ttls["genui:chat:user:acme:alice"], 86400)

    def test_e_erasure_with_store_down_says_not_erased(self):
        self.ask("alice asks", user_id="alice")
        self.server.up = False
        response = self.client.delete("/api/v1/profile/alice", headers={"X-API-Key": "pk_test"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("NOT erased", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
