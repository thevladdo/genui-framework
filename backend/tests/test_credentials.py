"""
A key that only looks valid is found before traffic is: each provider is asked whether it accepts the key and knows the model.

Pure stdlib with a scripted probe: runs with the shell python as well as in the backend venv.
"""

import asyncio
import unittest
from types import SimpleNamespace

from llm import credentials


def _settings(**overrides):
    base = dict(
        llm_provider="openai", openai_api_key="sk-good", anthropic_api_key=None, google_api_key=None,
        openai_base_url=None, response_model="gpt-4o-mini", profile_model="gpt-4o-mini", context_model="gpt-4o-mini",
        embedding_provider="openai", embedding_model="text-embedding-3-small", embedding_api_key=None,
        embedding_base_url=None, embedding_dimensions=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Status(Exception):
    def __init__(self, status_code, message="error"):
        super().__init__(message)
        self.status_code = status_code


def _probe(verdicts):
    """verdicts: (api_key, model) -> exception to raise; records every call."""
    calls = []

    async def probe(provider, model, api_key, base_url):
        calls.append((provider, model, api_key, base_url))
        error = verdicts.get((api_key, model))
        if error:
            raise error

    probe.calls = calls
    return probe


def _check(settings, probe):
    return asyncio.run(credentials.check(settings, probe=probe))


class TestVerdicts(unittest.TestCase):
    def test_accepted_keys_are_no_problem(self):
        self.assertEqual(_check(_settings(), _probe({})), [])

    def test_a_rejected_key_names_the_roles_and_the_key_variable(self):
        problems = _check(_settings(openai_api_key="sk-bad"), _probe({
            ("sk-bad", "gpt-4o-mini"): _Status(401),
            ("sk-bad", "text-embedding-3-small"): _Status(401),
        }))
        wheres = [where for where, _ in problems]
        self.assertIn("zone, chat, profile, behavior, context, summary (OPENAI_API_KEY)", wheres)
        self.assertIn("embeddings (OPENAI_API_KEY)", wheres)
        self.assertTrue(all("rejected" in why for _, why in problems))

    def test_an_unknown_model_on_the_provider_endpoint_is_a_problem(self):
        problems = _check(_settings(llm_zone="openai:gpt-typo"), _probe({("sk-good", "gpt-typo"): _Status(404)}))
        self.assertEqual(problems, [("zone (LLM_ZONE)", "model gpt-typo is not known to openai")])

    def test_a_compatible_endpoint_without_the_models_route_is_not_judged(self):
        settings = _settings(openai_base_url="http://vllm.internal:8000/v1", openai_api_key=None)
        self.assertEqual(_check(settings, _probe({(None, "gpt-4o-mini"): _Status(404)})), [])

    def test_an_endpoint_that_does_not_answer_is_not_a_configuration_verdict(self):
        self.assertEqual(_check(_settings(), _probe({("sk-good", "gpt-4o-mini"): ConnectionError("down")})), [])

    def test_a_rejected_embedding_key_of_its_own(self):
        problems = _check(
            _settings(embedding_api_key="sk-emb-bad"),
            _probe({("sk-emb-bad", "text-embedding-3-small"): _Status(403)}),
        )
        self.assertEqual([where for where, _ in problems], ["embeddings (EMBEDDING_API_KEY)"])

    def test_each_endpoint_key_and_model_is_asked_once(self):
        probe = _probe({})
        _check(_settings(llm_profile="openai:gpt-5-nano"), probe)
        self.assertEqual(len(probe.calls), len(set(probe.calls)))
        self.assertEqual(
            sorted(model for _, model, _, _ in probe.calls),
            ["gpt-4o-mini", "gpt-5-nano", "text-embedding-3-small"],
        )

    def test_the_last_answer_is_kept_for_readiness(self):
        _check(_settings(openai_api_key="sk-bad"), _probe({("sk-bad", "gpt-4o-mini"): _Status(401)}))
        self.assertTrue(credentials.problems())
        _check(_settings(), _probe({}))
        self.assertEqual(credentials.problems(), [])


if __name__ == "__main__":
    unittest.main()
