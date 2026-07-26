"""
Tests for the redundancy guard: a component may not spend itself
repeating what the visitor has already been shown.

The invariants:
- the same link target twice inside one component loses the repeat (a
  hero's second CTA pointing where the first points);
- the same target AND wording as an earlier component is removed, and a
  component emptied that way is dropped whole;
- different wording for the same target SURVIVES (the honest limit: that
  is an editorial call, not a comparison);
- a dropped component teaches the next one nothing, and pinned content is
  never touched (it runs after this step).

Runnable with `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from utils.redundancy_guard import RedundancyGuard

PRICING = "https://example.com/pricing"


def hero(*ctas):
    """A hero_banner with the given (label, url) CTAs."""
    data = {"variant": "centered", "headline": "Build faster", "badge": "New"}
    for slot, (label, url) in zip(("primary_cta", "secondary_cta"), ctas):
        data[slot] = {"label": label, "url": url}
    return {"type": "hero_banner", "data": data}


def bento(*cards):
    return {
        "type": "bento",
        "data": {
            "cards": [
                {"title": title, "description": "Compare plans.", "link": link}
                for title, link in cards
            ],
            "columns": 1,
        },
    }


class TestReportedShape(unittest.TestCase):
    """The render that started this: one link, three elements."""

    def setUp(self):
        self.components = [
            hero(("See pricing", PRICING), ("Explore", PRICING)),
            bento(("See pricing", PRICING)),
        ]

    def test_duplicate_cta_and_echo_card_are_both_removed(self):
        kept, notes = RedundancyGuard().sanitize_components(self.components)

        # The hero survives with ONE cta, the echoing card takes the bento down
        self.assertEqual([c["type"] for c in kept], ["hero_banner"])
        self.assertIn("primary_cta", kept[0]["data"])
        self.assertNotIn("secondary_cta", kept[0]["data"])
        self.assertEqual(len(notes), 2)  # both removals reported

    def test_disabled_guard_changes_nothing(self):
        kept, notes = RedundancyGuard(enforce=False).sanitize_components(self.components)
        self.assertEqual(len(kept), 2)
        self.assertEqual(notes, [])
        self.assertIn("secondary_cta", kept[0]["data"])


class TestKeepsLegitimateOutput(unittest.TestCase):
    """Narrow on purpose: what is not provably redundant stays."""

    def test_two_ctas_to_different_places_survive(self):
        kept, notes = RedundancyGuard().sanitize_components(
            [hero(("See pricing", PRICING), ("Read the docs", "https://example.com/docs"))]
        )
        self.assertIn("secondary_cta", kept[0]["data"])
        self.assertEqual(notes, [])

    def test_same_target_different_wording_survives(self):
        kept, _ = RedundancyGuard().sanitize_components(
            [hero(("See pricing", PRICING)), bento(("Plans and limits", PRICING))]
        )
        self.assertEqual([c["type"] for c in kept], ["hero_banner", "bento"])

    def test_only_the_repeat_is_dropped_not_the_whole_grid(self):
        kept, notes = RedundancyGuard().sanitize_components(
            [
                hero(("See pricing", PRICING)),
                bento(("See pricing", PRICING), ("Changelog", "https://example.com/log")),
            ]
        )
        self.assertEqual(len(kept), 2)
        titles = [card["title"] for card in kept[1]["data"]["cards"]]
        self.assertEqual(titles, ["Changelog"])
        self.assertEqual(len(notes), 1)

    def test_linkless_components_are_untouched(self):
        components = [
            {"type": "text", "data": {"content": "Ship polished products.", "style": "normal"}},
            {"type": "stats_banner", "data": {"stats": [{"value": "12", "label": "teams"}]}},
        ]
        kept, notes = RedundancyGuard().sanitize_components(components)
        self.assertEqual(len(kept), 2)
        self.assertEqual(notes, [])

    def test_trailing_punctuation_still_counts_as_the_same_target(self):
        # normalize_url is shared with the URL guard: same comparison rules
        kept, _ = RedundancyGuard().sanitize_components(
            [hero(("See pricing", PRICING), ("See pricing", PRICING + " "))]
        )
        self.assertNotIn("secondary_cta", kept[0]["data"])


class TestCrossComponentState(unittest.TestCase):
    """One instance per render: component N+1 sees what N left on the page."""

    def test_streaming_one_component_at_a_time_still_dedups(self):
        guard = RedundancyGuard()
        first, _ = guard.sanitize_components([hero(("See pricing", PRICING))])
        second, notes = guard.sanitize_components([bento(("See pricing", PRICING))])
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(notes), 1)

    def test_a_dropped_component_teaches_nothing(self):
        # The buttons component is dropped as an echo of the hero, so the
        # LAST component is checked against the hero only: a card with the
        # same target but new wording must still survive.
        guard = RedundancyGuard()
        kept, _ = guard.sanitize_components(
            [
                hero(("See pricing", PRICING)),
                {"type": "buttons", "data": {"buttons": [{"label": "See pricing", "url": PRICING}]}},
                bento(("Plans and limits", PRICING)),
            ]
        )
        self.assertEqual([c["type"] for c in kept], ["hero_banner", "bento"])


if __name__ == "__main__":
    unittest.main()
