"""
metrics_trend: one component, two rules of truth.

The section says two things at once, how big and how it is going, and the
two halves cannot fail the same way.
"""

import unittest

from schemas import component_to_dict, validate_components
from utils.numeric_guard import NumericGuard

INPUT_TEXT = (
    "We serve 50,000 teams with 99.9% uptime and 1,200 enterprise accounts. "
    "Monthly signups ran 20, 40, 60 and 80."
)


def _component(metrics, series=None, **extra):
    data = {"title": "Where we are", "metrics": metrics, **extra}
    if series is not None:
        data["series"] = series
    return {"type": "metrics_trend", "data": data}


def _metric(value, label="Teams"):
    return {"value": value, "label": label}


def _series(*values):
    return [{"label": f"M{i}", "value": v} for i, v in enumerate(values)]


class TestShape(unittest.TestCase):
    def test_grid_and_curve_together(self):
        valid, errors = validate_components([
            _component(
                [_metric("50,000"), _metric("99.9%", "Uptime")],
                _series(20, 40, 60, 80),
                tail="and how it grew",
            )
        ])
        self.assertEqual(errors, [])
        data = component_to_dict(valid[0])["data"]
        self.assertEqual(len(data["series"]), 4)
        self.assertEqual(data["tail"], "and how it grew")

    def test_one_metric_is_not_a_grid(self):
        valid, errors = validate_components([_component([_metric("50,000")])])
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_seven_metrics_are_refused(self):
        valid, _ = validate_components([
            _component([_metric(str(i), f"L{i}") for i in range(7)])
        ])
        self.assertEqual(valid, [])

    def test_a_single_point_is_not_a_series_and_the_grid_stays(self):
        valid, errors = validate_components([
            _component([_metric("50,000"), _metric("99.9%")], _series(20))
        ])
        self.assertEqual(errors, [])
        self.assertEqual(component_to_dict(valid[0])["data"]["series"], [])

    def test_no_series_at_all_is_valid(self):
        valid, errors = validate_components([
            _component([_metric("50,000"), _metric("99.9%")])
        ])
        self.assertEqual(errors, [])
        self.assertEqual(component_to_dict(valid[0])["data"].get("series", []), [])


class TestTheTwoRules(unittest.TestCase):
    def _guard(self):
        guard = NumericGuard(enforce=True)
        guard.allow_from_text(INPUT_TEXT)
        return guard

    def test_ungrounded_metric_leaves_with_only_itself(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components([
            _component(
                [_metric("50,000"), _metric("7,777", "Invented"), _metric("99.9%", "Uptime")],
                _series(20, 40),
            )
        ])
        self.assertEqual(len(kept), 1)
        data = kept[0]["data"]
        self.assertEqual([m["value"] for m in data["metrics"]], ["50,000", "99.9%"])
        self.assertEqual(len(data["series"]), 2)
        self.assertIn("7,777", removed)

    def test_ungrounded_point_takes_the_whole_curve_and_the_grid_stays(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components([
            _component(
                [_metric("50,000"), _metric("99.9%", "Uptime")],
                _series(20, 4242, 60),
            )
        ])
        data = kept[0]["data"]
        self.assertEqual(data["series"], [])
        self.assertEqual([m["value"] for m in data["metrics"]], ["50,000", "99.9%"])
        self.assertIn("4242", removed)

    def test_below_two_surviving_metrics_the_section_falls(self):
        guard = self._guard()
        kept, _ = guard.sanitize_components([
            _component(
                [_metric("50,000"), _metric("7,777", "Invented"), _metric("8,888", "Also")],
                _series(20, 40),
            )
        ])
        self.assertEqual(kept, [])

    def test_a_clean_section_survives_untouched(self):
        guard = self._guard()
        kept, removed = guard.sanitize_components([
            _component(
                [_metric("50,000"), _metric("99.9%", "Uptime"), _metric("1,200", "Accounts")],
                _series(20, 40, 60, 80),
            )
        ])
        self.assertEqual(removed, [])
        self.assertEqual(len(kept[0]["data"]["metrics"]), 3)
        self.assertEqual(len(kept[0]["data"]["series"]), 4)

    def test_the_two_rules_are_not_the_same_rule(self):
        """The point of the type: same input, same offence, different outcome."""
        guard = self._guard()
        kept, _ = guard.sanitize_components([
            _component(
                [_metric("50,000"), _metric("99.9%", "Uptime"), _metric("7,777", "Invented")],
                _series(20, 4242),
            )
        ])
        data = kept[0]["data"]
        self.assertEqual(len(data["metrics"]), 2)
        self.assertEqual(data["series"], [])


if __name__ == "__main__":
    unittest.main()
