"""
Tests for the URL guard (whitelist + scheme sanitization).
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from utils.url_guard import UrlGuard, extract_urls, normalize_url


class TestExtractUrls(unittest.TestCase):
    def test_absolute_urls(self):
        text = 'See https://example.com/page and (https://other.org/x?id=1).'
        urls = extract_urls(text)
        self.assertIn("https://example.com/page", urls)
        self.assertIn("https://other.org/x?id=1", urls)

    def test_relative_urls(self):
        text = 'ID 0: "Title" (Link: /articles/green-energy, Img: /img/a.jpg)'
        urls = extract_urls(text)
        self.assertIn("/articles/green-energy", urls)
        self.assertIn("/img/a.jpg", urls)

    def test_empty_text(self):
        self.assertEqual(extract_urls(None), set())
        self.assertEqual(extract_urls(""), set())


class TestSchemeRules(unittest.TestCase):
    """Dangerous schemes are blocked even with the whitelist disabled."""

    def setUp(self):
        self.guard = UrlGuard(enforce_whitelist=False)

    def test_dangerous_schemes_blocked(self):
        for url in (
            "javascript:alert(1)",
            "JAVASCRIPT:alert(1)",
            "data:text/html;base64,xxx",
            "vbscript:foo",
            "file:///etc/passwd",
            "blob:https://x",
        ):
            self.assertFalse(self.guard.is_allowed(url), url)

    def test_safe_schemes_allowed_without_whitelist(self):
        for url in ("https://example.com", "http://example.com", "/relative/path", "#anchor"):
            self.assertTrue(self.guard.is_allowed(url), url)

    def test_unknown_scheme_blocked(self):
        self.assertFalse(self.guard.is_allowed("ftp://example.com"))
        self.assertFalse(self.guard.is_allowed("customscheme:payload"))


class TestWhitelist(unittest.TestCase):
    def test_only_input_urls_survive(self):
        guard = UrlGuard(allowed_urls=["https://example.com/a", "/local/b"])
        self.assertTrue(guard.is_allowed("https://example.com/a"))
        self.assertTrue(guard.is_allowed("/local/b"))
        self.assertFalse(guard.is_allowed("https://example.com/invented"))
        self.assertFalse(guard.is_allowed("/invented"))

    def test_trailing_slash_normalized(self):
        guard = UrlGuard(allowed_urls=["https://example.com/a/"])
        self.assertTrue(guard.is_allowed("https://example.com/a"))

    def test_allow_from_text(self):
        guard = UrlGuard()
        guard.allow_from_text("Available: /products/trains and https://docs.example.com/api")
        self.assertTrue(guard.is_allowed("/products/trains"))
        self.assertTrue(guard.is_allowed("https://docs.example.com/api"))

    def test_check_records_removed(self):
        guard = UrlGuard(allowed_urls=["/ok"])
        self.assertEqual(guard.check("/ok"), "/ok")
        self.assertIsNone(guard.check("/bad"))
        self.assertIn("/bad", guard.removed_urls)


class TestSanitizeComponents(unittest.TestCase):
    def test_bento_invented_link_stripped_card_survives(self):
        guard = UrlGuard(allowed_urls=["/real"])
        components = [{
            "type": "bento",
            "data": {"cards": [
                {"title": "Real", "link": "/real"},
                {"title": "Fake", "link": "/invented", "image": "https://evil.test/x.png"},
            ], "columns": 2},
        }]
        sanitized, removed = guard.sanitize_components(components)
        cards = sanitized[0]["data"]["cards"]
        self.assertEqual(cards[0]["link"], "/real")
        self.assertNotIn("link", cards[1])
        self.assertNotIn("image", cards[1])
        self.assertEqual(set(removed), {"/invented", "https://evil.test/x.png"})

    def test_button_without_valid_url_dropped(self):
        guard = UrlGuard(allowed_urls=["/start"])
        components = [{
            "type": "buttons",
            "data": {"buttons": [
                {"label": "Go", "url": "/start"},
                {"label": "Evil", "url": "javascript:alert(1)"},
            ]},
        }]
        sanitized, removed = guard.sanitize_components(components)
        buttons = sanitized[0]["data"]["buttons"]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["label"], "Go")

    def test_all_buttons_dropped_removes_component(self):
        guard = UrlGuard(allowed_urls=[])
        components = [{
            "type": "buttons",
            "data": {"buttons": [{"label": "X", "url": "/invented"}]},
        }]
        sanitized, _ = guard.sanitize_components(components)
        self.assertEqual(sanitized, [])

    def test_markdown_links_collapse_to_text(self):
        guard = UrlGuard(allowed_urls=["/ok"])
        components = [{
            "type": "text",
            "data": {"content": "Visit [good](/ok) and [bad](https://evil.test)."},
        }]
        sanitized, removed = guard.sanitize_components(components)
        content = sanitized[0]["data"]["content"]
        self.assertIn("[good](/ok)", content)
        self.assertNotIn("evil.test", content)
        self.assertIn("bad", content)
        self.assertIn("https://evil.test", removed)

    def test_chart_untouched(self):
        guard = UrlGuard(allowed_urls=[])
        components = [{
            "type": "chart",
            "data": {"chart_type": "bar", "data": [{"label": "a", "value": 1}]},
        }]
        sanitized, removed = guard.sanitize_components(components)
        self.assertEqual(len(sanitized), 1)
        self.assertEqual(removed, [])


class TestNormalizeUrl(unittest.TestCase):
    def test_strips_trailing_punctuation_and_slash(self):
        self.assertEqual(normalize_url("https://x.com/a/."), "https://x.com/a")
        self.assertEqual(normalize_url("/a/"), "/a")


if __name__ == "__main__":
    unittest.main()
