"""
Golden harness for zone renders: the regression signal for prompt/model/
engine changes.

`experiments/` measures which variant EARNS more (CTR, uplift, z-test) on
real traffic, after shipping. This harness answers the question that comes
BEFORE shipping: "after changing a prompt, a model, or the BYOK engine,
does the output still honor its structural contract on known inputs?"
It fixes the FORM and the INVARIANTS of the output, never the exact prose:

- only the expected component types appear;
- every pinned item is present in the actual components;
- no URL outside the input whitelist survives;
- no displayed number (stat value, price, chart point) outside the
  input grounding survives;
- every component re-validates cleanly (schema + layout coherence).

Default run: deterministic, recorded LLM responses from tests/golden/*.json
(no key, no network, no cost — part of the normal unittest suite). The
recorded responses are deliberately adversarial (an invented URL, a missing
pinned item, an incoherent layout, an unknown type) so the harness goes red
if any link of the validate -> URL-guard -> pinned chain stops working.

Live mode (optional): vet a real BYOK engine before promoting a change.
It uses whatever the environment configures (LLM_PROVIDER, keys,
OPENAI_BASE_URL, ...) and checks the same invariants on fresh output:

    GENUI_GOLDEN_LIVE=1 ./venv/bin/python -m unittest tests.test_golden_zone -v

Add GENUI_GOLDEN_RECORD=1 to also rewrite each fixture's llm_response with
the fresh generation (how goldens are regenerated).

Adding a fixture = dropping a JSON file in tests/golden/ with: "request"
(ZoneRenderRequest fields), "retrieved" (recorded RAG results),
"invariants" {"allowed_types": [...]} (optional, defaults to all built-ins)
and "llm_response" (the recorded model envelope). No new code needed.
"""

import asyncio
import json
import os
import unittest
from pathlib import Path

from schemas import BUILTIN_TYPES, validate_components
from utils.numeric_guard import NumericGuard
from utils.url_guard import (
    UrlGuard,
    _URL_FIELD_NAMES,
    _URL_FIELD_SUFFIXES,
    extract_urls,
    normalize_url,
)

try:  # app-level deps: available in the backend venv, not in the shell python
    from agents.zone_agent import ZoneAgent, ZoneRenderRequest
    from config import settings
    from llm import create_llm_client
    HAVE_APP_DEPS = True
except ImportError:
    HAVE_APP_DEPS = False

GOLDEN_DIR = Path(__file__).parent / "golden"
LIVE = os.environ.get("GENUI_GOLDEN_LIVE") == "1"
RECORD = os.environ.get("GENUI_GOLDEN_RECORD") == "1"



# Invariant checker (pure: runs everywhere, reused by recorded and live)
def _input_guard(fixture):
    """
    The whitelist DEFINITION: every URL legitimately present in the input.
    Mirrors ZoneAgent._build_url_guard but is rebuilt independently from
    the fixture, so a pipeline that forgets to guard still goes red here.
    """
    request = fixture["request"]
    guard = UrlGuard(enforce_whitelist=True)
    guard.allow_from_text(request.get("base_prompt"))
    guard.allow_from_text(request.get("context_prompt"))
    for item in request.get("pinned_content") or []:
        guard.allow(item.get("url"), item.get("id"))
        for value in (item.get("metadata") or {}).values():
            if isinstance(value, str):
                guard.allow_from_text(value)
    guard.allow(request.get("current_page"))
    for value in (request.get("page_metadata") or {}).values():
        if isinstance(value, str):
            guard.allow_from_text(value)
    for doc in fixture.get("retrieved") or []:
        metadata = doc.get("metadata") or {}
        guard.allow(metadata.get("url"), metadata.get("image"))
        guard.allow_from_text(doc.get("content"))
    return guard


def _input_numeric_guard(fixture):
    """
    The grounding DEFINITION: every number legitimately present in the
    input. Mirrors ZoneAgent._build_numeric_guard but is rebuilt
    independently from the fixture, like _input_guard for URLs.
    """
    request = fixture["request"]
    guard = NumericGuard(enforce=True)
    guard.allow_from_text(request.get("base_prompt"))
    guard.allow_from_text(request.get("context_prompt"))
    for item in request.get("pinned_content") or []:
        guard.allow_from_text(json.dumps(item, default=str))
    guard.allow_from_text(request.get("current_page"))
    guard.allow_from_text(json.dumps(request.get("page_metadata") or {}, default=str))
    for doc in fixture.get("retrieved") or []:
        guard.allow_from_text(doc.get("content"))
        guard.allow_from_text(json.dumps(doc.get("metadata") or {}, default=str))
    return guard


def _displayed_numbers(components):
    """The numeric claims a render displays: stat values, prices, chart points."""
    for component in components:
        data = component.get("data", {})
        ctype = component.get("type")
        if ctype == "stats_banner":
            yield from (s.get("value") for s in data.get("stats", []))
        elif ctype == "pricing_cards":
            yield from (p.get("price") for p in data.get("plans", []))
        elif ctype == "chart":
            yield from (p.get("value") for p in data.get("data", []))


