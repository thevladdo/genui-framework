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
    
    # Semantic Chunking (LlamaIndex)
    use_semantic_chunking: bool = True
    breakpoint_percentile_threshold: int = 95
    buffer_size: int = 1
    
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
