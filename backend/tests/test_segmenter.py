"""
Tests for the profile segmenter.
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from segmentation import compute_segment
from segmentation.segmenter import ANONYMOUS_SEGMENT


def profile_entry(value, confidence=0.9):
    return {"value": value, "confidence": confidence}


class TestComputeSegment(unittest.TestCase):
    def test_no_signals_is_anonymous(self):
        for profile, behavior in [(None, None), ({}, {}), ({"interests": {}}, None)]:
            segment = compute_segment(profile, behavior)
            self.assertEqual(segment.key, ANONYMOUS_SEGMENT)
            self.assertTrue(segment.is_anonymous)
            self.assertEqual(segment.factors, [])

    def test_deterministic(self):
        profile = {
            "preferences": {"role": profile_entry("Developer")},
            "interests": {
                "sustainability": profile_entry(True),
                "ai": profile_entry(True),
            },
        }
        behavior = {"userType": "deep_reader", "maxScrollDepth": 85}
        a = compute_segment(profile, behavior)
        b = compute_segment(profile, behavior)
        self.assertEqual(a.key, b.key)
        self.assertEqual(
            a.key,
            "role=developer|int=ai+sustainability|type=deep-reader|eng=high",
        )
        self.assertEqual(a.factors, ["role", "interests", "user_type", "engagement"])

    def test_low_confidence_entries_are_ignored(self):
        profile = {
            "preferences": {"role": profile_entry("developer", confidence=0.2)},
            "interests": {"crypto": profile_entry(True, confidence=0.1)},
        }
        segment = compute_segment(profile, None)
        self.assertEqual(segment.key, ANONYMOUS_SEGMENT)

    def test_role_falls_back_to_demographic(self):
        profile = {"demographic": {"role": profile_entry("Investor")}}
        segment = compute_segment(profile, None)
        self.assertEqual(segment.key, "role=investor")

    def test_interests_sorted_and_capped(self):
        profile = {
            "interests": {
                "zebra": profile_entry(True),
                "alpha": profile_entry(True),
                "mid": profile_entry(True),
                "extra": profile_entry(True),
            }
        }
        segment = compute_segment(profile, None, max_interests=3)
        # Alphabetical, capped at 3: alpha, extra, mid
        self.assertEqual(segment.key, "int=alpha+extra+mid")

    def test_string_interest_value_used_over_key(self):
        profile = {"interests": {"products": profile_entry("Trains")}}
        segment = compute_segment(profile, None)
        self.assertEqual(segment.key, "int=trains")

    def test_engagement_buckets(self):
        self.assertEqual(compute_segment({}, {"maxScrollDepth": 90}).key, "eng=high")
        self.assertEqual(compute_segment({}, {"maxScrollDepth": 50}).key, "eng=mid")
        self.assertEqual(compute_segment({}, {"maxScrollDepth": 10}).key, "eng=low")

    def test_user_type_from_stored_profile(self):
        profile = {"behavior": {"_user_type": "quick_scanner"}}
        segment = compute_segment(profile, None)
        self.assertEqual(segment.key, "type=quick-scanner")

    def test_values_are_slugified(self):
        profile = {
            "preferences": {"role": profile_entry("Senior Software Engineer!")},
        }
        segment = compute_segment(profile, None)
        self.assertEqual(segment.key, "role=senior-software-engineer")
        self.assertNotIn(" ", segment.key)
        self.assertNotIn("!", segment.key)


if __name__ == "__main__":
    unittest.main()
