"""
A component type is declared once, in the dictionary, and every surface that
lets a model emit components composes its catalog from there. The two can
still drift apart in two ways and both are silent:

- a surface declares a type the dictionary does not have, so the catalog is 
built from a name nothing can render.
- the dictionary grows a type no surface declares, so the component exists, 
is validated, is rendered by the library, and is never offered to a model.
"""

import ast
import os
import re
import unittest

from schemas.registry import BUILTIN_TYPES, BUILTIN_TYPE_DOCS, builtin_catalog

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SURFACES = {
    "zone renders": ("agents/zone_agent.py", "ZoneAgent"),
    "chat answers": ("agents/response_agent.py", "ResponseAgent"),
}

ENTRY_RE = re.compile(r'^\d+\. "([a-z_]+)"', re.M)

UNION_RE = re.compile(r'"type": "([a-z_]+(?:\|[a-z_]+)+)"')

try:
    from agents.response_agent import ResponseAgent
    from agents.zone_agent import ZoneAgent

    PROMPTS = {
        "zone renders": ZoneAgent.SYSTEM_PROMPT,
        "chat answers": ResponseAgent.SYSTEM_PROMPT,
    }
except Exception: 
    PROMPTS = {}


def _declaration(relative_path, class_name):
    """The EXPOSED_TYPES and SURFACE_NOTES a surface declares."""
    path = os.path.join(BACKEND_ROOT, relative_path)
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            declared = {}
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                target = statement.targets[0]
                if isinstance(target, ast.Name) and target.id in ("EXPOSED_TYPES", "SURFACE_NOTES"):
                    declared[target.id] = ast.literal_eval(statement.value)
            return declared.get("EXPOSED_TYPES", ()), declared.get("SURFACE_NOTES", {})

    raise AssertionError(f"{relative_path} no longer defines {class_name}")


DECLARATIONS = {
    surface: _declaration(*location) for surface, location in SURFACES.items()
}


class TypeCatalogAlignmentTest(unittest.TestCase):
    """Declared types and rendered catalogs say the same thing."""

    def test_every_declared_type_exists(self):
        for surface, (exposed, _) in DECLARATIONS.items():
            self.assertTrue(exposed, f"{surface} declares no component types")
            for name in exposed:
                self.assertTrue(
                    name in BUILTIN_TYPE_DOCS,
                    f"{surface} exposes '{name}', which is not a component type: "
                    f"add it to BUILTIN_TYPE_DOCS in schemas/registry.py or stop "
                    f"exposing it",
                )

    def test_every_type_is_exposed_somewhere(self):
        for name in BUILTIN_TYPES:
            surfaces = [s for s, (exposed, _) in DECLARATIONS.items() if name in exposed]
            self.assertTrue(
                surfaces,
                f"component type '{name}' is described in the dictionary but no "
                f"surface exposes it, so no model is ever offered it: add it to "
                f"EXPOSED_TYPES on the surfaces it belongs to "
                f"({', '.join(SURFACES)}), or decide it belongs to none and say "
                f"so where the exclusion is explained",
            )

    def test_catalog_lists_exactly_the_declared_types(self):
        for surface, (exposed, notes) in DECLARATIONS.items():
            catalog = builtin_catalog(exposed, notes)
            listed = ENTRY_RE.findall(catalog)
            for name in exposed:
                self.assertIn(
                    name,
                    listed,
                    f"{surface} exposes '{name}' but its catalog has no entry for it",
                )
            for name in listed:
                self.assertIn(
                    name,
                    exposed,
                    f"the catalog of {surface} names '{name}', which that surface "
                    f"does not declare",
                )

    def test_notes_annotate_declared_types(self):
        for surface, (exposed, notes) in DECLARATIONS.items():
            for name in notes:
                self.assertIn(
                    name,
                    exposed,
                    f"{surface} carries surface advice for '{name}', which it does "
                    f"not expose",
                )

    @unittest.skipUnless(PROMPTS, "agent modules need the application configuration")
    def test_prompts_offer_exactly_the_declared_types(self):
        for surface, prompt in PROMPTS.items():
            exposed = DECLARATIONS[surface][0]
            self.assertEqual(
                ENTRY_RE.findall(prompt),
                list(exposed),
                f"the catalog inside the {surface} prompt has drifted from what "
                f"that surface declares",
            )
            unions = UNION_RE.findall(prompt)
            self.assertEqual(len(unions), 1, f"expected one type union in the {surface} prompt")
            for name in unions[0].split("|"):
                self.assertIn(
                    name,
                    exposed,
                    f"the {surface} prompt allows '{name}' in its output but does "
                    f"not describe it",
                )


if __name__ == "__main__":
    unittest.main()
