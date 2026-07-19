"""
GenUI Backend API
FastAPI application exposing the multi-agent system for GenUI frontend.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, File, Form, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from api.deps import get_profile_store
from api.events_router import router as events_router
from api.zone_router import router as zone_router
from pydantic import BaseModel, Field

from auth import AuthContext
from auth.dependencies import (
    USER_TOKEN_HEADER,
    check_user_access,
    get_audit_logger,
    require_admin,
    require_client,
)
from auth.identity import AuthError
from llm.embeddings import EmbeddingConfigError
from llm.factory import llm_configured
from config import settings
from agents import get_orchestrator, OrchestratorResult
from metrics.ops import get_ops_metrics
from rag import create_chunker, create_vector_store
from schemas.components import GENUI_CONTRACT_VERSION
from utils.redis_conn import shared_redis
from utils.tracing import span

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
    user_id: Optional[str] = Field(
        default=None,
        description="User ID: enables the server-side profile (authoritative) "
                    "and the audit trail"
    )
    user_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Client-side profile (IndexedDB cache). Used to seed the "
                    "server profile; ignored when a server profile exists"
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
    sanitization: Optional[Dict[str, Any]] = Field(
        default=None,
        description="What the guarantee chain removed: removed_urls, "
                    "dropped_components, removed_numbers, policy_violations"
    )


class QueryResponse(BaseModel):
    """Response from the query endpoint."""
    contract_version: int = Field(
        default=GENUI_CONTRACT_VERSION,
        description="Component contract version of the responding backend; "
                    "older frontend bundles use it to detect newer contracts "
                    "and silently skip unknown component types."
    )
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
    """
    Dependency statuses only: safe for unauthenticated monitors.
    Collection internals live behind the admin key (/documents/stats).
    """
    status: str
    version: str
    qdrant_connected: bool
    # Redis state as the stores see it: "connected" | "reconnecting"
    # (configured but unreachable, in-memory fallback active) | "disabled"
    # (not configured — single-process dev only).
    redis: Optional[str] = None
    # "configured" | "unconfigured": key/endpoint presence for the selected
    # provider. Reachability shows up as error counters in /metrics.
    llm: str = "unconfigured"


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting GenUI Backend...")

    # Tracing (no-op unless TRACING_ENABLED=true)
    from utils.tracing import setup_tracing
    setup_tracing(app)

    # Initialize orchestrator (warms up connections)
    try:
        get_orchestrator()
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
app.include_router(events_router)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    """Translate framework-free auth failures (auth.identity) to HTTP."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(EmbeddingConfigError)
async def embedding_config_error_handler(
    request: Request, exc: EmbeddingConfigError
) -> JSONResponse:
    """
    An unconfigured or mismatched embedding fails loudly with the fix in
    the message — never a silent OpenAI fallback or a mute no-RAG render.
    """
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# Observability: HTTP metrics middleware + health/readiness/liveness + /metrics
@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next):
    """
    Request count and latency per route template (bounded label set: an
    unmatched path is labeled "unmatched", never echoed — random 404
    probing must not explode metric cardinality).
    """
    ops = get_ops_metrics()
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        route = request.scope.get("route")
        path = getattr(route, "path", None) or "unmatched"
        ops.observe(
            "genui_http_requests_total",
            {"method": request.method, "path": path, "status": "500"},
        )
        raise
    route = request.scope.get("route")
    path = getattr(route, "path", None) or "unmatched"
    labels = {"method": request.method, "path": path}
    ops.observe(
        "genui_http_requests_total", {**labels, "status": str(response.status_code)}
    )
    ops.observe(
        "genui_http_request_seconds_sum", labels, time.perf_counter() - start
    )
    ops.observe("genui_http_request_seconds_count", labels)
    return response


