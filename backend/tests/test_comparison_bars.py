"""
comparison_bars: the shape contract and the guarantee that governs it.

A comparison is the most persuasive thing the model can put on a page, so
it is also the most dangerous: an invented figure inside a comparison is
not a content mistake, it is a false commercial claim drawn with the
authority of a chart.
"""

import unittest

from schemas import component_to_dict, validate_components
from utils.numeric_guard import NumericGuard
from utils.url_guard import UrlGuard

INPUT_TEXT = (
    "Our checkout completes in 1.4 seconds. Competing suites measure 3.2 and "
    "4.8 seconds on the same hardware. Details: https://acme.example/benchmark"
)


def _bars(*specs):
    return [
        {"label": label, "value": value, "suffix": "s", **extra}
        for label, value, extra in specs
    ]


def _component(bars, **data):
    return {
        "type": "comparison_bars",
        "data": {"title": "Checkout speed", "bars": bars, **data},
    }


class TestShape(unittest.TestCase):
    """What the schema accepts, and what it refuses to render at all."""

    def _valid(self, component):
        valid, errors = validate_components([component])
        return valid, errors

    def test_two_bars_are_a_comparison(self):
        valid, errors = self._valid(
            _component(_bars(("Us", 1.4, {"highlighted": True}), ("Suite A", 3.2, {})))
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(valid), 1)

    def test_a_single_bar_is_not_a_comparison(self):
        valid, errors = self._valid(_component(_bars(("Us", 1.4, {}))))
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_seven_bars_are_refused(self):
        valid, errors = self._valid(
            _component(_bars(*[(f"Option {i}", float(i + 1), {}) for i in range(7)]))
        )
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_only_one_bar_may_be_highlighted(self):
        valid, errors = self._valid(
            _component(
                _bars(
                    ("Us", 1.4, {"highlighted": True}),
                    ("Suite A", 3.2, {"highlighted": True}),
                    ("Suite B", 4.8, {}),
                )
            )
        )
        self.assertEqual(valid, [])
        self.assertTrue(any("highlighted" in e for e in errors), errors)

    def test_no_highlight_at_all_is_a_valid_comparison(self):
        valid, errors = self._valid(
            _component(_bars(("Suite A", 3.2, {}), ("Suite B", 4.8, {})))
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(valid), 1)

    def test_callout_belongs_to_the_highlighted_bar(self):
        valid, errors = self._valid(
            _component(
                _bars(
                    ("Us", 1.4, {"highlighted": True}),
                    ("Suite A", 3.2, {"callout": "Twice as slow"}),
                )
            )
        )
        self.assertEqual(valid, [])
        self.assertTrue(any("callout" in e for e in errors), errors)

    def test_negative_value_is_refused(self):
        valid, _ = self._valid(_component(_bars(("Us", -2.0, {}), ("Suite A", 3.2, {}))))
        self.assertEqual(valid, [])


class TestGrounding(unittest.TestCase):
    """One untraceable figure takes the component, never just the bar."""

    def _guard(self):
        guard = NumericGuard(enforce=True)
        guard.allow_from_text(INPUT_TEXT)
        return guard

    def test_invented_value_drops_the_whole_comparison(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components(
            [
                _component(
                    _bars(
                        ("Us", 1.4, {"highlighted": True}),
                        ("Suite A", 3.2, {}),
                        ("Suite B", 9.9, {}),
                    )
                )
            ]
        )
        self.assertEqual(kept, [])
        self.assertIn("9.9", removed)

    def test_the_flattering_bar_is_never_dropped_on_its_own(self):
        """The failure this type exists to prevent: a trimmed comparison."""
        guard = self._guard()
        kept, _ = guard.sanitize_components(
            [
                _component(
                    _bars(
                        ("Us", 1.4, {"highlighted": True}),
                        ("Suite A", 3.2, {}),
                        ("Suite B", 7.7, {}),
                    )
                ),
                {"type": "text", "data": {"content": "Measured on identical hardware."}},
            ]
        )
        self.assertEqual([c["type"] for c in kept], ["text"])

    def test_a_grounded_comparison_survives_the_full_chain(self):
        component = _component(
            _bars(
                ("Us", 1.4, {"highlighted": True, "callout": "Fastest"}),
                ("Suite A", 3.2, {}),
                ("Suite B", 4.8, {}),
            ),
            subtitle="Median of 500 runs on identical hardware",
        )
        valid, errors = validate_components([component])
        self.assertEqual(errors, [])

        components = [component_to_dict(c) for c in valid]

        url_guard = UrlGuard(enforce_whitelist=True)
        url_guard.allow_from_text(INPUT_TEXT)
        components, removed_urls = url_guard.sanitize_components(components)
        self.assertEqual(removed_urls, [])

        components, removed_numbers = self._guard().sanitize_components(components)
        self.assertEqual(removed_numbers, [])
        self.assertEqual(len(components), 1)

        bars = components[0]["data"]["bars"]
        self.assertEqual([b["label"] for b in bars], ["Us", "Suite A", "Suite B"])
        self.assertEqual(bars[0]["callout"], "Fastest")

    def test_fewer_than_two_bars_leaves_nothing_to_compare(self):
        kept, _ = self._guard().sanitize_components(
            [_component([{"label": "Us", "value": 1.4}])]
        )
        self.assertEqual(kept, [])

    def test_guard_disabled_keeps_everything(self):
        guard = NumericGuard(enforce=False)
        kept, removed = guard.sanitize_components(
            [_component(_bars(("Us", 1.4, {}), ("Suite A", 99.9, {})))]
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
