"""
Component Schemas Module
Single source of truth for the structure of LLM-generated UI components.

These schemas serve two purposes:
1. They are converted to a JSON schema and passed to the LLM provider as
   native structured output (response_format), so the model is constrained
   at generation time.
2. Every component coming back from the model is validated against them
   server-side before reaching the frontend — an invalid component is
   dropped (and reported), it never breaks the rest of the render.

The component vocabulary mirrors the frontend renderers in
frontend/src/components/ (BentoComponent, ChartComponent, TextComponent,
ButtonsComponent). Field names are snake_case here; the frontend
ComponentRenderer normalizes them to camelCase.
"""

import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .registry import ComponentTypeDef

logger = logging.getLogger(__name__)


class _SchemaModel(BaseModel):
    """Base config: tolerate unknown extra fields, the model often adds some."""
    model_config = ConfigDict(extra="ignore")



# Component data payloads
class TextData(_SchemaModel):
    """Markdown text block."""
    content: str = Field(..., min_length=1)
    style: Literal["normal", "emphasis", "note", "heading"] = "normal"


class CardAction(_SchemaModel):
    """Optional action button on a bento card."""
    label: str
    url: Optional[str] = None


class BentoCard(_SchemaModel):
    """A single card in a bento grid."""
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    icon: Optional[str] = None
    link: Optional[str] = None
    image: Optional[str] = None
    badge: Optional[str] = None
    action: Optional[CardAction] = None
    metadata: Optional[Dict[str, Any]] = None


class BentoData(_SchemaModel):
    """Bento grid payload."""
    cards: List[BentoCard] = Field(..., min_length=1)
    columns: int = Field(default=3, ge=1, le=4)
    gap: Optional[int] = Field(default=None, ge=0, le=64)


class ChartPoint(_SchemaModel):
    """A single chart data point."""
    label: str
    value: float
    color: Optional[str] = None


class ChartData(_SchemaModel):
    """Chart payload."""
    chart_type: Literal["bar", "line", "pie", "area", "donut"] = "bar"
    title: Optional[str] = None
    data: List[ChartPoint] = Field(..., min_length=1)
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    show_legend: Optional[bool] = None
    show_grid: Optional[bool] = None
    height: Optional[int] = Field(default=None, ge=100, le=1200)


class ButtonDef(_SchemaModel):
    """A single action button."""
    label: str = Field(..., min_length=1)
    url: Optional[str] = None
    style: Literal[
        "primary", "secondary", "outline", "ghost",
        "shine", "gooey", "expandIcon", "ringHover",
    ] = "primary"
    size: Optional[Literal["sm", "md", "lg"]] = None
    show_arrow: Optional[bool] = None
    arrow_placement: Optional[Literal["left", "right"]] = None


class ButtonsData(_SchemaModel):
    """Buttons row payload."""
    buttons: List[ButtonDef] = Field(..., min_length=1)
    direction: Optional[Literal["horizontal", "vertical"]] = None
    align: Optional[Literal["start", "center", "end"]] = None
    gap: Optional[int] = Field(default=None, ge=0, le=64)



# Components (discriminated by "type")
class _ComponentBase(_SchemaModel):
    layout: Optional[Dict[str, Any]] = None


class TextComponentModel(_ComponentBase):
    type: Literal["text"]
    data: TextData


class BentoComponentModel(_ComponentBase):
    type: Literal["bento"]
    data: BentoData


class ChartComponentModel(_ComponentBase):
    type: Literal["chart"]
    data: ChartData


class ButtonsComponentModel(_ComponentBase):
    type: Literal["buttons"]
    data: ButtonsData


GenUIComponentModel = Annotated[
    Union[
        TextComponentModel,
        BentoComponentModel,
        ChartComponentModel,
        ButtonsComponentModel,
    ],
    Field(discriminator="type"),
]

_component_adapter: TypeAdapter = TypeAdapter(GenUIComponentModel)



# Agent output envelopes
class ZoneAgentOutput(_SchemaModel):
    """Expected envelope of a ZoneAgent generation."""
    components: List[GenUIComponentModel] = Field(default_factory=list)
    pinned_included: List[str] = Field(default_factory=list)
    personalization_applied: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""
    profile_factors: List[str] = Field(default_factory=list)


class SourceRef(_SchemaModel):
    title: str = ""
    url: str = ""


