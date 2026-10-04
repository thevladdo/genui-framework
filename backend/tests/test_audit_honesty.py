"""
The audit trail and the counters record what they say they record.

(a) a chat query leaves no trace of the question in the audit line;
(b) the summary of what a render showed reads every component type, through the same walk the pinned-content check uses;
(c) a UI event names a user only when the user identity guard admits it, and client-declared fields are labelled as declared;
(d) counters are kept per experiment, and the stats say which experiment and which unit they are computed on.

Runnable with `python3 -m unittest discover -s tests` from backend/.
The route tests need fastapi (backend venv).
"""

import asyncio
import json
import os
import re
import tempfile
import unittest

from metrics import MetricsStore
from schemas.registry import BUILTIN_TYPE_DOCS
from utils.audit import summarize_shown_components
from utils.url_guard import is_url_field

try:
    from fastapi.testclient import TestClient

    import api.deps as deps
    import api.events_router as events_router
    import api.main as main
    import api.zone_router as zone_router
    import auth.dependencies as auth_deps
    from agents.orchestrator import AgentOrchestrator
    from auth.identity import sign_user_token
    from auth.keys import AuthContext
    from config import settings
    from experiments import assign_arm
    from utils.audit import AuditLogger
    from utils.rate_limit import RateLimiter

    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False


def run(coro):
    return asyncio.run(coro)


class _RecordingAudit:
    def __init__(self):
        self.lines = []

    def log(self, event, tenant, user_id=None, **payload):
        self.lines.append({"event": event, "tenant": tenant, "user_id": user_id, **payload})


# (a) the question stays out of the audit

IBAN = "IT60X0542811101000000123456"
QUESTION = f"I have diabetes, can I pay the clinic from {IBAN}?"


class _FakeResult:
    def to_frontend_response(self):
        return {
            "text": "ok",
            "components": [{"type": "text", "data": {"content": "answer"}}],
            "sources": [],
            "suggested_actions": [],
            "profile_updates": {"should_update": False, "updates": []},
            "meta": {"confidence": 0.7, "interaction_type": "question",
                     "topics": [], "sentiment": "neutral"},
        }


class _FakeOrchestrator:
    if HAVE_APP_DEPS:
        planned_generations = AgentOrchestrator.planned_generations

    async def process(self, query, user_profile=None, conversation_history=None,
                      behavior_data=None, tenant=None, conversation_summary=None):
        return _FakeResult()


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestQueryAuditOmitsTheQuestion(unittest.TestCase):
    def setUp(self):
        self._saved = (
            deps._llm_budget, auth_deps._audit_logger, settings.llm_budget_per_hour,
            settings.redis_url, main.get_orchestrator,
        )
        deps._llm_budget = None
        settings.llm_budget_per_hour = 100
        settings.redis_url = None
        self.audit = _RecordingAudit()
        auth_deps._audit_logger = self.audit
        main.get_orchestrator = lambda: _FakeOrchestrator()

    def tearDown(self):
        (
            deps._llm_budget, auth_deps._audit_logger, settings.llm_budget_per_hour,
            settings.redis_url, main.get_orchestrator,
        ) = self._saved

    def test_query_line_carries_counts_not_the_question(self):
        auth = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
        run(main.process_query(main.QueryRequest(query=QUESTION), auth, None))

        lines = [line for line in self.audit.lines if line["event"] == "query"]
        self.assertEqual(len(lines), 1)
        serialized = json.dumps(lines[0])
        self.assertNotIn(IBAN, serialized)
        self.assertNotIn("diabetes", serialized)
        self.assertNotIn("query", lines[0])
        self.assertEqual(lines[0]["component_count"], 1)
        self.assertEqual(lines[0]["confidence"], 0.7)


# (b) the summary reads every type

