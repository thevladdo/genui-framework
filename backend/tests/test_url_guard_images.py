"""
Image URLs are whitelisted separately from link URLs, so a pinned link
cannot be reused as an <img src> (a broken image). When the guard strips
an image that a variant required, the component degrades to its text-only
form instead of leaving an image-shaped hole.

Pure tests (no fastapi): runnable with `python3 -m unittest discover -s tests`.
"""

import unittest

from schemas.components import downgrade_image_variants
from utils.url_guard import UrlGuard, is_image_field, looks_like_image_url


class TestImageFieldClassification(unittest.TestCase):
    def test_image_fields(self):
        for key in ("src", "image", "image_url", "avatar_url", "hero_image",
                    "photo", "thumbnail", "backgroundImage"):
            self.assertTrue(is_image_field(key), key)

    def test_link_fields(self):
        for key in ("url", "href", "link", "cta_url", "primary_url"):
            self.assertFalse(is_image_field(key), key)

    def test_looks_like_image_url(self):
        for url in ("/img/a.jpg", "https://cdn.example/x.PNG", "/h.webp?v=2",
                    "https://x/y.svg#id"):
            self.assertTrue(looks_like_image_url(url), url)
        for url in ("/pricing", "https://example.com/plans", None, ""):
            self.assertFalse(looks_like_image_url(url), url)


class TestImageWhitelistSeparation(unittest.TestCase):
    def test_link_is_not_a_valid_image(self):
        guard = UrlGuard(allowed_urls=["/pricing"])
        self.assertTrue(guard.is_allowed("/pricing"))                    # as link
        self.assertFalse(guard.is_allowed("/pricing", as_image=True))    # as image

    def test_image_by_extension_is_valid_as_both(self):
        guard = UrlGuard(allowed_urls=["/img/hero.jpg"])
        self.assertTrue(guard.is_allowed("/img/hero.jpg"))
        self.assertTrue(guard.is_allowed("/img/hero.jpg", as_image=True))

    def test_allow_image_marks_extensionless_url_usable_as_image(self):
        guard = UrlGuard()
        guard.allow_image("https://cdn.example/asset/abc123")
        self.assertTrue(guard.is_allowed("https://cdn.example/asset/abc123", as_image=True))
        self.assertTrue(guard.is_allowed("https://cdn.example/asset/abc123"))  # also a link

    def test_whitelist_off_allows_any_scheme_safe_url_as_image(self):
        guard = UrlGuard(enforce_whitelist=False)
        self.assertTrue(guard.is_allowed("https://anything/x", as_image=True))


class TestSanitizeStripsLinkAsImage(unittest.TestCase):
    def test_hero_image_url_that_is_a_link_is_stripped(self):
        guard = UrlGuard(allowed_urls=["https://example.com/pricing"])
        components = [{
            "type": "hero_banner",
            "data": {
                "variant": "split",
                "headline": "Ship faster",
                "image_url": "https://example.com/pricing",
                "primary_cta": {"label": "See pricing", "url": "https://example.com/pricing"},
            },
        }]
        kept, removed = guard.sanitize_components(components)
        data = kept[0]["data"]
        self.assertNotIn("image_url", data)                       # stripped: link is no image
        self.assertEqual(data["primary_cta"]["url"], "https://example.com/pricing")  # link kept
        self.assertIn("https://example.com/pricing", removed)

    def test_bento_real_image_survives_but_link_as_image_does_not(self):
        guard = UrlGuard(allowed_urls=["/pricing"])
        guard.allow_image("/img/card.png")
        components = [{
            "type": "bento",
            "data": {"cards": [
                {"title": "A", "image": "/img/card.png", "link": "/pricing"},
                {"title": "B", "image": "/pricing"},
            ]},
        }]
        kept, _ = guard.sanitize_components(components)
        cards = kept[0]["data"]["cards"]
        self.assertEqual(cards[0]["image"], "/img/card.png")   # real image kept
        self.assertEqual(cards[0]["link"], "/pricing")         # link kept
        self.assertNotIn("image", cards[1])                    # link-as-image stripped


class TestDowngradeImageVariants(unittest.TestCase):
    def test_hero_split_without_image_becomes_centered(self):
        comps = [{"type": "hero_banner", "data": {"variant": "split", "headline": "H"}}]
        downgrade_image_variants(comps)
        self.assertEqual(comps[0]["data"]["variant"], "centered")

    def test_hero_split_with_image_stays_split(self):
        comps = [{"type": "hero_banner",
                  "data": {"variant": "split", "headline": "H", "image_url": "/a.jpg"}}]
        downgrade_image_variants(comps)
        self.assertEqual(comps[0]["data"]["variant"], "split")

    def test_steps_with_image_but_no_step_image_becomes_text_only(self):
        comps = [{"type": "steps_section",
                  "data": {"layout": "with-image", "steps": [{"title": "s1"}]}}]
        downgrade_image_variants(comps)
        self.assertEqual(comps[0]["data"]["layout"], "text-only")

    def test_content_grid_item_downgrades_per_item(self):
        comps = [{"type": "content_grid", "data": {"items": [
            {"title": "a", "layout": "with-image"},
            {"title": "b", "layout": "with-image", "image_url": "/b.png"},
        ]}}]
        downgrade_image_variants(comps)
        items = comps[0]["data"]["items"]
        self.assertEqual(items[0]["layout"], "text-only")   # no image -> degraded
        self.assertEqual(items[1]["layout"], "with-image")  # has image -> kept

    def test_tabs_content_downgrades(self):
        comps = [{"type": "tabs_feature", "data": {"tabs": [
            {"label": "T", "content": {"layout": "with-image", "title": "x"}},
        ]}}]
        downgrade_image_variants(comps)
        self.assertEqual(comps[0]["data"]["tabs"][0]["content"]["layout"], "text-only")


class TestGuardPlusDowngradeEndToEnd(unittest.TestCase):
    def test_hero_with_link_as_image_degrades_to_centered(self):
        """The reported case: one pinned link, hero rendered as split with the
        link as its image. Guard strips the image, downgrade fixes the variant."""
        guard = UrlGuard(allowed_urls=["https://example.com/pricing"])
        components = [{
            "type": "hero_banner",
            "data": {
                "variant": "split",
                "headline": "Ship faster",
                "image_url": "https://example.com/pricing",
                "primary_cta": {"label": "See pricing", "url": "https://example.com/pricing"},
            },
        }]
        kept, _ = guard.sanitize_components(components)
        kept = downgrade_image_variants(kept)
        data = kept[0]["data"]
        self.assertEqual(data["variant"], "centered")
        self.assertNotIn("image_url", data)
        self.assertEqual(data["primary_cta"]["url"], "https://example.com/pricing")


if __name__ == "__main__":
    unittest.main()