async def _dependency_health() -> HealthResponse:
    """One truthful snapshot of the real dependencies (Qdrant, Redis, LLM)."""
    try:
        vector_store = create_vector_store()
        qdrant_connected = bool(vector_store.get_collection_stats())
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        qdrant_connected = False

    # Probe the same handle the stores use.
    redis_status = await shared_redis(settings.redis_url).probe()
    redis_ok = redis_status == "connected" or (
        redis_status == "disabled" and settings.genui_dev_open
    )

    llm_ok = llm_configured()

    return HealthResponse(
        status="healthy" if (qdrant_connected and redis_ok and llm_ok) else "degraded",
        version="1.0.0",
        qdrant_connected=qdrant_connected,
        redis=redis_status,
        llm="configured" if llm_ok else "unconfigured",
    )


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Aggregate dependency health for dashboards and uptime monitors.
    Always 200; the body carries the truth (status: healthy | degraded).
    """
    return await _dependency_health()


@app.get("/live")
async def liveness():
    """Process liveness: 200 as long as the event loop answers."""
    return {"status": "alive"}


@app.get("/ready")
async def readiness():
    """
    Readiness for load balancers: 503 only when the process cannot serve
    at all (LLM unconfigured = every render/query fails). A degraded
    dependency (Redis blip, Qdrant down) keeps serving via fallbacks, so
    it stays 200: failing readiness on every replica for a shared
    dependency would turn degradation into a full outage.
    """
    health = await _dependency_health()
    status_code = 200 if health.llm == "configured" else 503
    return JSONResponse(status_code=status_code, content=health.model_dump())


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics(auth: AuthContext = Depends(require_admin)):
    """
    Prometheus text exposition (admin key: tenant names and traffic
    volumes are operator data). Scrape with
    `authorization: credentials: <admin key>` in prometheus.yml.
    """
    text = await get_ops_metrics().render_text(
        extra_gauges={"genui_llm_configured": 1.0 if llm_configured() else 0.0}
    )
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """
    Process a user query through the multi-agent system.

    This endpoint:
    1. Resolves the server-side profile (authoritative when user_id is given)
    2. Retrieves relevant documents from the knowledge base
    3. Generates a structured response using the Response Agent
    4. Analyzes the query for profile updates using the Profile Agent
    5. Analyzes behavior data using the Behave Agent (if provided)
    6. Persists profile updates server-side and audit-logs the interaction
    """
    check_user_access(auth, request.user_id, user_token)

    try:
        orchestrator = get_orchestrator()
        profile_store = get_profile_store()

        # Server-side profile is authoritative, the client copy seeds it
        if request.user_id:
            try:
                server_profile = await profile_store.get(auth.tenant, request.user_id)
                if server_profile:
                    request.user_profile = server_profile
                elif request.user_profile:
                    request.user_profile = await profile_store.sync_client_profile(
                        auth.tenant, request.user_id, request.user_profile
                    )
            except Exception as e:
                logger.warning(f"Profile resolution failed for {request.user_id}: {e}")

        # Convert conversation history to dict format
        history = None
        if request.conversation_history:
            history = [{"role": m.role, "content": m.content} for m in request.conversation_history]

        # Process through orchestrator with async. 
        # The span ties the genui.llm.* client spans to this query,
        # the counters are the SRE's view on chat LLM spend and failures.
        ops = get_ops_metrics()
        started = time.perf_counter()
        try:
            with span("genui.query", tenant=auth.tenant):
                result: OrchestratorResult = await orchestrator.process(
                    query=request.query,
                    user_profile=request.user_profile,
                    conversation_history=history,
                    behavior_data=request.behavior_data,
                    tenant=auth.tenant,
                )
        except Exception:
            ops.observe_generation(auth.tenant, "query", outcome="error")
            raise
        ops.observe_generation(auth.tenant, "query", time.perf_counter() - started)

        # Format response for frontend
        frontend_response = result.to_frontend_response()

        # Persist agent-derived profile updates server-side
        profile_updates = frontend_response.get("profile_updates", {})
        if request.user_id and profile_updates.get("updates"):
            try:
                await profile_store.apply_updates(
                    auth.tenant, request.user_id, profile_updates["updates"]
                )
            except Exception as e:
                logger.warning(f"Profile update persistence failed: {e}")

        # Audit: what was answered/shown to whom
        get_audit_logger().log(
            "query",
            tenant=auth.tenant,
            user_id=request.user_id,
            key=auth.key_fingerprint,
            query=request.query[:200],
            confidence=frontend_response["meta"].get("confidence"),
            component_count=len(frontend_response["components"]),
            profile_updates_applied=len(profile_updates.get("updates", [])),
        )
        
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
                sanitization=meta_data.get("sanitization"),
            ),
        )
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/documents")
async def upload_document(
    request: DocumentUploadRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_admin),
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

        if content_length < 10000:
            request.metadata.setdefault(
                "indexed_at", datetime.now(timezone.utc).isoformat()
            )
            chunks = chunker.chunk_text(
                text=request.content,
                metadata=request.metadata,
                source_name=request.metadata.get("title", "uploaded_document"),
            )
            indexed = vector_store.index_chunks(chunks, tenant=auth.tenant)

            get_audit_logger().log(
                "document_upload",
                tenant=auth.tenant,
                key=auth.key_fingerprint,
                source=request.metadata.get("title", "uploaded_document"),
                chunks_indexed=indexed,
            )

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
                auth.tenant,
            )

            return {
                "status": "processing",
                "message": "Document queued for background processing",
            }

    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/documents/upload")
async def upload_document_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    auth: AuthContext = Depends(require_admin),
):
    """
    Upload a document as a file (PDF, DOCX, HTML, TXT, MD).

    Text is extracted server-side, semantically chunked, and indexed in
    the tenant's knowledge base. The optional `url` becomes part of the
    URL whitelist when the AI cites this document.
    """
    from rag.extractors import ExtractionError, configured_backend, extract_text

    content = await file.read()
    source_name = title or file.filename or "uploaded_file"
    extractor = configured_backend()

    try:
        text = extract_text(file.filename or "", content)
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))

    try:
        chunker = create_chunker()
        vector_store = create_vector_store()

        metadata: Dict[str, Any] = {
            "title": source_name,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        if url:
            metadata["url"] = url
        if file.filename:
            metadata["file_type"] = file.filename.rsplit(".", 1)[-1].lower()

        chunks = chunker.chunk_text(
            text=text,
            metadata=metadata,
            source_name=source_name,
        )
        indexed = vector_store.index_chunks(chunks, tenant=auth.tenant)

        get_audit_logger().log(
            "document_upload",
            tenant=auth.tenant,
            key=auth.key_fingerprint,
            source=source_name,
            file_name=file.filename,
            extractor=extractor,
            extracted_chars=len(text),
            chunks_indexed=indexed,
        )

        return {
            "status": "completed",
            "source": source_name,
            "extractor": extractor,
            "extracted_chars": len(text),
            "chunks_created": len(chunks),
            "chunks_indexed": indexed,
        }

    except Exception as e:
        logger.error(f"File upload failed for {source_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _process_document_background(
    content: str,
    metadata: Dict[str, Any],
    tenant: str,
):
    """Background task for processing large documents."""
    try:
        chunker = create_chunker()
        vector_store = create_vector_store()

        metadata.setdefault("indexed_at", datetime.now(timezone.utc).isoformat())
        chunks = chunker.chunk_text(
            text=content,
            metadata=metadata,
            source_name=metadata.get("title", "uploaded_document"),
        )
        vector_store.index_chunks(chunks, tenant=tenant)

        logger.info(f"Background document processing completed: {len(chunks)} chunks")

    except Exception as e:
        logger.error(f"Background document processing failed: {e}")


@app.get("/api/v1/documents")
async def list_documents(auth: AuthContext = Depends(require_admin)):
    """
    List the documents in the tenant's knowledge base, with chunk counts.
    """
    try:
        vector_store = create_vector_store()
        documents = vector_store.list_documents(tenant=auth.tenant)
        return {
            "tenant": auth.tenant,
            "documents": documents,
            "count": len(documents),
        }
    except Exception as e:
        logger.error(f"Document listing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DocumentSearchRequest(BaseModel):
    """Preview what the AI would retrieve for a query."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


