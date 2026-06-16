"""
Tests for the incremental JSON component parser (streaming renders).
Runnable with pytest or `python3 -m unittest discover -s tests` from backend/.
"""

import json
import unittest

from utils.json_stream import ComponentStreamParser

FULL_RESPONSE = json.dumps({
    "components": [
        {"type": "text", "data": {"content": "Hello {braces} [ok]"}},
        {"type": "bento", "data": {"cards": [{"title": "A \"quoted\" title", "link": "/a"}], "columns": 2}},
        {"type": "buttons", "data": {"buttons": [{"label": "Go", "url": "/go"}]}},
    ],
    "pinned_included": ["/a"],
    "confidence": 0.9,
    "reasoning": "because { reasons }",
})


def feed_in_chunks(text: str, size: int):
    parser = ComponentStreamParser()
    collected = []
    for i in range(0, len(text), size):
        collected.extend(parser.feed(text[i:i + size]))
    return parser, collected


class TestComponentStreamParser(unittest.TestCase):
    def test_single_feed_extracts_all_components(self):
        parser = ComponentStreamParser()
        components = parser.feed(FULL_RESPONSE)
        self.assertEqual(len(components), 3)
        self.assertEqual(components[0]["type"], "text")
        self.assertEqual(components[2]["data"]["buttons"][0]["url"], "/go")

    def test_chunked_feeds_any_boundary(self):
        # Chunk sizes chosen to split strings, escapes, and braces
        for size in (1, 2, 3, 7, 16, 64):
            parser, components = feed_in_chunks(FULL_RESPONSE, size)
            self.assertEqual(len(components), 3, f"chunk size {size}")
            self.assertTrue(parser.components_array_done, f"chunk size {size}")

    def test_full_text_accumulated_for_envelope(self):
        parser, _ = feed_in_chunks(FULL_RESPONSE, 5)
        envelope = json.loads(parser.text)
        self.assertEqual(envelope["confidence"], 0.9)
        self.assertEqual(envelope["pinned_included"], ["/a"])

    def test_braces_inside_strings_ignored(self):
        response = '{"components": [{"type": "text", "data": {"content": "a } b { c ] d"}}]}'
        parser = ComponentStreamParser()
        components = parser.feed(response)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["data"]["content"], "a } b { c ] d")

    def test_escaped_quotes_inside_strings(self):
        response = '{"components": [{"type": "text", "data": {"content": "say \\"hi\\" {x}"}}]}'
        parser, components = feed_in_chunks(response, 3)
        self.assertEqual(len(components), 1)

    def test_components_emitted_incrementally(self):
        parser = ComponentStreamParser()
        first = '{"components": [{"type": "text", "data": {"content": "one"}}'
        second = ', {"type": "text", "data": {"content": "two"}}], "confidence": 1.0}'

        got_first = parser.feed(first)
        self.assertEqual(len(got_first), 1)
        self.assertEqual(got_first[0]["data"]["content"], "one")

        got_second = parser.feed(second)
        self.assertEqual(len(got_second), 1)
        self.assertEqual(got_second[0]["data"]["content"], "two")
        self.assertTrue(parser.components_array_done)

    def test_no_components_key(self):
        parser = ComponentStreamParser()
        self.assertEqual(parser.feed('{"text_response": "no components here"}'), [])
        self.assertFalse(parser.components_array_done)

    def test_nothing_after_array_done(self):
        parser = ComponentStreamParser()
        parser.feed('{"components": [], "confidence": 0.5}')
        self.assertTrue(parser.components_array_done)
        self.assertEqual(parser.feed('{"type": "text"}'), [])

    def test_empty_chunks_are_safe(self):
        parser = ComponentStreamParser()
        self.assertEqual(parser.feed(""), [])
        components = parser.feed(FULL_RESPONSE)
        self.assertEqual(len(components), 3)

    def test_whitespace_in_components_key(self):
        response = '{ "components" :  [ {"type": "text", "data": {"content": "x"}} ] }'
        parser = ComponentStreamParser()
        self.assertEqual(len(parser.feed(response)), 1)


if __name__ == "__main__":
    unittest.main()
