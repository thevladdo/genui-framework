"""
GenUI Backend API
FastAPI application exposing the multi-agent system for GenUI frontend.
"""

import logging
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from api.zone_router import router as zone_router
from pydantic import BaseModel, Field

from config import settings
from agents import get_orchestrator, OrchestratorResult
from rag import create_chunker, create_vector_store

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Request/Response Models
class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class QueryRequest(BaseModel):
    """Request for processing a user query."""
    query: str = Field(..., description="The user's query", min_length=1)
    user_profile: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="User profile data from IndexedDB"
    )
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Recent conversation messages for context"
    )
    behavior_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User behavior data from BehaviorTracker"
    )


class ComponentData(BaseModel):
    """Generic component data structure."""
    type: str
    data: Dict[str, Any]
    layout: Optional[Dict[str, Any]] = None


class ProfileUpdateInstruction(BaseModel):
    """Instructions for updating the user profile in IndexedDB."""
    should_update: bool
    updates: List[Dict[str, Any]]


class BehaviorMeta(BaseModel):
    """Behavior analysis metadata."""
    engagement_score: float
    user_type: str
    session_summary: str
    insights_count: int
    ui_adjustments: List[Dict[str, Any]]


class MetaInfo(BaseModel):
    """Response metadata."""
    confidence: float
    interaction_type: str
    topics: List[str]
    sentiment: str
    behavior: Optional[BehaviorMeta] = None


class QueryResponse(BaseModel):
    """Response from the query endpoint."""
    text: str = Field(..., description="Main text response")
    components: List[ComponentData] = Field(
        default_factory=list,
        description="UI components for GenUI rendering"
    )
    sources: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Source references"
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Suggested follow-up actions"
    )
    profile_updates: ProfileUpdateInstruction
    meta: MetaInfo


class DocumentUploadRequest(BaseModel):
    """Request for uploading documents to the knowledge base."""
    content: str = Field(..., description="Document content")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata (title, url, etc.)"
    )


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    qdrant_connected: bool
    collection_stats: Optional[Dict[str, Any]] = None


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting GenUI Backend...")
    
    # Initialize orchestrator (warms up connections)
    try:
        orchestrator = get_orchestrator()
        logger.info("Orchestrator initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down GenUI Backend...")


# Create FastAPI app
app = FastAPI(
    title="GenUI Backend API",
    description="Multi-agent backend for Generative User Interface system",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zone_router)

# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    Returns system status and Qdrant connection info.
    """
    try:
        vector_store = create_vector_store()
        stats = vector_store.get_collection_stats()
        qdrant_connected = True
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        stats = None
        qdrant_connected = False
    
    return HealthResponse(
        status="healthy" if qdrant_connected else "degraded",
        version="1.0.0",
        qdrant_connected=qdrant_connected,
        collection_stats=stats,
    )


@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a user query through the multi-agent system.
    
    This endpoint:
    1. Retrieves relevant documents from the knowledge base
    2. Generates a structured response using the Response Agent
    3. Analyzes the query for profile updates using the Profile Agent
    4. Analyzes behavior data using the Behave Agent (if provided)
    5. Returns components for GenUI rendering + profile update instructions
    """
    try:
        orchestrator = get_orchestrator()
        
        # Convert conversation history to dict format
        history = None
        if request.conversation_history:
            history = [{"role": m.role, "content": m.content} for m in request.conversation_history]
        
        # Process through orchestrator with async
        result: OrchestratorResult = await orchestrator.process(
            query=request.query,
            user_profile=request.user_profile,
            conversation_history=history,
            behavior_data=request.behavior_data,
        )
        
        # Format response for frontend
        frontend_response = result.to_frontend_response()
        
        # Build meta info with optional behavior data
        meta_data = frontend_response["meta"]
        behavior_meta = None
        if "behavior" in meta_data and meta_data["behavior"]:
            behavior_meta = BehaviorMeta(**meta_data["behavior"])
        
        # Safely extract profile_updates, ensuring should_update is always a boolean
        raw_profile_updates = frontend_response.get("profile_updates", {})
        profile_updates = ProfileUpdateInstruction(
            should_update=bool(raw_profile_updates.get("should_update", False)),
            updates=raw_profile_updates.get("updates", [])
        )
        
        return QueryResponse(
            text=frontend_response["text"],
            components=[ComponentData(**c) for c in frontend_response["components"]],
            sources=frontend_response["sources"],
            suggested_actions=frontend_response["suggested_actions"],
            profile_updates=profile_updates,
            meta=MetaInfo(
                confidence=meta_data["confidence"],
                interaction_type=meta_data["interaction_type"],
                topics=meta_data["topics"],
                sentiment=meta_data["sentiment"],
                behavior=behavior_meta,
            ),
        )
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/documents")
async def upload_document(
    request: DocumentUploadRequest,
    background_tasks: BackgroundTasks
):
    """
    Upload a document to the knowledge base.
    
    The document will be chunked semantically and indexed in Qdrant.
    Processing happens in the background.
    """
    try:
        chunker = create_chunker()
        vector_store = create_vector_store()
        
        # Process synchronously for small documents, async for large
        content_length = len(request.content)
        
        if content_length < 10000:  # ~2500 words
            # Process immediately
            chunks = chunker.chunk_text(
                text=request.content,
                metadata=request.metadata,
                source_name=request.metadata.get("title", "uploaded_document"),
            )
            indexed = vector_store.index_chunks(chunks)
            
            return {
                "status": "completed",
                "chunks_created": len(chunks),
                "chunks_indexed": indexed,
            }
        else:
            # Schedule for background processing
            background_tasks.add_task(
                _process_document_background,
                request.content,
                request.metadata,
            )
            
            return {
                "status": "processing",
                "message": "Document queued for background processing",
            }
            
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _process_document_background(content: str, metadata: Dict[str, Any]):
    """Background task for processing large documents."""
    try:
        chunker = create_chunker()
        vector_store = create_vector_store()
        
        chunks = chunker.chunk_text(
            text=content,
            metadata=metadata,
            source_name=metadata.get("title", "uploaded_document"),
        )
        vector_store.index_chunks(chunks)
        
        logger.info(f"Background document processing completed: {len(chunks)} chunks")
        
    except Exception as e:
        logger.error(f"Background document processing failed: {e}")


@app.delete("/api/v1/documents/{source_name}")
async def delete_document(source_name: str):
    """
    Delete a document from the knowledge base by source name.
    """
    try:
        vector_store = create_vector_store()
        success = vector_store.delete_by_source(source_name)
        
        if success:
            return {"status": "deleted", "source": source_name}
        else:
            raise HTTPException(status_code=500, detail="Deletion failed")
            
    except Exception as e:
        logger.error(f"Document deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/documents/stats")
async def get_document_stats():
    """
    Get statistics about the document knowledge base.
    """
    try:
        vector_store = create_vector_store()
        stats = vector_store.get_collection_stats()
        
        return {
            "status": "ok",
            "stats": stats,
        }
        
    except Exception as e:
        logger.error(f"Failed to get document stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Profile management endpoints (for frontend IndexedDB sync)

class ProfileSyncRequest(BaseModel):
    """Request for syncing profile data."""
    user_id: str
    profile_data: Dict[str, Any]


@app.post("/api/v1/profile/sync")
async def sync_profile(request: ProfileSyncRequest):
    """
    Sync user profile from IndexedDB.
    
    This endpoint receives profile data from the frontend
    and can be used for server-side analytics or backup.
    Currently just acknowledges receipt - extend as needed.
    """
    logger.info(f"Profile sync received for user: {request.user_id}")
    
    # Here you could:
    # - Store profile in a database for analytics
    # - Validate profile structure
    # - Trigger profile-based recommendations
    
    return {
        "status": "synced",
        "user_id": request.user_id,
    }


# Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)