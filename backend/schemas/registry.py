"""
Component Type Registry
Extensible vocabulary of UI components the LLM may generate.

The four built-in types (bento, chart, text, buttons) cover generic
content zones, but the real value for an adopting team is generating
*their* design system. A custom component type is:

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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BUILTIN_TYPES = (
    "bento", "chart", "text", "buttons",
    "tabs_feature", "steps_section", "stats_banner",
    "testimonial_carousel", "pricing_cards", "content_grid", "hero_banner",
)

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
