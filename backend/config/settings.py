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
    embedding_model: str = Field(default="text-embedding-3-small", description="Model for embeddings")
    
    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "genui_documents"
    qdrant_vector_size: int = 1536  # OpenAI text-embedding-3-small dimension
    
    # RAG Configuration
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k_retrieval: int = 5
    similarity_threshold: float = 0.7

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

    # Rate Limiting (per client key, per minute; 0 = disabled)
    rate_limit_per_minute: int = 120

    # Audit Log
    audit_log_enabled: bool = Field(
        default=True,
        description="Record what was shown to whom (zone renders, queries, profile changes)"
    )
    audit_log_path: Optional[str] = Field(
        default=None,
        description="JSONL file path; empty = emit on the 'genui.audit' logger"
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


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()
