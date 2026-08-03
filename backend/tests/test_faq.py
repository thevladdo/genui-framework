"""
faq: two questions is the floor, and an answer is prose like any other.
"""

import unittest

from schemas import component_to_dict, validate_components
from utils.url_guard import UrlGuard

INPUT_TEXT = "Billing questions are answered at https://acme.example/billing"


def _faq(items, **data):
    return {"type": "faq", "data": {"title": "Common questions", "items": items, **data}}


def _entry(question="What is included?", answer="Everything in the plan."):
    return {"question": question, "answer": answer}


class TestShape(unittest.TestCase):
    def test_two_entries_is_a_list_of_questions(self):
        valid, errors = validate_components([
            _faq([_entry(), _entry("How do I cancel?", "From the billing page.")],
                 intro="Answers to what people ask most.")
        ])
        self.assertEqual(errors, [])
        data = component_to_dict(valid[0])["data"]
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["intro"], "Answers to what people ask most.")

    def test_one_entry_is_a_paragraph_wearing_a_widget(self):
        valid, errors = validate_components([_faq([_entry()])])
        self.assertEqual(valid, [])
        self.assertTrue(errors)

    def test_thirteen_entries_are_refused(self):
        valid, _ = validate_components([
            _faq([_entry(f"Question {i}?") for i in range(13)])
        ])
        self.assertEqual(valid, [])

    def test_the_intro_is_optional(self):
        valid, errors = validate_components([
            _faq([_entry(), _entry("Second?", "Yes.")])
        ])
        self.assertEqual(errors, [])
        self.assertNotIn("intro", component_to_dict(valid[0])["data"])


class TestAnswerSanitization(unittest.TestCase):
    def _guard(self):
        guard = UrlGuard(enforce_whitelist=True)
        guard.allow_from_text(INPUT_TEXT)
        return guard

    def test_a_link_that_was_not_in_the_input_does_not_survive_an_answer(self):
        guard = self._guard()
        components, removed = guard.sanitize_components([
            _faq([
                _entry("Where do I pay?", "On the [billing page](https://acme.example/billing)."),
                _entry("Where else?", "Try the [partner portal](https://evil.example/pay)."),
            ])
        ])
        answers = [item["answer"] for item in components[0]["data"]["items"]]
        self.assertEqual(answers[0], "On the [billing page](https://acme.example/billing).")
        self.assertEqual(answers[1], "Try the partner portal.")
        self.assertIn("https://evil.example/pay", removed)

    def test_a_dangerous_scheme_in_an_answer_is_removed(self):
        guard = self._guard()
        components, _ = guard.sanitize_components([
            _faq([
                _entry("Reset?", "Click [here](javascript:alert(1))."),
                _entry("Second?", "Yes."),
            ])
        ])
        self.assertNotIn("javascript:", str(components[0]["data"]["items"]))


if __name__ == "__main__":
    unittest.main()