# One realistic payload per built-in type that has a URL-carrying field.
# The set of keys is checked against the catalog, so a new type with a URL field fails here until it has a sample.
SAMPLES = {
    "bento": {"cards": [{"title": "Docs", "link": "https://ex.com/docs"}]},
    "buttons": {"buttons": [{"label": "Go", "url": "https://ex.com/go"}]},
    "tabs_feature": {"heading": "Plans", "tabs": [{"label": "Pro", "content": {
        "layout": "text-only", "title": "Pro plan",
        "button": {"label": "See", "url": "https://ex.com/pro"}}}]},
    "steps_section": {"layout": "with-image", "steps": [
        {"title": "Sign up", "image_url": "https://ex.com/step.png"}]},
    "testimonial_carousel": {"testimonials": [
        {"quote": "Great", "name": "Ada", "avatar_url": "https://ex.com/ada.png"}]},
    "pricing_cards": {"plans": [{"name": "Team", "price": "10", "features": ["x"],
                                 "cta": {"label": "Buy", "url": "https://ex.com/buy"}}]},
    "content_grid": {"items": [
        {"layout": "text-only", "title": "Post", "url": "https://ex.com/post"}]},
    "hero_banner": {"variant": "centered", "headline": "Welcome",
                    "primary_cta": {"label": "Start", "url": "https://ex.com/start"}},
    "case_studies": {"cases": [{"title": "Case", "image_url": "https://ex.com/case.png"}]},
    "quote": {"quote": "Less is more", "logo_url": "https://ex.com/logo.png"},
    "logo_wall": {"logos": [{"image_url": "https://ex.com/acme.png", "alt": "Acme",
                             "url": "https://acme.example"}]},
}


def _types_with_url_fields():
    types = set()
    for name, doc in BUILTIN_TYPE_DOCS.items():
        fields = re.findall(r'"([a-z_]+)\??"', doc)
        if any(is_url_field(field) for field in fields):
            types.add(name)
    return types


def _urls_in(node):
    if isinstance(node, str):
        return [node] if node.startswith("https://") else []
    if isinstance(node, dict):
        node = list(node.values())
    if isinstance(node, list):
        return [url for item in node for url in _urls_in(item)]
    return []


class TestShownSummaryCoversEveryType(unittest.TestCase):
    def test_every_type_with_a_url_field_has_a_sample(self):
        self.assertEqual(set(SAMPLES), _types_with_url_fields())

    def test_every_url_shown_is_in_the_summary(self):
        for ctype, data in SAMPLES.items():
            with self.subTest(type=ctype):
                summary = summarize_shown_components([{"type": ctype, "data": data}])
                self.assertEqual(summary["component_types"], [ctype])
                expected = _urls_in(data)
                self.assertTrue(expected)
                for url in expected:
                    self.assertIn(url, summary["shown_links"])

    def test_titles_beyond_bento_and_buttons(self):
        summary = summarize_shown_components([
            {"type": "hero_banner", "data": SAMPLES["hero_banner"]},
            {"type": "pricing_cards", "data": SAMPLES["pricing_cards"]},
        ])
        for title in ("Welcome", "Start", "Team", "Buy"):
            self.assertIn(title, summary["shown_titles"])

    def test_custom_component(self):
        summary = summarize_shown_components([{"type": "promo_strip", "data": {
            "headline": "Sale", "items": [{"label": "Shoes", "target_url": "https://ex.com/shoes"}],
        }}])
        self.assertEqual(summary["shown_links"], ["https://ex.com/shoes"])
        self.assertIn("Sale", summary["shown_titles"])

    def test_markdown_links_in_body_text(self):
        summary = summarize_shown_components([
            {"type": "text", "data": {"content": "Read [the guide](https://ex.com/guide)."}},
            {"type": "faq", "data": {"title": "FAQ", "items": [
                {"question": "How?", "answer": "See [docs](https://ex.com/faq)"}]}},
        ])
        self.assertEqual(summary["shown_links"], ["https://ex.com/guide", "https://ex.com/faq"])

    @unittest.skipUnless(HAVE_APP_DEPS, "requires the agent dependencies (backend venv)")
    def test_pinned_link_used_in_markdown_is_not_appended_again(self):
        from agents.zone_agent import enforce_pinned

        components = [{"type": "text", "data": {"content": "Read [the guide](https://ex.com/guide)."}}]
        pinned = [{"title": "Setup guide", "url": "https://ex.com/guide"}]
        result, included = enforce_pinned(components, pinned, max_items=6)
        self.assertEqual([c["type"] for c in result], ["text"])
        self.assertEqual(included, ["https://ex.com/guide"])