@app.post("/api/v1/documents/search")
async def search_documents(
    request: DocumentSearchRequest,
    auth: AuthContext = Depends(require_admin),
):
    """
    Search the tenant's knowledge base and return the passages (with
    similarity scores) that a zone render would see for this query.
    Useful for content debugging: "why does the AI show X?".
    """
    try:
        vector_store = create_vector_store()
        results = await vector_store.search_async(
            query=request.query,
            top_k=request.top_k,
            score_threshold=0.0,  # preview shows everything; real scores are the point
            tenant=auth.tenant,
        )
        return {
            "query": request.query,
            "results": [
                {
                    "content": r.content,
                    "score": round(r.score, 4),
                    "source_document": r.metadata.get("source_document"),
                    "url": r.metadata.get("url"),
                }
                for r in results
            ],
        }
    except Exception as e:
        logger.error(f"Document search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/documents/{source_name}")
async def delete_document(
    source_name: str,
    auth: AuthContext = Depends(require_admin),
):
    """
    Delete a document from the tenant's knowledge base by source name.
    """
    try:
        vector_store = create_vector_store()
        success = vector_store.delete_by_source(source_name, tenant=auth.tenant)

        if success:
            get_audit_logger().log(
                "document_delete",
                tenant=auth.tenant,
                key=auth.key_fingerprint,
                source=source_name,
            )
            return {"status": "deleted", "source": source_name}
        else:
            raise HTTPException(status_code=500, detail="Deletion failed")

    except Exception as e:
        logger.error(f"Document deletion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/documents/stats")
