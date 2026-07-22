"""
GenUI Backend Configuration
Centralized settings management using pydantic-settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, Union
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "GenUI Backend"
    debug: bool = False
    api_prefix: str = "/api/v1"
    
    # LLM Configuration
    llm_provider: str = Field(default="openai", description="LLM provider: openai, anthropic, gemini")
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Custom OpenAI-compatible endpoint (Azure, vLLM, Ollama, ...)"
    )
    
    # Model Selection
    response_model: str = Field(default="gpt-4o-mini", description="Model for response generation")
    profile_model: str = Field(default="gpt-4o-mini", description="Model for profile analysis")

    # Embeddings (BYOK, like the LLM: documents embed where YOU choose)
    embedding_model: str = Field(default="text-embedding-3-small", description="Model for embeddings")
    embedding_provider: str = Field(
        default="openai",
        description="Embedding provider: openai (covers any OpenAI-compatible "
                    "endpoint via EMBEDDING_BASE_URL) or gemini. Independent of "
                    "LLM_PROVIDER; misconfiguration fails loudly, never falls "
                    "back to another provider"
    )
    embedding_api_key: Optional[str] = Field(
        default=None,
        description="Key for the embedding endpoint; falls back to the "
                    "provider's LLM key (OPENAI_API_KEY / GOOGLE_API_KEY)"
    )
    embedding_base_url: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible embedding endpoint (vLLM, Ollama, TEI, "
                    "RunPod); falls back to OPENAI_BASE_URL so an all-local "
                    "deployment keeps embeddings local too"
    )
    embedding_dimensions: Optional[int] = Field(
        default=None,
        description="Vector size of the embedding model; unset = derived from "
                    "the model (known models, or a one-time probe). Replaces "
                    "the old QDRANT_VECTOR_SIZE constant"
    )

    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "genui_documents"
    
    # RAG Configuration
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k_retrieval: int = 5
    similarity_threshold: float = 0.35

    # Document Extraction (file uploads)
    extractor_backend: str = Field(
        default="local",
        description="local (pypdf/docx/bs4, zero deps, data stays in-house) | "
                    "docling (better tables/layout, no GPU, local) | "
                    "glmocr (state-of-the-art incl. scans/images; self-hosted "
                    "via GLMOCR_BASE_URL keeps data in-house, Z.ai API does not)"
    )
    glmocr_api_key: Optional[str] = Field(
        default=None,
        description="Z.ai API key for glmocr cloud mode (documents leave your infra)"
    )
    glmocr_base_url: Optional[str] = Field(
        default=None,
        description="Self-hosted GLM-OCR endpoint (vLLM/SGLang/Ollama)"
    )
    
    # Semantic Chunking (LlamaIndex)
    use_semantic_chunking: bool = True
    breakpoint_percentile_threshold: int = 95
    buffer_size: int = 1

    # Zone Render Cache (segment-based, stale-while-revalidate)
    zone_cache_enabled: bool = Field(
        default=True,
        description="Cache zone renders per (zone config, segment) instead of calling the LLM per request"
    )
    zone_cache_fresh_ttl: int = Field(
        default=300,
        description="Seconds a cached render is served without revalidation"
    )
    zone_cache_stale_ttl: int = Field(
        default=86400,
        description="Seconds a cached render may still be served while refreshing in background"
    )
    zone_cache_lock_ttl: int = Field(
        default=60,
        description="Seconds a single-flight refresh lock is held"
    )
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis URL (e.g. redis://localhost:6379/0). Empty = in-memory cache"
    )

    # Profile Segmentation
    segment_min_confidence: float = Field(
        default=0.5,
        description="Profile entries below this confidence are ignored when segmenting"
    )
    segment_max_interests: int = Field(
        default=3,
        description="Max interest dimensions per segment (bounds segment cardinality)"
    )

    # Output Guarantees
    url_whitelist_enabled: bool = Field(
        default=True,
        description="Strip generated URLs that were not present in the input "
                    "(pinned content, prompts, RAG documents, page context). "
                    "Dangerous schemes (javascript:, data:) are always stripped."
    )
    numeric_grounding_enabled: bool = Field(
        default=True,
        description="Remove displayed numbers (stats_banner values, pricing "
                    "prices, chart points) that do not trace to a number "
                    "present in the input. Same model as the URL whitelist: "
                    "check the output, don't trust the instruction."
    )
    content_policy: str = Field(
        default="",
        description='Per-tenant banned terms, enforced post-generation. JSON: '
                    '{"*": {"banned_terms": [...]}, "<tenant>": {"banned_terms": '
                    '[...]}}. A component containing a banned term is dropped; '
                    'chat text is redacted. Empty = disabled.'
    )

    # Authentication (comma-separated "key" or "key:tenant" entries).
    # No keys configured = auth disabled.
    client_api_keys: Union[list[str], str] = Field(
        default_factory=list,
        description="Browser-facing keys: identify the tenant, gate rate limits"
    )
    admin_api_keys: Union[list[str], str] = Field(
        default_factory=list,
        description="Server-to-server keys: documents, warmup, cache stats"
    )

    # Explicit dev mode: the ONLY way to run without keys (fail-open).
    # Default is fail-closed: no keys configured = privileged routes refuse.
    genui_dev_open: bool = Field(
        default=False,
        description="Explicitly allow running with no API keys / no user-token "
                    "secrets (open, dev only). Never set in production."
    )

    # Signed user identity ("secret:tenant" entries, like the API keys).
    user_token_secrets: Union[list[str], str] = Field(
        default_factory=list,
        description="Per-tenant HMAC secrets for user identity tokens; "
                    "required for /profile and personalized renders in production"
    )

    # Rate Limiting (per client key, per minute; 0 = disabled)
    rate_limit_per_minute: int = 120

    # Cost controls (protect the tenant's BYOK LLM key from public-key traffic)
    llm_timeout_seconds: Optional[float] = Field(
        default=60.0,
        description="Per-call timeout for LLM and embedding provider requests. "
                    "A slow provider (cold RunPod endpoint, hung gateway) must "
                    "never hold requests open for the SDK default of 10 minutes. "
                    "Empty = SDK default"
    )
    llm_budget_per_hour: int = Field(
        default=0,
        description="Per-tenant cap on LLM generations per hour (cold misses, "
                    "stale refreshes, renders with the cache disabled). Over "
                    "the cap: cached renders keep being served, new generations "
                    "return 429. Admin-triggered renders (warmup, admin 'live') "
                    "are exempt. Shares the rate-limit Redis store, so the cap "
                    "is consistent across workers. 0 = disabled"
    )
    zone_batch_max: int = Field(
        default=10,
        description="Max zones per /zone/batch-render request (413 above). "
                    "Each zone in a client batch also counts individually "
                    "against the per-key rate limit"
    )

    zone_max_components: int = Field(
        default=2,
        description="Default component budget per zone render. A zone is one "
                    "band of a host page, not a page: extra components are "
                    "cut after validation and reported in meta.sanitization. "
                    "Overridable per request/registry via max_components"
    )

    # Audit Log
    audit_log_enabled: bool = Field(
        default=True,
        description="Record what was shown to whom (zone renders, queries, profile changes)"
    )
    audit_log_path: Optional[str] = Field(
        default=None,
        description="JSONL file path; empty (production default) = emit on the "
                    "'genui.audit' logger for the host's log pipeline"
    )
    audit_log_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Rotate the audit file at this size (0 = never rotate). "
                    "Rotation is per-process: the file sink is for single-worker "
                    "runs; multi-worker deployments use the logger sink"
    )
    audit_log_backup_count: int = Field(
        default=5,
        description="Rotated audit files to keep (audit.jsonl.1 ... .N); "
                    "older ones are deleted"
    )

    # Server-side Profiles
    profile_ttl_seconds: int = Field(
        default=0,
        description="Profile retention in seconds, refreshed on write (0 = keep forever)"
    )

    # Experimentation (personalization uplift measurement)
    holdout_percent: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Share of identified users served the NON-personalized render "
                    "(control arm) to measure uplift. 0 = experiment disabled"
    )
    holdout_salt: str = Field(
        default="genui-exp-1",
        description="Experiment identifier: changing it reshuffles arm assignments "
                    "(= starts a new experiment)"
    )

    # Tracing (OpenTelemetry)
    tracing_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing (FastAPI + zone renders + LLM calls)"
    )
    otlp_endpoint: Optional[str] = Field(
        default=None,
        description="OTLP gRPC collector endpoint (e.g. http://localhost:4317); "
                    "empty = console exporter"
    )
    
    # CORS
    cors_origins: Union[list[str], str] = ["http://localhost:3000", "http://localhost:5173"]
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Split comma-separated string
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()