def _output_urls(node, key=None):
    """
    Every URL in the rendered components: URL-named fields are taken
    whole (relative paths included); other strings are scanned for
    absolute URLs only (relative extraction from prose would flag
    innocent values like a pricing period "/month").
    """
    urls = set()
    if isinstance(node, dict):
        for child_key, value in node.items():
            urls |= _output_urls(value, child_key)
    elif isinstance(node, list):
        for item in node:
            urls |= _output_urls(item, key)
    elif isinstance(node, str) and node.strip():
        lowered = (key or "").lower()
        if lowered in _URL_FIELD_NAMES or lowered.endswith(_URL_FIELD_SUFFIXES):
            urls.add(node)
        else:
            urls |= {u for u in extract_urls(node) if u.startswith(("http://", "https://"))}
    return urls


def check_invariants(fixture, components):
    """Return human-readable violations of the golden contract (empty = green)."""
    violations = []
    request = fixture["request"]

    # 1. Component types: only the expected vocabulary may appear
    allowed = set(fixture.get("invariants", {}).get("allowed_types") or BUILTIN_TYPES)
    for component in components:
        ctype = component.get("type")
        if ctype not in allowed:
            violations.append(f"component type {ctype!r} not in allowed set {sorted(allowed)}")

    # 2. Schema + layout coherence: the output must re-validate cleanly
    _, errors = validate_components(components)
    violations.extend(f"schema/coherence: {error}" for error in errors)

    # 3. URL whitelist: every URL in the output existed in the input
    guard = _input_guard(fixture)
    for url in sorted(_output_urls(components)):
        if not guard.is_allowed(url):
            violations.append(f"URL outside input whitelist: {url}")

    # 4. Numeric grounding: displayed numbers trace to the input
    numeric_guard = _input_numeric_guard(fixture)
    for value in _displayed_numbers(components):
        if value is not None and not numeric_guard.is_grounded(value):
            violations.append(f"number outside input grounding: {value}")

    # 5. Pinned presence: verified on the actual output, not on claims
    urls = {normalize_url(u) for u in _output_urls(components)}
    serialized = json.dumps(components).lower()
    for item in request.get("pinned_content") or []:
        url = item.get("url")
        title = (item.get("title") or "").strip().lower()
        if url and normalize_url(url) in urls:
            continue
        if title and title in serialized:
            continue
        violations.append(f"pinned item missing from output: {url or title}")

    return violations


class TestInvariantChecker(unittest.TestCase):
    """Red-first: each invariant must flag the exact output it exists to catch."""

    def _fixture(self, allowed_types=("bento", "text")):
        return {
            "request": {
                "zone_id": "z",
                "base_prompt": "Our catalog: https://ok.example/products",
                "pinned_content": [{"title": "Spring sale", "url": "https://ok.example/sale"}],
                "max_items": 4,
            },
            "retrieved": [],
            "invariants": {"allowed_types": list(allowed_types)},
        }

    def _clean_output(self):
        return [{"type": "bento", "data": {"columns": 2, "cards": [
            {"title": "Spring sale", "link": "https://ok.example/sale"},
            {"title": "Catalog", "link": "https://ok.example/products"},
        ]}}]

    def test_clean_output_has_no_violations(self):
        self.assertEqual(check_invariants(self._fixture(), self._clean_output()), [])

    def test_invented_url_is_flagged(self):
        components = self._clean_output()
        components[0]["data"]["cards"][1]["link"] = "https://evil.example/phish"
        violations = check_invariants(self._fixture(), components)
        self.assertTrue(any("whitelist" in v for v in violations), violations)

    def test_absolute_url_in_prose_is_flagged(self):
        components = self._clean_output() + [{"type": "text", "data": {
            "content": "Order now at https://evil.example/deal before midnight"}}]
        violations = check_invariants(self._fixture(), components)
        self.assertTrue(any("evil.example/deal" in v for v in violations), violations)

    def test_missing_pinned_is_flagged(self):
        components = [{"type": "bento", "data": {"cards": [
            {"title": "Catalog", "link": "https://ok.example/products"}]}}]
        violations = check_invariants(self._fixture(), components)
        self.assertTrue(any("pinned" in v for v in violations), violations)

    def test_disallowed_type_is_flagged(self):
        # buttons is a VALID built-in: only the type invariant may fire
        components = self._clean_output() + [{"type": "buttons", "data": {
            "buttons": [{"label": "Go", "url": "https://ok.example/products"}]}}]
        violations = check_invariants(self._fixture(), components)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("not in allowed set", violations[0])

    def test_ungrounded_number_is_flagged(self):
        fixture = self._fixture(allowed_types=("bento", "stats_banner"))
        components = self._clean_output() + [{"type": "stats_banner", "data": {
            "stats": [{"value": "97%", "label": "Satisfaction"}]}}]
        violations = check_invariants(fixture, components)
        self.assertTrue(any("grounding" in v for v in violations), violations)

    def test_incoherent_layout_is_flagged(self):
        fixture = self._fixture(allowed_types=("bento", "content_grid"))
        components = self._clean_output() + [{"type": "content_grid", "data": {
            "items": [{"layout": "with-image", "title": "No image here"}]}}]
        violations = check_invariants(fixture, components)
        self.assertTrue(any("schema/coherence" in v for v in violations), violations)



