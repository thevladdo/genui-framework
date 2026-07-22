"""
Zone component budget: a zone is one band of a host page, not a page.
The model is told the budget in the prompt; apply_component_budget
enforces it after validation, and the cut is reported honestly.

Pure tests + router-level checks that run only where fastapi exists.
"""

import unittest

from schemas.components import apply_component_budget

try:
    from api import zone_router  # noqa: F401
    HAS_APP = True
except Exception:
    HAS_APP = False


def _c(ctype: str) -> dict:
    return {"type": ctype, "data": {}}


class TestApplyComponentBudget(unittest.TestCase):
    def test_under_budget_untouched(self):
        comps = [_c("hero_banner"), _c("bento")]
        kept, dropped = apply_component_budget(comps, 2)
        self.assertEqual(kept, comps)
        self.assertEqual(dropped, [])

    def test_over_budget_cuts_in_order_and_reports(self):
        comps = [_c("bento"), _c("text"), _c("quote"), _c("tabs_feature")]
        kept, dropped = apply_component_budget(comps, 2)
        self.assertEqual([c["type"] for c in kept], ["bento", "text"])
        self.assertEqual(len(dropped), 2)
        self.assertIn("quote", dropped[0])
        self.assertIn("budget (2)", dropped[0])
        self.assertIn("tabs_feature", dropped[1])

    def test_no_limit_means_no_budget(self):
        comps = [_c("a"), _c("b"), _c("c")]
        for limit in (None, 0, -1):
            kept, dropped = apply_component_budget(comps, limit)
            self.assertEqual(kept, comps, limit)
            self.assertEqual(dropped, [], limit)


@unittest.skipUnless(HAS_APP, "fastapi app deps not installed")
class TestRouterWiring(unittest.TestCase):
    def _request(self, **kwargs):
        return zone_router.ZoneRenderRequest(zone_id="z", **kwargs)

    def test_budget_is_part_of_the_cache_config(self):
        from config import settings
        config = zone_router._request_config(self._request())
        self.assertEqual(
            config["max_components"], settings.zone_max_components
        )
        config = zone_router._request_config(self._request(max_components=5))
        self.assertEqual(config["max_components"], 5)

    def test_agent_request_carries_the_resolved_default(self):
        from config import settings
        agent_req = zone_router._agent_request(self._request(), "t")
        self.assertEqual(
            agent_req.max_components, settings.zone_max_components
        )


if __name__ == "__main__":
    unittest.main()
