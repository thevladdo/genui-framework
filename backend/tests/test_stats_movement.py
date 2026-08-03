"""
stats_banner grows a narration, a two column layout and a movement.
"""

import unittest

from schemas import component_to_dict, validate_components
from utils.numeric_guard import NumericGuard

INPUT_TEXT = "Monthly active users reached 500,000, up 20.1% on the quarter."


def _banner(stats, **data):
    return {"type": "stats_banner", "data": {"stats": stats, **data}}


class TestCompatibility(unittest.TestCase):
    """The payload shape that existed before this work still renders."""

    def test_the_old_payload_survives_untouched(self):
        before = [
            {"value": "10M", "label": "Users reached"},
            {"value": "99.9%", "label": "Uptime", "description": "last 12 months"},
        ]
        valid, errors = validate_components([_banner(before, columns=2)])
        self.assertEqual(errors, [])

        data = component_to_dict(valid[0])["data"]
        self.assertEqual(data["stats"], before)
        self.assertEqual(data["columns"], 2)
        for field in ("eyebrow", "title", "description"):
            self.assertNotIn(field, data)
        self.assertEqual(data["layout"], "grid")

    def test_the_default_layout_is_the_old_one(self):
        valid, _ = validate_components([_banner([{"value": "1", "label": "One"}])])
        self.assertEqual(component_to_dict(valid[0])["data"]["layout"], "grid")


class TestNarration(unittest.TestCase):
    def test_split_carries_the_narration_beside_the_grid(self):
        valid, errors = validate_components([
            _banner(
                [{"value": "500,000", "label": "Users"}, {"value": "1,052", "label": "Cost"}],
                layout="split",
                eyebrow="Platform",
                title="This is the start of something new",
                description="What the numbers are counting.",
            )
        ])
        self.assertEqual(errors, [])
        data = component_to_dict(valid[0])["data"]
        self.assertEqual(data["eyebrow"], "Platform")
        self.assertEqual(data["layout"], "split")

    def test_split_without_a_title_is_two_columns_with_an_empty_one(self):
        valid, errors = validate_components([
            _banner([{"value": "1", "label": "One"}], layout="split")
        ])
        self.assertEqual(valid, [])
        self.assertTrue(any("split" in e for e in errors), errors)


class TestDirectionAndSentiment(unittest.TestCase):
    def test_a_movement_carries_direction_and_delta(self):
        valid, _ = validate_components([
            _banner([{
                "value": "500,000", "label": "Users",
                "change": {"direction": "up", "value": "+20.1%", "sentiment": "good"},
            }])
        ])
        change = component_to_dict(valid[0])["data"]["stats"][0]["change"]
        self.assertEqual(change["direction"], "up")
        self.assertEqual(change["sentiment"], "good")

    def test_a_sentiment_is_never_inferred_from_a_direction(self):
        """Down is not bad: cost, churn and response time going down is the win."""
        valid, _ = validate_components([
            _banner([{
                "value": "1,052", "label": "Cost per acquisition",
                "change": {"direction": "down", "value": "-2%"},
            }])
        ])
        change = component_to_dict(valid[0])["data"]["stats"][0]["change"]
        self.assertEqual(change["direction"], "down")
        self.assertNotIn("sentiment", change)

    def test_an_unknown_direction_is_refused(self):
        valid, _ = validate_components([
            _banner([{"value": "1", "label": "One", "change": {"direction": "sideways"}}])
        ])
        self.assertEqual(valid, [])


class TestGrounding(unittest.TestCase):
    """The delta is a displayed number, so it is grounded like the value."""

    def _guard(self):
        guard = NumericGuard(enforce=True)
        guard.allow_from_text(INPUT_TEXT)
        return guard

    def test_an_ungrounded_delta_removes_the_stat_like_an_ungrounded_value(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components([
            _banner([
                {"value": "500,000", "label": "Users",
                 "change": {"direction": "up", "value": "+20.1%"}},
                {"value": "500,000", "label": "Invented delta",
                 "change": {"direction": "up", "value": "+77%"}},
            ])
        ])
        labels = [s["label"] for s in kept[0]["data"]["stats"]]
        self.assertEqual(labels, ["Users"])
        self.assertIn("+77%", removed)

    def test_a_movement_with_no_delta_makes_no_numeric_claim(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components([
            _banner([{"value": "500,000", "label": "Users",
                      "change": {"direction": "up", "sentiment": "good"}}])
        ])
        self.assertEqual(len(kept[0]["data"]["stats"]), 1)
        self.assertEqual(removed, [])

    def test_a_banner_whose_stats_all_go_is_dropped(self):
        guard = self._guard()
        kept, _ = guard.sanitize_components([
            _banner([{"value": "500,000", "label": "Users",
                      "change": {"direction": "up", "value": "+77%"}}])
        ])
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main()
