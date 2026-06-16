"""
Tests for the component type registry, custom component validation,
and recursive URL sanitization of custom components.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from schemas import (
    component_to_dict,
    merge_custom_types,
    register_component_type,
    unregister_component_type,
    validate_components,
)
from schemas.registry import ComponentTypeDef, validate_type_name
from utils.url_guard import UrlGuard

HERO_SCHEMA = {
    "type": "object",
    "required": ["headline"],
    "properties": {
        "headline": {"type": "string"},
        "subtitle": {"type": "string"},
        "cta_url": {"type": "string"},
    },
}


def hero_def(name="hero_banner"):
    return ComponentTypeDef(name=name, data_schema=HERO_SCHEMA, description="Hero")


class TestRegistry(unittest.TestCase):
    def tearDown(self):
        unregister_component_type("hero_banner")

    def test_register_and_merge(self):
        register_component_type("hero_banner", HERO_SCHEMA, "Hero")
        merged = merge_custom_types(None)
        self.assertIn("hero_banner", merged)

    def test_invalid_names_rejected(self):
        for bad in ("", "X", "1abc", "UPPER", "a" * 40, "has space"):
            with self.assertRaises(ValueError):
                validate_type_name(bad)

    def test_builtin_names_reserved(self):
        for builtin in ("bento", "chart", "text", "buttons"):
            with self.assertRaises(ValueError):
                register_component_type(builtin, HERO_SCHEMA)

    def test_request_components_override_global(self):
        register_component_type("hero_banner", HERO_SCHEMA, "global version")
        merged = merge_custom_types([{
            "name": "hero_banner",
            "data_schema": HERO_SCHEMA,
            "description": "request version",
        }])
        self.assertEqual(merged["hero_banner"].description, "request version")

    def test_invalid_request_entries_skipped(self):
        merged = merge_custom_types([
            {"name": "bento", "data_schema": HERO_SCHEMA},     # reserved
            {"name": "ok_type", "data_schema": "not a dict"},  # bad schema
            {"name": "good_one", "data_schema": HERO_SCHEMA},
            "not a dict",
        ])
        self.assertIn("good_one", merged)
        self.assertNotIn("bento", merged)
        self.assertNotIn("ok_type", merged)


class TestProviderSchemaExtension(unittest.TestCase):
    def test_custom_types_added_to_components_union(self):
        from schemas import zone_output_json_schema

        base = zone_output_json_schema()
        extended = zone_output_json_schema({"hero_banner": hero_def()})

        def variants(schema):
            items = schema["properties"]["components"]["items"]
            return items.get("oneOf") or items.get("anyOf") or []

        self.assertEqual(len(variants(extended)), len(variants(base)) + 1)
        added = variants(extended)[-1]
        self.assertEqual(added["properties"]["type"]["const"], "hero_banner")
        self.assertEqual(added["properties"]["data"], HERO_SCHEMA)

    def test_no_custom_types_schema_unchanged(self):
        from schemas import zone_output_json_schema
        self.assertEqual(zone_output_json_schema(), zone_output_json_schema(None))


class TestValidateCustomComponents(unittest.TestCase):
    def setUp(self):
        self.custom = {"hero_banner": hero_def()}

    def test_valid_custom_component_passes(self):
        raw = [{
            "type": "hero_banner",
            "data": {"headline": "Welcome", "cta_url": "/start"},
            "layout": {"width": "100%"},
        }]
        valid, errors = validate_components(raw, self.custom)
        self.assertEqual(errors, [])
        self.assertEqual(len(valid), 1)
        wire = component_to_dict(valid[0])
        self.assertEqual(wire["type"], "hero_banner")
        self.assertEqual(wire["data"]["headline"], "Welcome")
        self.assertEqual(wire["layout"], {"width": "100%"})

    def test_schema_violation_dropped(self):
        raw = [{"type": "hero_banner", "data": {"subtitle": "no headline"}}]
        valid, errors = validate_components(raw, self.custom)
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("hero_banner", errors[0])

    def test_unknown_type_still_dropped(self):
        raw = [{"type": "carousel", "data": {"x": 1}}]
        valid, errors = validate_components(raw, self.custom)
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)

    def test_builtins_still_work_alongside_custom(self):
        raw = [
            {"type": "text", "data": {"content": "hi"}},
            {"type": "hero_banner", "data": {"headline": "H"}},
        ]
        valid, errors = validate_components(raw, self.custom)
        self.assertEqual(len(valid), 2)
        self.assertEqual(errors, [])

    def test_custom_data_must_be_object(self):
        raw = [{"type": "hero_banner", "data": "just a string"}]
        valid, errors = validate_components(raw, self.custom)
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)


class TestCustomComponentUrlSanitization(unittest.TestCase):
    def test_url_fields_checked_recursively(self):
        guard = UrlGuard(allowed_urls=["/start", "https://cdn.example.com/h.jpg"])
        components = [{
            "type": "hero_banner",
            "data": {
                "headline": "Welcome",
                "cta_url": "/start",
                "items": [
                    {"label": "ok", "link": "https://cdn.example.com/h.jpg"},
                    {"label": "bad", "link": "https://evil.test/x"},
                ],
                "nested": {"image": "/invented.png"},
            },
        }]
        sanitized, removed = guard.sanitize_components(components)
        data = sanitized[0]["data"]
        self.assertEqual(data["cta_url"], "/start")
        self.assertEqual(data["items"][0]["link"], "https://cdn.example.com/h.jpg")
        self.assertNotIn("link", data["items"][1])
        self.assertNotIn("image", data["nested"])
        self.assertIn("https://evil.test/x", removed)
        self.assertIn("/invented.png", removed)

    def test_dangerous_scheme_in_any_string_field(self):
        guard = UrlGuard(enforce_whitelist=False)
        components = [{
            "type": "hero_banner",
            "data": {"headline": "javascript:alert(1)", "subtitle": "safe text"},
        }]
        sanitized, removed = guard.sanitize_components(components)
        self.assertNotIn("headline", sanitized[0]["data"])
        self.assertEqual(sanitized[0]["data"]["subtitle"], "safe text")

    def test_absolute_url_in_text_field_checked(self):
        guard = UrlGuard(allowed_urls=["https://ok.example.com"])
        components = [{
            "type": "hero_banner",
            "data": {"headline": "https://evil.test/phish"},
        }]
        sanitized, removed = guard.sanitize_components(components)
        self.assertNotIn("headline", sanitized[0]["data"])
        self.assertIn("https://evil.test/phish", removed)

    def test_markdown_links_in_custom_text(self):
        guard = UrlGuard(allowed_urls=["/ok"])
        components = [{
            "type": "hero_banner",
            "data": {"subtitle": "See [good](/ok) and [bad](https://evil.test)"},
        }]
        sanitized, _ = guard.sanitize_components(components)
        subtitle = sanitized[0]["data"]["subtitle"]
        self.assertIn("[good](/ok)", subtitle)
        self.assertNotIn("evil.test", subtitle)

    def test_plain_text_untouched(self):
        guard = UrlGuard(allowed_urls=[])
        components = [{
            "type": "hero_banner",
            "data": {"headline": "Plain headline", "count": 3, "flag": True},
        }]
        sanitized, removed = guard.sanitize_components(components)
        self.assertEqual(sanitized[0]["data"]["headline"], "Plain headline")
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