# The harness: recorded fixtures through the REAL pipeline
class _RecordedLLM:
    """Replays the fixture's recorded model response (no key, no network)."""

    def __init__(self, envelope):
        self._text = json.dumps(envelope)

    async def complete_json(self, system, user, json_schema=None):
        return self._text


class _RecordingLLM:
    """Delegates to a real client and keeps the raw text for GENUI_GOLDEN_RECORD."""

    def __init__(self, inner):
        self._inner = inner
        self.last_text = None

    async def complete_json(self, system, user, json_schema=None):
        self.last_text = await self._inner.complete_json(system, user, json_schema=json_schema)
        return self.last_text


class _FakeStore:
    """Serves the fixture's recorded RAG results."""

    def __init__(self, docs):
        class _Result:
            def __init__(self, doc):
                self.content = doc.get("content", "")
                self.metadata = doc.get("metadata") or {}
                self.score = doc.get("score", 0.5)
                self.chunk_id = doc.get("chunk_id", "")

        self._results = [_Result(doc) for doc in docs]

    async def search_async(self, query=None, top_k=None, tenant=None, **kwargs):
        return self._results


def _load_fixtures():
    paths = sorted(GOLDEN_DIR.glob("*.json"))
    return [(path, json.loads(path.read_text())) for path in paths]


def _run_pipeline(fixture, llm_client):
    """Run the full public render path (validate -> URL guard -> pinned)."""
    req = fixture["request"]
    request = ZoneRenderRequest(
        zone_id=req["zone_id"],
        base_prompt=req["base_prompt"],
        context_prompt=req.get("context_prompt"),
        pinned_content=req.get("pinned_content") or [],
        preferred_component_type=req.get("preferred_component_type"),
        max_items=req.get("max_items", 6),
        user_profile=req.get("user_profile"),
        behavior_data=req.get("behavior_data"),
        current_page=req.get("current_page"),
        page_metadata=req.get("page_metadata") or {},
        tenant="golden",
        archetype=req.get("archetype") or None,
    )
    agent = ZoneAgent(
        model="golden-harness",
        vector_store=_FakeStore(fixture.get("retrieved") or []),
        llm_client=llm_client,
    )
    return asyncio.run(agent.render_zone_async(request))


class _GoldenBase(unittest.TestCase):
    def setUp(self):
        # Deterministic regardless of the operator's .env
        self._saved_whitelist = settings.url_whitelist_enabled
        settings.url_whitelist_enabled = True
        self.addCleanup(setattr, settings, "url_whitelist_enabled", self._saved_whitelist)

    def _assert_golden(self, name, fixture, result):
        # A pipeline that silently fell back never exercised the chain:
        # that must read as red, not as green-by-accident
        self.assertNotIn("Fallback render", result.reasoning,
                         f"{name}: pipeline degraded to the fallback render")
        self.assertTrue(result.components, f"{name}: empty render")
        violations = check_invariants(fixture, result.components)
        self.assertEqual(violations, [], f"{name}: " + "; ".join(violations))


@unittest.skipUnless(HAVE_APP_DEPS, "requires app deps (backend venv)")
class TestGoldenZones(_GoldenBase):
    """Deterministic golden run: recorded responses, full real pipeline."""

    def test_recorded_fixtures_hold_invariants(self):
        fixtures = _load_fixtures()
        self.assertTrue(fixtures, "no golden fixtures in tests/golden/")
        for path, fixture in fixtures:
            with self.subTest(fixture=path.stem):
                result = _run_pipeline(fixture, _RecordedLLM(fixture["llm_response"]))
                self._assert_golden(path.stem, fixture, result)


@unittest.skipUnless(LIVE and HAVE_APP_DEPS,
                     "live golden: set GENUI_GOLDEN_LIVE=1 (needs a configured provider)")
class TestGoldenZonesLive(_GoldenBase):
    """Same invariants against the REAL engine configured in the env (BYOK)."""

    def test_live_engine_holds_invariants(self):
        for path, fixture in _load_fixtures():
            with self.subTest(fixture=path.stem):
                recorder = _RecordingLLM(create_llm_client(settings.response_model))
                result = _run_pipeline(fixture, recorder)
                self._assert_golden(path.stem, fixture, result)
                if RECORD and recorder.last_text:
                    fixture["llm_response"] = json.loads(recorder.last_text)
                    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
                    print(f"\n[golden] re-recorded {path.name}")


if __name__ == "__main__":
    unittest.main()
