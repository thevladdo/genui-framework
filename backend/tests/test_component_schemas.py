"""
Tests for the component schemas (Pydantic validation of LLM output).
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import unittest

from schemas import (
    ZoneAgentOutput,
    component_to_dict,
    validate_components,
    zone_output_json_schema,
)


def bento(cards=None, **extra):
    if cards is None:
        cards = [{"title": "Card"}]
    return {
        "type": "bento",
        "data": {"cards": cards, **extra},
    }


class TestValidateComponents(unittest.TestCase):
    def test_valid_components_pass(self):
        raw = [
            bento(),
            {"type": "text", "data": {"content": "hello", "style": "note"}},
            {"type": "chart", "data": {"chart_type": "pie", "data": [{"label": "a", "value": 1}]}},
            {"type": "buttons", "data": {"buttons": [{"label": "Go", "url": "/x"}]}},
        ]
        valid, errors = validate_components(raw)
        self.assertEqual(len(valid), 4)
        self.assertEqual(errors, [])

    def test_invalid_component_dropped_others_survive(self):
        raw = [
            bento(),
            {"type": "carousel", "data": {}},          # unknown type
            {"type": "text", "data": {}},               # missing content
            {"type": "chart", "data": {"chart_type": "3d-pie", "data": [{"label": "a", "value": 1}]}},
        ]
        valid, errors = validate_components(raw)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 3)

    def test_non_dict_and_non_list_input(self):
        valid, errors = validate_components(["not a dict"])
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)

        valid, errors = validate_components("nonsense")
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)

    def test_constraints_enforced(self):
        # Empty cards list violates min_length=1
        valid, errors = validate_components([bento(cards=[])])
        self.assertEqual(valid, [])
        self.assertEqual(len(errors), 1)

        # columns out of range
        valid, errors = validate_components([bento(columns=9)])
        self.assertEqual(valid, [])

    def test_extra_fields_tolerated(self):
        raw = [bento()]
        raw[0]["data"]["cards"][0]["hallucinated_field"] = "whatever"
        raw[0]["unknown_envelope_key"] = True
        valid, errors = validate_components(raw)
        self.assertEqual(len(valid), 1)
        self.assertEqual(errors, [])

    def test_round_trip_to_wire_format(self):
        valid, _ = validate_components([bento()])
        wire = component_to_dict(valid[0])
        self.assertEqual(wire["type"], "bento")
        self.assertEqual(wire["data"]["cards"][0]["title"], "Card")
        # exclude_none: optional empty fields don't pollute the payload
        self.assertNotIn("link", wire["data"]["cards"][0])


class TestZoneAgentOutput(unittest.TestCase):
    def test_envelope_defaults(self):
        out = ZoneAgentOutput.model_validate({})
        self.assertEqual(out.components, [])
        self.assertEqual(out.confidence, 0.5)
        self.assertFalse(out.personalization_applied)

    def test_confidence_bounds(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ZoneAgentOutput.model_validate({"confidence": 1.7})

    def test_json_schema_is_generatable(self):
        schema = zone_output_json_schema()
        self.assertEqual(schema.get("type"), "object")
        self.assertIn("components", schema.get("properties", {}))
        # Discriminated union must be expressed via $defs/oneOf-anyOf
        self.assertIn("$defs", schema)


if __name__ == "__main__":
    unittest.main()