class ResponseAgentOutput(_SchemaModel):
    """Expected envelope of a ResponseAgent (chat) generation."""
    text_response: str = ""
    components: List[GenUIComponentModel] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    suggested_actions: List[str] = Field(default_factory=list)



# Helpers
def _validate_custom_data(
    data: Any,
    type_def: ComponentTypeDef,
) -> Optional[str]:
    """
    Validate custom component data against its registered JSON Schema.
    Returns an error summary, or None when valid.

    A broken *schema* (developer error) is logged but does not drop the
    component — the host's content should not disappear because of a
    typo in their schema definition.
    """
    try:
        import jsonschema
    except ImportError:
        logger.warning(
            "jsonschema not installed: custom component %r accepted without "
            "schema validation", type_def.name
        )
        return None

    try:
        jsonschema.validate(instance=data, schema=type_def.data_schema)
        return None
    except jsonschema.ValidationError as e:
        return str(e.message)[:200]
    except jsonschema.SchemaError as e:
        logger.warning(
            "Invalid JSON Schema for custom component %r: %s", type_def.name, e
        )
        return None


# A validated component: a Pydantic model or a plain dict {"type", "data", "layout"} for custom types
ValidatedComponent = Union[GenUIComponentModel, Dict[str, Any]]


def validate_components(
    raw_components: List[Any],
    custom_types: Optional[Dict[str, ComponentTypeDef]] = None,
) -> Tuple[List[ValidatedComponent], List[str]]:
    """
    Validate components one by one so a single malformed component
    doesn't invalidate the whole render.

    Built-in types are validated with the Pydantic schemas; types found
    in `custom_types` (registered by the host app) are validated against
    their JSON Schema; anything else is dropped.

    Returns:
        (valid_components, errors) — errors are human-readable summaries
        of what was dropped, for debug metadata and logging.
    """
    valid: List[ValidatedComponent] = []
    errors: List[str] = []
    custom_types = custom_types or {}

    if not isinstance(raw_components, list):
        return [], [f"components is not a list (got {type(raw_components).__name__})"]

    for i, raw in enumerate(raw_components):
        ctype = raw.get("type") if isinstance(raw, dict) else None

        # Custom types registered by the host
        if ctype in custom_types:
            data = raw.get("data")
            if not isinstance(data, dict):
                errors.append(f"component[{i}] type={ctype}: data is not an object")
                continue
            error = _validate_custom_data(data, custom_types[ctype])
            if error:
                summary = f"component[{i}] type={ctype}: {error}"
                errors.append(summary)
                logger.warning("Dropped invalid custom component: %s", summary)
                continue
            cleaned: Dict[str, Any] = {"type": ctype, "data": data}
            if isinstance(raw.get("layout"), dict):
                cleaned["layout"] = raw["layout"]
            valid.append(cleaned)
            continue

        # Built-in types
        try:
            valid.append(_component_adapter.validate_python(raw))
        except ValidationError as e:
            first = e.errors()[0] if e.errors() else {}
            summary = f"component[{i}] type={ctype or 'unknown'}: {first.get('msg', 'invalid')}"
            errors.append(summary)
            logger.warning("Dropped invalid component: %s", summary)

    return valid, errors


def component_to_dict(component: ValidatedComponent) -> Dict[str, Any]:
    """Serialize a validated component back to the wire format."""
    if isinstance(component, dict):
        return component
    return component.model_dump(exclude_none=True)


def zone_output_json_schema(
    custom_types: Optional[Dict[str, ComponentTypeDef]] = None,
) -> Dict[str, Any]:
    """
    JSON schema of the zone output envelope, for provider-native
    structured output (response_format=json_schema).

    When custom component types are in play, their schemas are added to
    the components union — otherwise the provider-side schema would
    steer the model away from the very types the host registered.
    """
    schema = ZoneAgentOutput.model_json_schema()

    if custom_types:
        items = schema.get("properties", {}).get("components", {}).get("items")
        if isinstance(items, dict):
            variants = items.get("oneOf") or items.get("anyOf")
            if isinstance(variants, list):
                for definition in custom_types.values():
                    variants.append({
                        "type": "object",
                        "required": ["type", "data"],
                        "properties": {
                            "type": {"const": definition.name},
                            "data": definition.data_schema,
                            "layout": {"type": "object"},
                        },
                    })
                # The discriminator mapping no longer covers all variants
                items.pop("discriminator", None)

    return schema