async def get_document_stats(auth: AuthContext = Depends(require_admin)):
    """
    Get statistics about the document knowledge base (tenant-aware).
    """
    try:
        vector_store = create_vector_store()
        stats = vector_store.get_collection_stats(tenant=auth.tenant)

        return {
            "status": "ok",
            "tenant": auth.tenant,
            "stats": stats,
        }

    except Exception as e:
        logger.error(f"Failed to get document stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Profile management endpoints
# The server-side store is the source of truth. 
# The frontend IndexedDB copy is a cache that seeds and follows it.

class ProfileSyncRequest(BaseModel):
    """Request for syncing profile data."""
    user_id: str
    profile_data: Dict[str, Any]


@app.post("/api/v1/profile/sync")
async def sync_profile(
    request: ProfileSyncRequest,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """
    Merge a client-side (IndexedDB) profile into the server store.

    The server copy is authoritative: client entries only win when they
    carry strictly higher confidence (e.g. collected while the server
    had no data).
    """
    check_user_access(auth, request.user_id, user_token)
    store = get_profile_store()
    merged = await store.sync_client_profile(
        auth.tenant, request.user_id, request.profile_data
    )

    get_audit_logger().log(
        "profile_sync",
        tenant=auth.tenant,
        user_id=request.user_id,
        key=auth.key_fingerprint,
        sections=sorted(merged.keys()),
    )

    return {
        "status": "synced",
        "user_id": request.user_id,
        "profile": merged,
    }


@app.get("/api/v1/profile/{user_id}")
async def get_profile(
    user_id: str,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """Read the server-side profile (source of truth)."""
    check_user_access(auth, user_id, user_token)
    store = get_profile_store()
    profile = await store.get(auth.tenant, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"user_id": user_id, "profile": profile}


@app.delete("/api/v1/profile/{user_id}")
async def delete_profile(
    user_id: str,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """
    Erase a user profile (GDPR right-to-erasure).

    The deletion itself is audit-logged; the audit record contains no
    profile data.
    """
    check_user_access(auth, user_id, user_token)
    store = get_profile_store()
    existed = await store.delete(auth.tenant, user_id)

    get_audit_logger().log(
        "profile_delete",
        tenant=auth.tenant,
        user_id=user_id,
        key=auth.key_fingerprint,
        existed=existed,
    )

    return {"status": "deleted", "user_id": user_id, "existed": existed}


# Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)