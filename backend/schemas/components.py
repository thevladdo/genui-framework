"""
Component Schemas Module
Single source of truth for the structure of LLM-generated UI components.

These schemas serve two purposes:
1. They are converted to a JSON schema and passed to the LLM provider as
   native structured output (response_format), so the model is constrained
   at generation time.
2. Every component coming back from the model is validated against them
   server-side before reaching the frontend: an invalid component is
   dropped (and reported), it never breaks the rest of the render.

The component vocabulary mirrors the frontend renderers in
frontend/src/components/ (BentoComponent, ChartComponent, TextComponent,
ButtonsComponent). Field names are snake_case here; the frontend
ComponentRenderer normalizes them to camelCase.
"""

import logging
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from .registry import ComponentTypeDef

logger = logging.getLogger(__name__)

# Version of the component contract carried by every API response
# (zone renders and /query). Bump it when a component's shape changes
# incompatibly or a new built-in type ships: an already-deployed
# frontend bundle can then detect a newer backend and degrade unknown
# types silently instead of breaking the end user's page.
GENUI_CONTRACT_VERSION = 1


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



# Enterprise section components.
# Image-optional pattern: layout is EXPLICIT so the LLM always picks a
# variant and the frontend knows which shape to render. Validators
# enforce coherence: "with-image" without an image URL is invalid (the
# component gets dropped, never rendered half-empty).
ImageLayout = Literal["with-image", "text-only"]


class CTALinkModel(_SchemaModel):
    label: str = Field(..., min_length=1)
    url: Optional[str] = None


class FeatureTabContent(_SchemaModel):
    layout: ImageLayout = "text-only"
    badge: Optional[str] = None
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    button: Optional[CTALinkModel] = None
    image_url: Optional[str] = None

    @model_validator(mode="after")
    def _image_coherence(self) -> "FeatureTabContent":
        if self.layout == "with-image" and not self.image_url:
            raise ValueError("layout 'with-image' requires image_url")
        return self


class FeatureTab(_SchemaModel):
    label: str = Field(..., min_length=1)
    icon: Optional[str] = Field(default=None, max_length=8)
    content: FeatureTabContent


class TabsFeatureData(_SchemaModel):
    """Tabbed feature section (plan comparison, SaaS highlights)."""
    badge: Optional[str] = None
    heading: str = Field(..., min_length=1)
    description: Optional[str] = None
    tabs: List[FeatureTab] = Field(..., min_length=1, max_length=6)