# (c) and (d) over HTTP

SECRET = "test-signing-secret"


@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestEventsAreHonest(unittest.TestCase):
    def setUp(self):
        audit_dir = tempfile.TemporaryDirectory(prefix="genui-audit-")
        self.addCleanup(audit_dir.cleanup)
        self.audit_path = os.path.join(audit_dir.name, "audit.jsonl")
        self._saved = (
            settings.client_api_keys, settings.admin_api_keys, settings.user_token_secrets,
            settings.genui_dev_open, settings.audit_log_path, settings.audit_log_enabled,
            settings.redis_url, settings.holdout_percent, settings.holdout_salt,
            auth_deps._registry, auth_deps._rate_limiter, auth_deps._audit_logger,
            auth_deps._user_token_verifier, events_router._metrics_store,
        )
        settings.client_api_keys = "pk_test:acme"
        settings.admin_api_keys = "sk_test:acme"
        settings.user_token_secrets = f"{SECRET}:acme"
        settings.genui_dev_open = False
        settings.audit_log_path = self.audit_path
        settings.audit_log_enabled = True
        settings.redis_url = None
        settings.holdout_percent = 50.0
        settings.holdout_salt = "exp-a"
        auth_deps._registry = None
        auth_deps._rate_limiter = RateLimiter(limit=1000, window_seconds=60)
        auth_deps._audit_logger = AuditLogger(path=self.audit_path, enabled=True)
        self.addCleanup(auth_deps._audit_logger.close)
        auth_deps._user_token_verifier = None
        events_router._metrics_store = MetricsStore()
        self.client = TestClient(main.app)

    def tearDown(self):
        (
            settings.client_api_keys, settings.admin_api_keys, settings.user_token_secrets,
            settings.genui_dev_open, settings.audit_log_path, settings.audit_log_enabled,
            settings.redis_url, settings.holdout_percent, settings.holdout_salt,
            auth_deps._registry, auth_deps._rate_limiter, auth_deps._audit_logger,
            auth_deps._user_token_verifier, events_router._metrics_store,
        ) = self._saved

    def _post(self, event, token=None):
        headers = {"X-API-Key": "pk_test"}
        if token:
            headers["X-User-Token"] = token
        response = self.client.post("/api/v1/events", json={"events": [event]}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _audit(self):
        with open(self.audit_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _stats(self):
        response = self.client.get(
            "/api/v1/events/stats?zone_id=home", headers={"X-API-Key": "sk_test"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _arm_of(self, user_id):
        return assign_arm(user_id, settings.holdout_percent, settings.holdout_salt)

    def test_user_id_without_token_is_not_audited(self):
        body = self._post({"event_type": "click", "zone_id": "home", "user_id": "victim",
                           "render_id": "deadbeef0000", "arm": "personalized",
                           "segment": "anon"})
        self.assertEqual(body["counted"], 1)
        line = self._audit()[-1]
        self.assertEqual(line["event"], "ui_click")
        self.assertIsNone(line["user_id"])
        self.assertNotIn("victim", json.dumps(line))
        self.assertEqual(set(line["declared"]), {"render_id", "arm", "segment"})

    def test_user_id_with_a_valid_token_is_audited_and_arm_is_the_servers(self):
        token = sign_user_token(SECRET, "alice", "acme")
        server_arm = self._arm_of("alice")
        wrong_arm = "control" if server_arm == "personalized" else "personalized"
        self._post({"event_type": "click", "zone_id": "home", "user_id": "alice",
                    "render_id": "r1", "arm": wrong_arm}, token=token)
        line = self._audit()[-1]
        self.assertEqual(line["user_id"], "alice")
        self.assertEqual(line["arm"], server_arm)
        self.assertEqual(line["declared"], ["render_id"])

        arm_stats = self._stats()["arms"][server_arm]
        self.assertEqual(arm_stats["click"], 1)
        self.assertEqual(arm_stats["verified"], {"click": 1})

    def test_token_for_someone_else_does_not_name_them(self):
        token = sign_user_token(SECRET, "mallory", "acme")
        self._post({"event_type": "impression", "zone_id": "home", "user_id": "alice"},
                   token=token)
        self.assertIsNone(self._audit()[-1]["user_id"])

    def test_anonymous_events_still_count_as_unverified(self):
        self._post({"event_type": "impression", "zone_id": "home", "arm": "personalized"})
        self._post({"event_type": "click", "zone_id": "home", "arm": "personalized"})
        arm_stats = self._stats()["arms"]["personalized"]
        self.assertEqual(arm_stats["impression"], 1)
        self.assertEqual(arm_stats["click"], 1)
        self.assertEqual(arm_stats["verified"], {})

    def test_dev_open_admits_ids_but_never_a_placeholder(self):
        settings.user_token_secrets = ""
        settings.genui_dev_open = True
        auth_deps._user_token_verifier = None
        self._post({"event_type": "impression", "zone_id": "home", "user_id": "anonymous"})
        self.assertIsNone(self._audit()[-1]["user_id"])
        self._post({"event_type": "impression", "zone_id": "home", "user_id": "alice"})
        self.assertEqual(self._audit()[-1]["user_id"], "alice")

    def test_two_salts_two_buckets_and_stats_name_the_experiment(self):
        self._post({"event_type": "impression", "zone_id": "home", "arm": "control"})
        settings.holdout_salt = "exp-b"
        self._post({"event_type": "impression", "zone_id": "home", "arm": "control"})
        self._post({"event_type": "impression", "zone_id": "home", "arm": "control"})

        stats = self._stats()
        self.assertEqual(stats["experiment"], "exp-b")
        self.assertEqual(stats["unit"], "event")
        self.assertEqual(stats["arms"]["control"]["impression"], 2)

        settings.holdout_salt = "exp-a"
        self.assertEqual(self._stats()["arms"]["control"]["impression"], 1)


class TestMetricsStorePerExperiment(unittest.TestCase):
    def test_experiments_do_not_mix(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "exp-a", "control", "impression", 5)
            await store.record("acme", "home", "exp-b", "control", "impression", 2)
            return await store.stats("acme", "home", "exp-a"), await store.stats("acme", "home", "exp-b")

        a, b = run(scenario())
        self.assertEqual(a["arms"]["control"]["impression"], 5)
        self.assertEqual(b["arms"]["control"]["impression"], 2)
        self.assertEqual(a["experiment"], "exp-a")

    def test_redis_key_carries_the_experiment(self):
        store = MetricsStore()
        self.assertNotEqual(
            store._key("acme", "home", "exp-a", "control"),
            store._key("acme", "home", "exp-b", "control"),
        )

    def test_significance_is_labelled_indicative_on_events(self):
        store = MetricsStore()

        async def scenario():
            await store.record("acme", "home", "e", "personalized", "impression", 500)
            await store.record("acme", "home", "e", "personalized", "click", 60)
            await store.record("acme", "home", "e", "control", "impression", 500)
            await store.record("acme", "home", "e", "control", "click", 30)
            return await store.stats("acme", "home", "e")

        stats = run(scenario())
        self.assertEqual(stats["unit"], "event")
        self.assertTrue(stats["significance"]["indicative"])


# The render line: the page is what the client says it is on

@unittest.skipUnless(HAVE_APP_DEPS, "requires fastapi (backend venv)")
class TestRenderAuditPage(unittest.TestCase):
    def test_page_without_query_string_and_marked_declared(self):
        audit = _RecordingAudit()
        saved = auth_deps._audit_logger
        auth_deps._audit_logger = audit
        try:
            auth = AuthContext(tenant="acme", is_admin=False, key_fingerprint="cfp")
            request = zone_router.ZoneRenderRequest(
                zone_id="hero", base_prompt="x",
                current_page="https://shop.example/checkout?email=a%40b.it#pay",
            )
            payload = {"render_id": "r1", "components": [], "meta": {}}
            zone_router._audit_render(auth, request, payload, {"status": "miss"})
        finally:
            auth_deps._audit_logger = saved

        line = audit.lines[0]
        self.assertEqual(line["page"], "https://shop.example/checkout")
        self.assertEqual(line["declared"], ["page"])


if __name__ == "__main__":
    unittest.main()
