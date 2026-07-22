"""
Schema + guard coverage for the editorial components added for studio/
agency zones: case_studies, quote, logo_wall.

Pure tests: `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from schemas.components import component_to_dict, validate_components
from utils.numeric_guard import NumericGuard
from utils.url_guard import UrlGuard, is_image_field


class TestSchemas(unittest.TestCase):
    def test_three_new_types_validate(self):
        comps = [
            {"type": "case_studies", "data": {"cases": [{"title": "Only a title"}]}},
            {"type": "quote", "data": {"quote": "Just the statement"}},
            {"type": "logo_wall", "data": {"logos": [{"image_url": "/a.svg", "alt": "A"}]}},
        ]
        valid, dropped = validate_components(comps, None)
        self.assertEqual(len(valid), 3, dropped)
        self.assertEqual(dropped, [])

    def test_case_requires_at_least_one_case_and_a_title(self):
        empty, dropped = validate_components(
            [{"type": "case_studies", "data": {"cases": []}}], None
        )
        self.assertEqual(empty, [])  # min_length 1
        no_title, _ = validate_components(
            [{"type": "case_studies", "data": {"cases": [{"summary": "x"}]}}], None
        )
        self.assertEqual(no_title, [])  # title required

    def test_logo_requires_an_image(self):
        # A logo without an image URL is meaningless; the whole component drops.
        kept, _ = validate_components(
            [{"type": "logo_wall", "data": {"logos": [{"alt": "no image"}]}}], None
        )
        self.assertEqual(kept, [])

    def test_optional_attribution_is_accepted_absent(self):
        kept, _ = validate_components(
            [{"type": "quote", "data": {"quote": "Q"}}], None
        )
        self.assertEqual(len(kept), 1)
        data = component_to_dict(kept[0])["data"]
        # exclude_none drops the optional fields entirely
        self.assertNotIn("author", data)
        self.assertNotIn("avatar_url", data)


class TestNumericGroundingMetrics(unittest.TestCase):
    def test_ungrounded_case_metric_is_removed_case_survives(self):
        comp = {
            "type": "case_studies",
            "data": {"cases": [{
                "title": "Project",
                "metrics": [
                    {"value": "40%", "label": "Faster"},
                    {"value": "999", "label": "Invented"},
                ],
            }]},
        }
        guard = NumericGuard()
        guard.allow_from_text("We shipped 40% faster than before")
        kept, removed = guard.sanitize_components([comp])
        self.assertEqual(len(kept), 1)  # case survives
        metrics = kept[0]["data"]["cases"][0]["metrics"]
        self.assertEqual([m["value"] for m in metrics], ["40%"])
        self.assertIn("999", removed)


class TestImageFields(unittest.TestCase):
    def test_new_image_fields_classified_as_images(self):
        for key in ("logo_url", "avatar_url", "image_url"):
            self.assertTrue(is_image_field(key), key)

    def test_link_cannot_fill_a_logo_or_avatar(self):
        guard = UrlGuard(allowed_urls=["/clients"])
        # /clients is a link; it must not pass as a logo image src
        self.assertTrue(guard.is_allowed("/clients"))
        self.assertFalse(guard.is_allowed("/clients", as_image=True))


if __name__ == "__main__":
    unittest.main()
