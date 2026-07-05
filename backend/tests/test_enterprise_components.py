"""
Tests for the enterprise section components (schemas + URL guard).
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from schemas import validate_components, component_to_dict
from schemas.registry import register_component_type
from utils.url_guard import UrlGuard

HERO = {
    "type": "hero_banner",
    "data": {
        "variant": "split",
        "headline": "Insurance that adapts",
        "primary_cta": {"label": "Get a quote", "url": "/quote"},
        "image_url": "/img/hero.jpg",
    },
}

VALID = [
    {
        "type": "tabs_feature",
        "data": {
            "heading": "Compare plans",
            "tabs": [
                {"label": "Base", "content": {"layout": "text-only", "title": "Base plan"}},
                {
                    "label": "Pro",
                    "icon": "⭐",
                    "content": {
                        "layout": "with-image",
                        "title": "Pro plan",
                        "image_url": "/img/pro.jpg",
                        "button": {"label": "Choose", "url": "/plans/pro"},
                    },
                },
            ],
        },
    },
    {
        "type": "steps_section",
        "data": {
            "layout": "text-only",
            "steps": [{"title": "Sign up"}, {"title": "Configure", "description": "..."}],
            "autoplay": True,
            "interval": 4000,
        },
    },
    {
        "type": "stats_banner",
        "data": {"stats": [{"value": "10M", "label": "users"}], "columns": 2},
    },
    {
        "type": "testimonial_carousel",
        "data": {"testimonials": [{"quote": "Great.", "name": "Ada L."}]},
    },
    {
        "type": "pricing_cards",
        "data": {
            "variant": "detailed",
            "plans": [
                {"name": "Free", "price": "$0", "features": ["A"]},
                {"name": "Pro", "price": "$29", "period": "mo", "features": ["A", "B"],
                 "highlighted": True, "cta": {"label": "Buy", "url": "/buy"}},
            ],
        },
    },
    {
        "type": "content_grid",
        "data": {
            "items": [
                {"layout": "with-image", "title": "Post", "image_url": "/img/p.jpg"},
                {"layout": "text-only", "title": "Note", "category": "News"},
            ],
        },
    },
    HERO,
]


class TestEnterpriseSchemas(unittest.TestCase):
    def test_all_valid_components_pass(self):
        valid, errors = validate_components(VALID)
        self.assertEqual(errors, [])
        self.assertEqual(len(valid), len(VALID))

    def test_round_trip_wire_format(self):
        valid, _ = validate_components([HERO])
        wire = component_to_dict(valid[0])
        self.assertEqual(wire["type"], "hero_banner")
        self.assertEqual(wire["data"]["primary_cta"]["url"], "/quote")

    def test_image_coherence_hero_split_requires_image(self):
        broken = {"type": "hero_banner", "data": {"variant": "split", "headline": "X"}}
        valid, errors = validate_components([broken])
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)

    def test_image_coherence_tab_content(self):
        broken = {
            "type": "tabs_feature",
            "data": {
                "heading": "H",
                "tabs": [{"label": "T", "content": {"layout": "with-image", "title": "X"}}],
            },
        }
        valid, errors = validate_components([broken])
        self.assertEqual(valid, [])

    def test_image_coherence_content_grid_item(self):
        broken = {
            "type": "content_grid",
            "data": {"items": [{"layout": "with-image", "title": "No image"}]},
        }
        valid, errors = validate_components([broken])
        self.assertEqual(valid, [])

    def test_one_bad_component_does_not_kill_the_rest(self):
        broken = {"type": "stats_banner", "data": {"stats": []}}
        valid, errors = validate_components([HERO, broken])
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 1)

    def test_new_types_are_reserved_builtins(self):
        with self.assertRaises(ValueError):
            register_component_type("hero_banner", {"type": "object"})


class TestEnterpriseUrlGuard(unittest.TestCase):
    def test_invented_image_url_stripped(self):
        guard = UrlGuard(allowed_urls=["/img/hero.jpg", "/quote"])
        valid, _ = validate_components([HERO])
        components = [component_to_dict(c) for c in valid]
        sanitized, removed = guard.sanitize_components(components)
        # Whitelisted URLs survive
        data = sanitized[0]["data"]
        self.assertEqual(data["image_url"], "/img/hero.jpg")
        self.assertEqual(data["primary_cta"]["url"], "/quote")
        self.assertEqual(removed, [])

    def test_non_whitelisted_urls_removed_recursively(self):
        guard = UrlGuard(allowed_urls=[])
        valid, _ = validate_components([HERO])
        components = [component_to_dict(c) for c in valid]
        sanitized, removed = guard.sanitize_components(components)
        data = sanitized[0]["data"]
        self.assertNotIn("image_url", data)
        self.assertNotIn("url", data["primary_cta"])
        self.assertIn("/img/hero.jpg", removed)
        self.assertIn("/quote", removed)


if __name__ == "__main__":
    unittest.main()
