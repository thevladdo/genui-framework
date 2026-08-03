"""
pros_cons: the degraded shapes, and the sanitization of item text.

This type is falsifiable by structure alone. An empty column rendered as
half a grid says "there are no drawbacks" without a single false word
being written, so the shapes are the contract:

- one populated side renders as one full-width column, a deliberate shape;
- neither side populated is not a component at all;
- blank entries never become empty bullets that read as withheld items.
"""

import unittest

from schemas import component_to_dict, validate_components
from utils.url_guard import UrlGuard

INPUT_TEXT = "Our docs live at https://acme.example/docs and cover the trade-offs."


def _component(**data):
    return {"type": "pros_cons", "data": data}


def _validated(component):
    valid, errors = validate_components([component])
    return valid, errors


class TestShape(unittest.TestCase):
    """What survives validation, and in which shape."""

    def test_both_sides_is_the_full_form(self):
        valid, errors = _validated(
            _component(title="Serverless", pros=["Cheap to run"], cons=["Cold starts"])
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(valid), 1)

    def test_one_side_only_is_valid(self):
        valid, errors = _validated(_component(pros=["Cheap to run", "Scales with traffic"]))
        self.assertEqual(errors, [])
        self.assertEqual(component_to_dict(valid[0])["data"]["cons"], [])

    def test_neither_side_is_not_a_component(self):
        valid, errors = _validated(_component(title="Serverless", pros=[], cons=[]))
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_blank_entries_never_become_empty_bullets(self):
        valid, errors = _validated(_component(pros=["Cheap"], cons=["   ", ""]))
        self.assertEqual(errors, [])
        data = component_to_dict(valid[0])["data"]
        self.assertEqual(data["cons"], [])
        self.assertEqual(data["pros"], ["Cheap"])

    def test_only_blank_entries_is_not_a_component(self):
        valid, _ = _validated(_component(pros=[" "], cons=[""]))
        self.assertEqual(valid, [])

    def test_eleven_items_on_one_side_is_refused(self):
        valid, errors = _validated(
            _component(pros=[f"Benefit {i}" for i in range(11)], cons=["One limit"])
        )
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_headings_are_optional_and_carried_through(self):
        valid, _ = _validated(
            _component(pros_heading="Vantaggi", cons_heading="Limiti", pros=["A"], cons=["B"])
        )
        data = component_to_dict(valid[0])["data"]
        self.assertEqual(data["pros_heading"], "Vantaggi")
        self.assertEqual(data["cons_heading"], "Limiti")


class TestItemSanitization(unittest.TestCase):
    """Item text goes through the URL guard like every other displayed string."""

    def _guard(self):
        guard = UrlGuard(enforce_whitelist=True)
        guard.allow_from_text(INPUT_TEXT)
        return guard

    def test_invented_link_in_an_item_does_not_survive(self):
        guard = self._guard()
        components, removed = guard.sanitize_components([
            _component(
                pros=["Read the [docs](https://acme.example/docs)"],
                cons=["Grab the [deal](https://evil.example/phish)"],
            )
        ])
        data = components[0]["data"]
        self.assertEqual(data["pros"], ["Read the [docs](https://acme.example/docs)"])
        self.assertEqual(data["cons"], ["Grab the deal"])
        self.assertIn("https://evil.example/phish", removed)

    def test_item_that_is_only_an_invented_url_leaves_no_empty_bullet(self):
        guard = self._guard()
        components, removed = guard.sanitize_components([
            _component(pros=["Cheap to run", "https://evil.example/x"])
        ])
        self.assertEqual(components[0]["data"]["pros"], ["Cheap to run"])
        self.assertIn("https://evil.example/x", removed)

    def test_dangerous_scheme_in_an_item_is_removed(self):
        guard = self._guard()
        components, _ = guard.sanitize_components([
            _component(pros=["Click [here](javascript:alert(1))"], cons=["A limit"])
        ])
        self.assertNotIn("javascript:", str(components[0]["data"]["pros"]))

    def test_plain_string_lists_of_other_types_are_covered_too(self):
        guard = self._guard()
        components, removed = guard.sanitize_components([{
            "type": "pricing_cards",
            "data": {"plans": [{
                "name": "Pro",
                "price": "$9",
                "features": ["See the [offer](https://evil.example/x)"],
            }]},
        }])
        self.assertEqual(
            components[0]["data"]["plans"][0]["features"], ["See the offer"]
        )
        self.assertIn("https://evil.example/x", removed)


if __name__ == "__main__":
    unittest.main()
