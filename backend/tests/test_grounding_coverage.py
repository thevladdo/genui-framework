"""
Every field that displays a number is checked by the numeric guard.
"""

import json
import unittest
from typing import Any, Dict, Literal, Tuple, Union, get_args, get_origin

from pydantic import BaseModel

from schemas import component_to_dict, validate_components
from schemas.components import GenUIComponentModel
from utils.numeric_guard import NumericGuard

# Field names whose value is a displayed number in this vocabulary.
CONTENT_NAMES = frozenset({"value", "price"})

# A figure the input never carries, and a filler one it always does.
UNGROUNDED = "987654321"
GROUNDED = "1"
INPUT_TEXT = f"Everything in the sample payloads is {GROUNDED}."


def _model_and_list(annotation: Any) -> Tuple[Any, bool]:
    """(nested model, is a list) for a field annotation, Optional ignored."""
    origin = get_origin(annotation)
    if origin is Union:
        inner = [a for a in get_args(annotation) if a is not type(None)]
        return _model_and_list(inner[0]) if len(inner) == 1 else (None, False)
    if origin is list:
        model, _ = _model_and_list(get_args(annotation)[0])
        return model, True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation, False
    return None, False


def _is_scalar_number(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Union:
        inner = [a for a in get_args(annotation) if a is not type(None)]
        return len(inner) == 1 and _is_scalar_number(inner[0])
    return annotation in (str, float, int)


def numeric_paths(model: Any, prefix: Tuple[str, ...] = ()) -> list:
    """Paths, from the schema, whose leaf displays a number."""
    found = []
    for name, field in model.model_fields.items():
        nested, _ = _model_and_list(field.annotation)
        if nested is not None:
            found.extend(numeric_paths(nested, prefix + (name,)))
        elif name in CONTENT_NAMES and _is_scalar_number(field.annotation):
            found.append(prefix + (name,))
    return found


def _scalar(annotation: Any, figure: str) -> Any:
    origin = get_origin(annotation)
    if origin is Union:
        inner = [a for a in get_args(annotation) if a is not type(None)]
        return _scalar(inner[0], figure)
    if origin is Literal:
        return get_args(annotation)[0]
    if annotation in (float, int):
        return float(figure)
    if annotation is bool:
        return True
    if annotation is dict or origin is dict:
        return {}
    return figure


def _fill(model: Any, target: Tuple[str, ...], figure: str) -> Dict[str, Any]:
    """
    The smallest valid payload for this model, carrying `figure` at `target`.

    Optional fields are left out unless the target runs through them, and
    every list gets two entries: one is the case under test, the other
    keeps the component alive.
    """
    out: Dict[str, Any] = {}
    for name, field in model.model_fields.items():
        on_path = bool(target) and target[0] == name
        if not field.is_required() and not on_path:
            continue
        rest = target[1:] if on_path else ()
        nested, is_list = _model_and_list(field.annotation)
        if nested is not None:
            out[name] = (
                [_fill(nested, rest, figure), _fill(nested, (), GROUNDED)]
                if is_list
                else _fill(nested, rest, figure)
            )
        elif is_list:
            out[name] = ["x", "x"]
        else:
            out[name] = _scalar(
                field.annotation, figure if on_path and not rest else GROUNDED
            )
    return out


def _components() -> list:
    """(type name, data model) for every built-in component."""
    union = get_args(GenUIComponentModel)[0]
    pairs = []
    for member in get_args(union):
        ctype = get_args(member.model_fields["type"].annotation)[0]
        pairs.append((ctype, member.model_fields["data"].annotation))
    return pairs


def _serve(ctype: str, data: Dict[str, Any]) -> Tuple[list, list]:
    """Validate, then run the numeric guard, the way a render does."""
    valid, errors = validate_components([{"type": ctype, "data": data}])
    if errors or not valid:
        raise AssertionError(f"{ctype}: the sample payload is invalid: {errors}")
    guard = NumericGuard(enforce=True)
    guard.allow_from_text(INPUT_TEXT)
    return guard.sanitize_components([component_to_dict(c) for c in valid])


class TestGroundingCoverage(unittest.TestCase):
    def test_the_schemas_carry_displayed_numbers(self):
        """A guard against the check quietly finding nothing to check."""
        total = sum(len(numeric_paths(model)) for _, model in _components())
        self.assertGreater(total, 5, "no numeric fields found: the walk is broken")

    def test_every_displayed_number_is_grounded(self):
        for ctype, model in _components():
            for path in numeric_paths(model):
                where = ".".join(path)
                with self.subTest(component=ctype, field=where):
                    kept, _ = _serve(ctype, _fill(model, path, GROUNDED))
                    self.assertTrue(
                        kept,
                        f"{ctype}: the sample for '{where}' does not survive even "
                        f"with a grounded figure, so this check proves nothing",
                    )

                    kept, removed = _serve(ctype, _fill(model, path, UNGROUNDED))
                    self.assertNotIn(
                        UNGROUNDED,
                        json.dumps(kept),
                        f"{ctype}: '{where}' displays a number the numeric guard "
                        f"does not check. Add it to the map in "
                        f"utils/numeric_guard.py, or take the field off this "
                        f"type if nothing renders it",
                    )
                    self.assertTrue(
                        removed,
                        f"{ctype}: '{where}' was removed without being reported "
                        f"in meta.sanitization.removed_numbers",
                    )


if __name__ == "__main__":
    unittest.main()
