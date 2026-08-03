"""
Component Type Registry
Extensible vocabulary of UI components the LLM may generate.

The built-in types below cover generic content zones and editorial
sections, but the real value for an adopting team is generating *their*
design system. A custom component type is:

    name        -> identifier the LLM emits in {"type": name, ...}
    data_schema -> JSON Schema of the component's `data` payload, used both to teach the LLM the shape (prompt) and to validate what it generates (jsonschema)
    description -> one-liner telling the LLM when to use it

Two registration paths:
- Python API (backend embedders): from schemas.registry import register_component_type register_component_type("hero_banner", schema, "Full-width hero ...")
- Per request (frontend-driven adoption): the zone render request can carry `custom_components`; 
  they are merged over the global registry for that render and are part of the zone's cache identity.
"""

import logging
import re
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# The framework's own vocabulary, declared once. Every surface that lets a
# model emit components (zone renders, chat answers) composes its catalog
# from here instead of describing the types again in its own prompt.
BUILTIN_TYPE_DOCS: Dict[str, str] = {
    "bento": """Bento of content cards: cells are deliberately unequal, the leading card takes the large one and the rest fill around it, so put the most important card first (or mark it "featured")
data: {
    "cards": [
        {
            "title": "Card Title",
            "description": "Brief description",
            "icon": "emoji or icon name",
            "link": "https://...",
            "image": "image_url (optional)",
            "badge": "NEW (optional)",
            "featured": "true on the ONE card that matters most (optional)",
            "metadata": { ... any extra data ... }
        }
    ],
    "columns": 2-4 (density, not a hard grid: the shape follows the card count)
}""",
    "chart": """Data visualization
data: { "chart_type": "bar|line|pie|area|donut", "title": "...",
  "data": [{"label": "...", "value": 0}], "x_axis?": "...", "y_axis?": "..." }""",
    "text": """Short body copy the visitor reads (a section intro or lede).
"style" is purely visual, not a cue to explain.
data: { "content": "markdown text", "style": "normal|emphasis|note|heading" }""",
    "buttons": """Action buttons
data: { "buttons": [{ "label": "...", "url": "...", "style": "primary|secondary|outline|ghost|shine|gooey|expandIcon|ringHover" }] }""",
    "tabs_feature": """Tabbed feature section (plan comparison, product categories)
data: { "heading": "...", "badge?": "...", "tabs": [{ "label": "...", "icon?": "emoji",
  "content": { "layout": "with-image|text-only", "title": "...", "description?": "...",
    "button?": {"label","url"}, "image_url?": "..." } }] }""",
    "steps_section": """Step sequence (onboarding, how-it-works)
data: { "layout": "with-image|text-only", "steps": [{"title","description?","image_url?"}],
  "autoplay?": true, "interval?": 4000 }""",
    "stats_banner": """Numeric metrics, text only (use RAG facts, never invent numbers)
data: { "stats": [{"value": "10M", "label": "...", "description?": "...",
    "change?": {"direction": "up|down", "value?": "+20.1%", "sentiment?": "good|bad"}}],
  "columns?": 2-4, "layout?": "grid|split",
  "eyebrow?": "...", "title?": "...", "description?": "..." }
"grid" is the bare grid. "split" puts the eyebrow, title and paragraph beside it and
REQUIRES a title. A change is optional per metric: "direction" is what the number did,
"sentiment" is whether that is good news, and they are NOT the same. Cost, churn and
response time going down is good, so only send "sentiment" when the input says which
way is better; without it the movement is shown in a neutral tone.""",
    "testimonial_carousel": """Quotes with optional avatar
data: { "testimonials": [{"quote","name","role?","company?","avatar_url?"}], "autoplay?": true }""",
    "pricing_cards": """Plan grid; "detailed" adds a comparison table
data: { "variant": "compact|detailed", "plans": [{"name","price","period?","description?",
  "features": ["..."], "cta?": {"label","url"}, "highlighted?": true, "flag?": "Recommended"}] }""",
    "content_grid": """Blog/news cards, per-item image-optional
data: { "columns?": 2-4, "items": [{"layout": "with-image|text-only", "title",
  "category?", "excerpt?", "image_url?", "url?", "date?"}] }""",
    "hero_banner": """Hero section
data: { "variant": "split|centered|minimal", "headline", "subheadline?", "badge?",
  "primary_cta?": {"label","url"}, "secondary_cta?": {"label","url"}, "image_url?" }
("split" REQUIRES image_url; use "centered" or "minimal" without an image)""",
    "case_studies": """Editorial project/case studies (studios, agencies, portfolios)
data: { "heading?", "subheading?", "cases": [{"title", "summary?", "name?",
  "role?", "image_url?", "metrics?": [{"value","label","description?"}]}] }
Only include what the input gives: no image, no metrics, no name/role are all
fine and degrade cleanly. Never invent figures, names or roles.""",
    "comparison_bars": """Vertical bars comparing figures side by side
data: { "title", "subtitle?", "bars": [{"label", "value": 0, "suffix?": "%",
  "highlighted?": true, "callout?": "..."}] }
Two to six bars. Bar heights are relative to the largest value of the series,
so percentages and absolute figures both work; put the unit in "suffix", never
in "value". At most ONE bar is highlighted (the one the page belongs to) and
only that bar may carry a callout. Every value is copied from the input and
never estimated: a single figure that cannot be traced drops the whole
comparison, because a comparison with the unverifiable competitor quietly
removed flatters instead of informing.""",
    "metrics_trend": """Headline figures with the curve of how they got there
data: { "title", "tail?": "second half of the sentence, in a quieter tone",
  "metrics": [{"value": "50,000+", "label": "...", "description?": "..."}],
  "series": [{"label": "Jan", "value": 20}] }
Two to six metrics, and a series of two to twenty-four points drawn as an area
under a line. Every figure is copied from the input: an unverifiable metric is
removed and the others stay, while an unverifiable point takes the whole curve,
because a curve missing a point is a different curve. Only send a series when
the input really carries one over time; the grid alone is a finished section.""",
    "faq": """Questions that open onto their answers
data: { "title", "intro?", "items": [{"question", "answer": "simple markdown allowed"}] }
Two to twelve entries. Both the questions and the answers come from the input:
the zone context, the pinned content or the retrieved documents. Do not write a
question because it sounds like one a visitor would ask, and do not answer one
the input does not answer: an invented answer here reads as official policy.""",
    "pros_cons": """Advantages and limits side by side
data: { "title?", "pros_heading?": "Pros", "cons_heading?": "Cons",
  "pros": ["item text (simple markdown allowed)"], "cons": ["..."] }
Both sides come from the input: the zone context, the pinned content or the
retrieved documents. Never write an item to balance the two columns, and never
soften a drawback into a benefit. A side you were given nothing for stays
empty, and the component renders the other one full width as a deliberate
shape; make the headings say what the two sides are, in the language of the
page. At most 10 items per side.""",
    "quote": """A single large editorial quote / manifesto
data: { "quote", "author?", "role?", "avatar_url?", "logo_url?", "logo_label?" }
Author, role, avatar and top logo are each optional; omit any you were not
given rather than inventing it.""",
    "logo_wall": """A grid of logos (clients, technologies, partners)
data: { "heading?", "logos": [{"image_url", "alt", "url?"}], "cta_label?", "cta_url?" }
Label the wall for what it shows ("Selected clients", "Our stack"), not always
"clients". Each logo needs a real image URL from the input; drop logos with no
image. Only set cta_label + cta_url when there is a real overview link.""",
}