class StepItem(_SchemaModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    image_url: Optional[str] = None


class StepsSectionData(_SchemaModel):
    """Animated step sequence (onboarding, purchase flow)."""
    layout: ImageLayout = "text-only"
    steps: List[StepItem] = Field(..., min_length=1, max_length=8)
    autoplay: Optional[bool] = None
    interval: Optional[int] = Field(default=None, ge=1500, le=20000)

    @model_validator(mode="after")
    def _image_coherence(self) -> "StepsSectionData":
        if self.layout == "with-image" and not any(s.image_url for s in self.steps):
            raise ValueError("layout 'with-image' requires at least one step image_url")
        return self


class StatItem(_SchemaModel):
    value: str = Field(..., min_length=1, max_length=24)
    label: str = Field(..., min_length=1)
    description: Optional[str] = None


class StatsBannerData(_SchemaModel):
    """Numeric metrics grid: pure text, values typically from RAG."""
    stats: List[StatItem] = Field(..., min_length=1, max_length=8)
    columns: Optional[Literal[2, 3, 4]] = None


class TestimonialItem(_SchemaModel):
    quote: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: Optional[str] = None
    company: Optional[str] = None
    avatar_url: Optional[str] = None


class TestimonialCarouselData(_SchemaModel):
    """Quote carousel; missing avatars degrade to initials."""
    testimonials: List[TestimonialItem] = Field(..., min_length=1, max_length=12)
    autoplay: Optional[bool] = None
    interval: Optional[int] = Field(default=None, ge=2500, le=30000)


class PricingPlanModel(_SchemaModel):
    name: str = Field(..., min_length=1)
    price: str = Field(..., min_length=1, max_length=24)
    period: Optional[str] = Field(default=None, max_length=16)
    description: Optional[str] = None
    features: List[str] = Field(default_factory=list, max_length=16)
    cta: Optional[CTALinkModel] = None
    highlighted: Optional[bool] = None
    flag: Optional[str] = Field(default=None, max_length=32)


class PricingCardsData(_SchemaModel):
    """Plan grid; 'detailed' adds a feature comparison table."""
    plans: List[PricingPlanModel] = Field(..., min_length=1, max_length=4)
    variant: Literal["compact", "detailed"] = "compact"


class ContentGridItemModel(_SchemaModel):
    layout: ImageLayout = "text-only"
    title: str = Field(..., min_length=1)
    category: Optional[str] = None
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None

    @model_validator(mode="after")
    def _image_coherence(self) -> "ContentGridItemModel":
        if self.layout == "with-image" and not self.image_url:
            raise ValueError("layout 'with-image' requires image_url")
        return self


class ContentGridData(_SchemaModel):
    """Blog/news card grid with per-item image-optional layout."""
    items: List[ContentGridItemModel] = Field(..., min_length=1, max_length=12)
    columns: Optional[Literal[2, 3, 4]] = None


class HeroBannerData(_SchemaModel):
    """Parametric hero: split (text+image) | centered | minimal."""
    variant: Literal["split", "centered", "minimal"] = "centered"
    badge: Optional[str] = None
    headline: str = Field(..., min_length=1)
    subheadline: Optional[str] = None
    primary_cta: Optional[CTALinkModel] = None
    secondary_cta: Optional[CTALinkModel] = None
    image_url: Optional[str] = None

    @model_validator(mode="after")
    def _image_coherence(self) -> "HeroBannerData":
        if self.variant == "split" and not self.image_url:
            raise ValueError("variant 'split' requires image_url")
        return self


class CaseStudyMetric(_SchemaModel):
    """One result figure of a case (value is numeric-grounded downstream)."""
    value: str = Field(..., min_length=1, max_length=24)
    label: str = Field(..., min_length=1)
    description: Optional[str] = None


class CaseStudyItem(_SchemaModel):
    """
    A project/case. Everything but the title is optional and degrades on
    its own: no image, no figures, no named reference are all valid.
    """
    title: str = Field(..., min_length=1)
    summary: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    image_url: Optional[str] = None
    metrics: List[CaseStudyMetric] = Field(default_factory=list, max_length=4)


class CaseStudiesData(_SchemaModel):
    """Editorial project/case studies: image + summary + optional figures."""
    heading: Optional[str] = None
    subheading: Optional[str] = None
    cases: List[CaseStudyItem] = Field(..., min_length=1, max_length=6)


class QuoteData(_SchemaModel):
    """
    A single editorial quote / manifesto. Author, role, avatar and the
    top logo are each optional and omitted when absent (never invented,
    no initials fallback: the statement is the point).
    """
    quote: str = Field(..., min_length=1)
    author: Optional[str] = None
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    logo_url: Optional[str] = None
    logo_label: Optional[str] = None


class LogoItem(_SchemaModel):
    """One logo: an image plus its accessible name, optionally linked."""
    image_url: str = Field(..., min_length=1)
    alt: str = Field(..., min_length=1)
    url: Optional[str] = None


class LogoWallData(_SchemaModel):
    """
    A grid of logos (clients, technologies, partners). Not client-specific:
    `heading` labels the wall ("Selected clients", "Our stack"). The overall
    cta (label + url) drives the hover reveal; without cta_url the grid is
    a plain static wall.
    """
    heading: Optional[str] = None
    logos: List[LogoItem] = Field(..., min_length=1, max_length=16)
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None


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


class TabsFeatureComponentModel(_ComponentBase):
    type: Literal["tabs_feature"]
    data: TabsFeatureData


class StepsSectionComponentModel(_ComponentBase):
    type: Literal["steps_section"]
    data: StepsSectionData


class StatsBannerComponentModel(_ComponentBase):
    type: Literal["stats_banner"]
    data: StatsBannerData


class TestimonialCarouselComponentModel(_ComponentBase):
    type: Literal["testimonial_carousel"]
    data: TestimonialCarouselData


class PricingCardsComponentModel(_ComponentBase):
    type: Literal["pricing_cards"]
    data: PricingCardsData


class ContentGridComponentModel(_ComponentBase):
    type: Literal["content_grid"]
    data: ContentGridData


class HeroBannerComponentModel(_ComponentBase):
    type: Literal["hero_banner"]
    data: HeroBannerData


class CaseStudiesComponentModel(_ComponentBase):
    type: Literal["case_studies"]
    data: CaseStudiesData


class QuoteComponentModel(_ComponentBase):
    type: Literal["quote"]
    data: QuoteData


class LogoWallComponentModel(_ComponentBase):
    type: Literal["logo_wall"]
    data: LogoWallData


GenUIComponentModel = Annotated[
    Union[
        TextComponentModel,
        BentoComponentModel,
        ChartComponentModel,
        ButtonsComponentModel,
        TabsFeatureComponentModel,
        StepsSectionComponentModel,
        StatsBannerComponentModel,
        TestimonialCarouselComponentModel,
        PricingCardsComponentModel,
        ContentGridComponentModel,
        HeroBannerComponentModel,
        CaseStudiesComponentModel,
        QuoteComponentModel,
        LogoWallComponentModel,
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
    component. The host's content should not disappear because of a
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
        (valid_components, errors): errors are human-readable summaries
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


def downgrade_image_variants(
    components: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Re-cohere components whose image was removed by the URL guard.

    A component can be generated as an image variant (hero "split",
    steps / tabs / content-grid "with-image"), pass validation because
    an image_url was present, then have that URL stripped by the guard
    (it was a link, not an image). That would leave an image-shaped hole.
    Here the variant is degraded to its text-only form in place instead,
    so the render stays coherent. Runs after the guard on both paths.
    """
    for component in components:
        if not isinstance(component, dict):
            continue
        data = component.get("data")
        if not isinstance(data, dict):
            continue
        ctype = component.get("type")

        if ctype == "hero_banner":
            if data.get("variant") == "split" and not data.get("image_url"):
                data["variant"] = "centered"

        elif ctype == "steps_section":
            steps = data.get("steps") or []
            has_image = any(
                isinstance(s, dict) and s.get("image_url") for s in steps
            )
            if data.get("layout") == "with-image" and not has_image:
                data["layout"] = "text-only"

        elif ctype == "content_grid":
            for item in data.get("items") or []:
                if (
                    isinstance(item, dict)
                    and item.get("layout") == "with-image"
                    and not item.get("image_url")
                ):
                    item["layout"] = "text-only"

        elif ctype == "tabs_feature":
            for tab in data.get("tabs") or []:
                content = tab.get("content") if isinstance(tab, dict) else None
                if (
                    isinstance(content, dict)
                    and content.get("layout") == "with-image"
                    and not content.get("image_url")
                ):
                    content["layout"] = "text-only"

    return components


def apply_component_budget(
    components: List[Dict[str, Any]],
    limit: Optional[int],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Keep at most `limit` components; report what the budget cut.

    A zone is one band of a host page, not a page: the model is told the
    budget in the prompt, and this enforces it after validation (order
    preserved, first components win). Pinned enforcement runs AFTER the
    budget on purpose: the pinned guarantee may exceed it rather than be
    silently dropped. limit None/<=0 disables the budget.
    """
    if not limit or limit <= 0 or len(components) <= limit:
        return components, []
    dropped = [
        f"{c.get('type', 'component')}: over the zone component budget ({limit})"
        for c in components[limit:]
    ]
    return components[:limit], dropped


def zone_output_json_schema(
    custom_types: Optional[Dict[str, ComponentTypeDef]] = None,
) -> Dict[str, Any]:
    """
    JSON schema of the zone output envelope, for provider-native
    structured output (response_format=json_schema).

    When custom component types are in play, their schemas are added to
    the components union, otherwise the provider-side schema would
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