BUILTIN_TYPES = tuple(BUILTIN_TYPE_DOCS)


def builtin_catalog(
    names: Iterable[str],
    notes: Optional[Dict[str, str]] = None,
) -> str:
    """
    Numbered catalog of built-in types for one surface's prompt.

    `names` is what that surface exposes, in the order it wants to present
    them. `notes` maps a type to surface-specific advice appended to its
    entry, which is how "PREFERRED for content zones" stays a property of
    the zone prompt and not of the type.
    """
    notes = notes or {}
    entries = []
    for number, name in enumerate(names, 1):
        head, _, rest = BUILTIN_TYPE_DOCS[name].partition("\n")
        entry = f'{number}. "{name}" - {head}'
        body = "\n".join(part for part in (notes.get(name), rest) if part)
        if body:
            entry += "\n" + textwrap.indent(body, "   ")
        entries.append(entry)
    return "\n\n".join(entries)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


@dataclass(frozen=True)
class ComponentTypeDef:
    """Definition of a custom component type."""
    name: str
    data_schema: Dict[str, Any]
    description: str = ""
    example: Optional[Dict[str, Any]] = None

    def prompt_doc(self) -> str:
        """Compact documentation block for the LLM prompt."""
        import json

        lines = [f'- "{self.name}": {self.description or "custom component"}']
        lines.append(f"  data schema: {json.dumps(self.data_schema, sort_keys=True)}")
        if self.example is not None:
            lines.append(f"  example data: {json.dumps(self.example, sort_keys=True)}")
        return "\n".join(lines)


def validate_type_name(name: str) -> None:
    """Raise ValueError for invalid or reserved component type names."""
    if not _NAME_PATTERN.match(name or ""):
        raise ValueError(
            f"Invalid component type name {name!r}: use 2-32 chars, "
            "lowercase letters, digits, '_' or '-', starting with a letter"
        )
    if name in BUILTIN_TYPES:
        raise ValueError(f"Component type {name!r} is built-in and cannot be overridden")


# Global registry (backend embedders)
_registry: Dict[str, ComponentTypeDef] = {}


def register_component_type(
    name: str,
    data_schema: Dict[str, Any],
    description: str = "",
    example: Optional[Dict[str, Any]] = None,
) -> ComponentTypeDef:
    """
    Register a custom component type globally.

    Raises ValueError on invalid/reserved names. Re-registering a name
    replaces the previous definition (logged).
    """
    validate_type_name(name)
    if not isinstance(data_schema, dict):
        raise ValueError("data_schema must be a JSON Schema object (dict)")

    definition = ComponentTypeDef(
        name=name,
        data_schema=data_schema,
        description=description,
        example=example,
    )
    if name in _registry:
        logger.info("Component type %r re-registered", name)
    _registry[name] = definition
    return definition


def unregister_component_type(name: str) -> bool:
    """Remove a globally registered type. True if it existed."""
    return _registry.pop(name, None) is not None


def get_registered_types() -> Dict[str, ComponentTypeDef]:
    """Snapshot of the global registry."""
    return dict(_registry)


def merge_custom_types(
    request_components: Optional[List[Dict[str, Any]]],
) -> Dict[str, ComponentTypeDef]:
    """
    Merge per-request component definitions over the global registry.

    Request entries are dicts: {"name", "data_schema", "description", "example"}.
    Invalid entries are skipped (logged), they never break the render.
    """
    merged = get_registered_types()

    for entry in request_components or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        try:
            validate_type_name(name)
            schema = entry.get("data_schema")
            if not isinstance(schema, dict):
                raise ValueError("missing data_schema")
            merged[name] = ComponentTypeDef(
                name=name,
                data_schema=schema,
                description=str(entry.get("description", "")),
                example=entry.get("example"),
            )
        except ValueError as e:
            logger.warning("Skipping invalid custom component %r: %s", name, e)

    return merged
