"""
GenUI Backend API
FastAPI application exposing the multi-agent system for GenUI frontend.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, File, Form, Path, Query, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from api.deps import (
    allow_indexing_budget,
    budget_tenant,
    charge_llm_budget,
    get_corpus_size,
    get_llm_budget,
    get_profile_store,
    get_session_store,
)
from api.audit_router import router as audit_router
from api.content_policy_router import router as content_policy_router
from api.events_router import router as events_router
from api.theme_router import router as theme_router
from api.zone_config_router import router as zone_config_router
from api.zone_router import router as zone_router
from pydantic import BaseModel, Field

from auth import AuthContext
from auth.dependencies import (
    USER_TOKEN_HEADER,
    check_user_access,
    get_audit_logger,
    get_audit_reader,
    require_admin,
    require_client,
)
from auth.identity import AuthError
from llm import credentials
from llm.embeddings import EmbeddingConfigError
from llm.factory import Role, create_llm_client, llm_config_problems, llm_configured
from config import settings
from agents import get_orchestrator, OrchestratorResult
from metrics.ops import get_ops_metrics
from auth.keys import fingerprint
from profiles import is_identified, new_session_id
from profiles.sessions import SESSION_ID_PATTERN
from rag import create_chunker, get_vector_store
from rag.chunker import cutting_embeddings
from rag import extractors, ingest_status
from rag.chunker import SemanticChunk
from rag.vector_store import assign_point_ids
from rag.contextualizer import (
    contextual_indexing_enabled,
    contextualize,
    estimate_tokens,
    prompt_cache_mode,
)
from schemas.components import GENUI_CONTRACT_VERSION
from utils.redis_conn import RETRY_AFTER_SECONDS, StoreUnavailable, shared_redis
from utils.request_context import (
    REQUEST_ID_HEADER,
    begin_request,
    configure_logging,
    request_id,
    server_error,
)
from utils.tracing import span
from qdrant_client.http.exceptions import ResponseHandlingException

configure_logging(
    settings.log_format or ("text" if settings.genui_dev_open else "json"),
    logging.DEBUG if settings.debug else logging.INFO,
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
    session_id: Optional[str] = Field(
        default=None,
        pattern=SESSION_ID_PATTERN,
        description="Conversation to continue, as returned by a previous answer. "
                    "The server keeps its recent messages and a summary of the "
                    "older ones; absent, unknown or not readable by this caller, "
                    "a new session starts"
    )
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="For clients that do not send session_id: recent messages, "
                    "cut to CHAT_WINDOW_MESSAGES. Ignored when session_id is sent"
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
    disclosure: Optional[Dict[str, Any]] = Field(
        default=None,
        description="AI content marking of this answer: ai_generated, "
                    "provenance, generated_at, system. Absent when the "
                    "operator set GENUI_DISCLOSURE_OFF"
    )
    session: Optional[Dict[str, Any]] = Field(
        default=None,
        description="What the conversation memory did: resumed (the answer "
                    "saw this session's earlier messages), stored (this "
                    "exchange is remembered; false when the session store "
                    "did not answer), unsummarized (messages that left the "
                    "window without entering the summary, for lack of budget "
                    "or a failed summary call)"
    )
    retrieval: Optional[str] = Field(
        default=None,
        description="ok, or unavailable: the knowledge base did not answer "
                    "and this answer was written without documents"
    )


class QueryResponse(BaseModel):
    """Response from the query endpoint."""
    contract_version: int = Field(
        default=GENUI_CONTRACT_VERSION,
        description="Component contract version of the responding backend; "
                    "older frontend bundles use it to detect newer contracts "
                    "and silently skip unknown component types."
    )
    session_id: str = Field(..., description="Session to send with the next message of this conversation")
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
    dry_run: bool = Field(
        default=False,
        description="Report what indexing this document would cost (chunks, model calls, how the engine reuses the document) without indexing it or spending anything"
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
    # "configured" | "unconfigured" | "rejected"
    llm: str = "unconfigured"
    llm_unconfigured: List[str] = Field(default_factory=list)
    # "configured" | "rejected": a rejected embedding key costs retrieval, not the process, so it degrades without failing /ready
    embeddings: str = "configured"


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting GenUI Backend...")

    # Tracing (no-op unless TRACING_ENABLED=true)
    from utils.tracing import setup_tracing
    setup_tracing(app)

    # Transparency posture, stated at boot: the compliant default is
    # silent, turning it off is not. An operator who inherits a
    # deployment must be able to read this off the logs.
    if settings.genui_disclosure_off:
        logger.warning(
            "GENUI_DISCLOSURE_OFF=1: AI content disclosure is DISABLED. "
            "Served payloads carry no marking of generated content and the "
            "library renders no notice. By setting this you are declaring "
            "that the transparency information for AI-generated content is "
            "provided elsewhere in your product."
        )

    # The reason names provider and key: log only, /ready is unauthenticated
    for where, why in llm_config_problems():
        logger.error(f"LLM role not callable: {where}: {why}")

    # Initialize orchestrator (warms up connections)
    try:
        get_orchestrator()
        logger.info("Orchestrator initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}", exc_info=True)

    try:
        await asyncio.wait_for(credentials.check(), timeout=15)
    except Exception:
        logger.warning("LLM key check did not finish at startup; it runs again in the background", exc_info=True)
    key_watch = asyncio.create_task(credentials.watch())

    yield

    key_watch.cancel()
    logger.info("Shutting down GenUI Backend...")


# Create FastAPI app
app = FastAPI(
    title="GenUI Backend API",
    description="Multi-agent backend for Generative User Interface system",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(zone_config_router)
app.include_router(zone_router)
app.include_router(events_router)
app.include_router(audit_router)
app.include_router(content_policy_router)
app.include_router(theme_router)


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


@app.exception_handler(StoreUnavailable)
async def store_unavailable_handler(
    request: Request, exc: StoreUnavailable
) -> JSONResponse:
    """
    State that cannot be regenerated (policy, registry, theme, profile) was unreadable and no known version could stand in: a retryable refusal, never an answer built on "nothing stored".
    """
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


# Observability: HTTP middleware + health/readiness/liveness + /metrics
@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next):
    """
    Request id, the single handler for unhandled exceptions, and request count and latency per route template.

    The route label is bounded: an unmatched path is labeled "unmatched", never echoed, so random 404 probing cannot explode metric cardinality.
    """
    request_id = begin_request(request.headers.get(REQUEST_ID_HEADER))
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
        response = JSONResponse(
            status_code=500, content=server_error(f"{request.method} {path}")
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    response.headers[REQUEST_ID_HEADER] = request_id
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


# Added last, so it wraps the middleware above: a 500 built there still carries the CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Not CORS-safelisted headers: a page on another origin cannot read them unless listed
    expose_headers=["Retry-After", REQUEST_ID_HEADER],
)


def _qdrant_reachable() -> bool:
    """
    Ask Qdrant, now. The connection is reused across probes but the
    answer never is: a live round-trip is the only thing that can tell a
    healthy dependency from a dead one.
    """
    try:
        return bool(get_vector_store().get_collection_stats())
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        return False


async def _dependency_health() -> HealthResponse:
    """One truthful snapshot of the real dependencies (Qdrant, Redis, LLM)."""
    # The Qdrant client is synchronous: on the event loop it would let a
    # slow dependency stall every request this worker is serving, through
    # the very probes that exist to notice it. A probe must be able to
    # report "sick" without making the process sick.
    qdrant_connected = await asyncio.to_thread(_qdrant_reachable)

    # Probe the same handle the stores use.
    redis_status = await shared_redis(settings.redis_url).probe()
    redis_ok = redis_status == "connected" or (
        redis_status == "disabled" and settings.genui_dev_open
    )

    llm_problems = [where for where, _ in llm_config_problems()]
    checked = [where for where, _ in credentials.problems()]
    rejected = [where for where in checked if not where.startswith("embeddings ")]
    embeddings_ok = len(rejected) == len(checked)
    llm_ok = not llm_problems and not rejected

    return HealthResponse(
        status="healthy" if (qdrant_connected and redis_ok and llm_ok and embeddings_ok) else "degraded",
        version="1.0.0",
        qdrant_connected=qdrant_connected,
        redis=redis_status,
        llm="unconfigured" if llm_problems else "rejected" if rejected else "configured",
        llm_unconfigured=llm_problems + rejected,
        embeddings="configured" if embeddings_ok else "rejected",
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


@app.get("/api/v1/whoami")
async def whoami(auth: AuthContext = Depends(require_admin)):
    """
    The tenant an admin key resolves to (the console shows it, so an
    operator sees which tenant they are editing). The tenant always comes
    from the key, never from the request; a key configured without a
    ':tenant' suffix maps to 'default'.
    """
    return {"tenant": auth.tenant, "is_admin": auth.is_admin}


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
    # No usable identity means no data subject: the answer is generated,
    # nothing per-user is read, and nothing per-user is written.
    if not is_identified(request.user_id):
        request.user_id = None

    check_user_access(auth, request.user_id, user_token)

    orchestrator = get_orchestrator()

    await charge_llm_budget(
        budget_tenant(auth),
        cost=orchestrator.planned_generations(request.behavior_data),
    )

    sessions = get_session_store()
    session_id, session, reachable = await _open_session(
        sessions, auth.tenant, request.session_id, request.user_id
    )

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

    summary = None
    history = None
    if session is not None:
        history = session["messages"]
        summary = session.get("summary") or None
    elif request.session_id is None and request.conversation_history:
        history = [
            {"role": m.role, "content": m.content}
            for m in request.conversation_history[-settings.chat_window_messages:]
        ]

    # The span ties the genui.llm.* client spans to this query
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
                conversation_summary=summary,
            )
    except Exception:
        ops.observe_generation(auth.tenant, "query", outcome="error")
        raise
    ops.observe_generation(
        auth.tenant, "query", time.perf_counter() - started,
        outcome="degraded" if getattr(result, "degraded", False) else "ok",
    )

    frontend_response = result.to_frontend_response()

    profile_updates = frontend_response.get("profile_updates", {})
    if request.user_id and profile_updates.get("updates"):
        try:
            await profile_store.apply_updates(
                auth.tenant, request.user_id, profile_updates["updates"]
            )
        except Exception as e:
            logger.warning(f"Profile update persistence failed: {e}")

    session_meta = {"resumed": session is not None, "stored": False, "unsummarized": 0}
    if reachable:
        try:
            session_meta["unsummarized"] = await _remember_exchange(
                sessions, auth, session_id, session, request.user_id,
                request.query, frontend_response["text"],
            )
            session_meta["stored"] = True
        except StoreUnavailable as e:
            logger.warning(f"Chat session not saved: {e}")

    # The question is free text a visitor may fill with anything, special categories included: the line records what was answered, never what was asked.
    get_audit_logger().log(
        "query",
        tenant=auth.tenant,
        user_id=request.user_id,
        key=auth.key_fingerprint,
        confidence=frontend_response["meta"].get("confidence"),
        component_count=len(frontend_response["components"]),
        profile_updates_applied=len(profile_updates.get("updates", [])),
        session=fingerprint(session_id),
        context_messages=len(history or []),
        summary_used=summary is not None,
    )
    
    meta_data = frontend_response["meta"]
    behavior_meta = None
    if "behavior" in meta_data and meta_data["behavior"]:
        behavior_meta = BehaviorMeta(**meta_data["behavior"])
    
    raw_profile_updates = frontend_response.get("profile_updates", {})
    profile_updates = ProfileUpdateInstruction(
        should_update=bool(raw_profile_updates.get("should_update", False)),
        updates=raw_profile_updates.get("updates", [])
    )
    
    return QueryResponse(
        session_id=session_id,
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
            disclosure=meta_data.get("disclosure"),
            session=session_meta,
            retrieval=meta_data.get("retrieval"),
        ),
    )


async def _open_session(store, tenant: str, requested: Optional[str], user_id: Optional[str]):
    """
    (session_id, record, reachable) for this request.

    A stored session is used only when it exists in this tenant and belongs to the same verified user, None for an anonymous one.
    Anything else (another tenant, another user, expired, an anonymous session presented after login) is a session this caller cannot read: a new id is minted, never the one the client sent.
    With the store unreachable the requested id is kept, so the conversation resumes when the store is back.
    """
    try:
        record = await store.get(tenant, requested) if requested else None
    except StoreUnavailable as e:
        logger.warning(f"Chat session store unreachable, answering without memory: {e}")
        return requested or new_session_id(), None, False
    if record is not None and record.get("user_id") == user_id:
        return requested, record, True
    return new_session_id(), None, True


_SUMMARY_SYSTEM = (
    "You keep the running summary of a conversation between a user and an assistant. "
    "Rewrite the summary so that it also covers the new messages: what the user said about themselves, "
    "what they asked, what was answered, what is still open. "
    "At most 120 words, third person, no greetings. "
    'Respond with JSON: {"summary": "..."}'
)
_SUMMARY_MAX_CHARS = 2000


async def _remember_exchange(store, auth: AuthContext, session_id: str, record, user_id, question: str, answer: str) -> int:
    """
    Append the exchange to the session, keep the last CHAT_WINDOW_MESSAGES and fold the older ones into the summary.
    The fold is one generation, charged to the tenant budget before it is spent.
    Without budget, or when the call fails, the window slides anyway and the summary stays as it was: the dropped messages are counted instead.
    Two messages in flight on one session keep only the exchange saved last; a chat sends one at a time.
    Returns the messages left out of the summary so far.
    """
    now = datetime.now(timezone.utc).isoformat()
    record = dict(record or {"user_id": user_id, "summary": "", "unsummarized": 0, "created_at": now})
    messages = record.get("messages", []) + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    window = settings.chat_window_messages
    overflow, record["messages"] = messages[:-window], messages[-window:]

    if overflow:
        tenant = budget_tenant(auth)
        folded = None
        if tenant is None or await get_llm_budget().allow(tenant, cost=1):
            folded = await _fold_summary(record.get("summary", ""), overflow, auth.tenant)
        if folded:
            record["summary"] = folded
        else:
            record["unsummarized"] = record.get("unsummarized", 0) + len(overflow)

    record["updated_at"] = now
    await store.save(auth.tenant, session_id, record)
    return record.get("unsummarized", 0)


async def _fold_summary(summary: str, messages: List[Dict[str, str]], tenant: str) -> Optional[str]:
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    ops = get_ops_metrics()
    started = time.perf_counter()
    try:
        raw = await create_llm_client(Role.SUMMARY).complete_json(
            _SUMMARY_SYSTEM,
            f"<summary>\n{summary}\n</summary>\n\n<new_messages>\n{transcript}\n</new_messages>",
        )
        folded = str(json.loads(raw).get("summary", "")).strip()
    except Exception as e:
        ops.observe_generation(tenant, "chat_summary", outcome="error")
        logger.warning(f"Chat summary failed, the window slides without it: {e}")
        return None
    ops.observe_generation(tenant, "chat_summary", time.perf_counter() - started)
    return folded[:_SUMMARY_MAX_CHARS] or None


@app.delete("/api/v1/query/sessions/{session_id}")
async def delete_chat_session(
    session_id: str = Path(..., pattern=SESSION_ID_PATTERN),
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """
    Forget a conversation: its recent messages and its summary.

    A session with a user is deleted only with that user's identity, as every per-user route; an anonymous one by whoever holds its id.
    With the store unreachable it is a 503 and nothing was deleted.
    """
    store = get_session_store()
    record = await store.get(auth.tenant, session_id)
    if record is None:
        return {"deleted": False}
    check_user_access(auth, record.get("user_id"), user_token)
    return {"deleted": await store.delete(auth.tenant, session_id)}


# Chunks enriched and written down together
_INGEST_BATCH = 50


def _chunk_document(
    text: str, metadata: Dict[str, Any], source_name: str, estimate: bool = False,
):
    """
    Blocking: the semantic splitter embeds while it decides where to cut.
    An estimate cuts at sentences and embeds nothing.
    """
    return create_chunker(use_semantic=False if estimate else None).chunk_text(
        text=text, metadata=metadata, source_name=source_name,
    )


async def _chunk_and_index(
    text: str,
    metadata: Dict[str, Any],
    source_name: str,
    tenant: str,
    dry_run: bool = False,
    ingest_id: str = "",
) -> Dict[str, Any]:
    """
    One ingest, in one place so every caller keeps the blocking parts off
    the event loop the same way.

    Chunking, embedding and the Qdrant upsert are blocking and go to a
    thread. Writing the context of each chunk is a batch of model calls
    and stays on the loop. `dry_run` runs everything up to the point
    where money is spent and reports what it would cost, without spending
    it: with semantic chunking on, the estimate cuts at sentences, so its
    chunk counts are approximate and it states what the real cut embeds.
    """
    metadata.setdefault("indexed_at", datetime.now(timezone.utc).isoformat())

    async def stopped(chunks_created: int) -> Dict[str, Any]:
        await ingest_status.finish(ingest_id, "cancelled")
        logger.info("Ingest of %s stopped before anything was indexed", source_name)
        return {
            "chunks_created": chunks_created, "chunks_indexed": 0,
            "cancelled": True, "status": "cancelled",
            "contextual_indexing": False, "context_calls": 0,
        }

    # Registered before the cutting starts
    if not dry_run and not await ingest_status.begin(ingest_id, 0, source_name, tenant):
        return await stopped(0)

    chunks = await asyncio.to_thread(
        _chunk_document, text, metadata, source_name, dry_run
    )
    store = await asyncio.to_thread(get_vector_store)
    assign_point_ids(tenant, chunks)

    corpus_tokens = await _corpus_tokens(store, tenant)
    with_context = contextual_indexing_enabled(tenant, corpus_tokens)

    stored = await asyncio.to_thread(store.indexed_state, source_name, tenant)

    def already_indexed(chunk) -> bool:
        """
        Whether this chunk is already in the index as it is now.

        A point id is derived from the text it holds, so finding one is the
        same as finding that text: a passage that was only moved is found
        and left alone, and a passage that was corrected is not found and
        is written again. A chunk that is unchanged but has no context is
        not done either, once context is being written.
        """
        payload = stored.get(chunk.point_id)
        if payload is None:
            return False
        return bool(payload.get("contextualized")) or not with_context

    pending = [chunk for chunk in chunks if not already_indexed(chunk)]
    unchanged = [chunk for chunk in chunks if already_indexed(chunk)]

    # What this upload adds, and whether it is the one that takes the corpus over the line: 
    # the operator is asked about the corpus left behind at that moment.
    # Text already stored is already counted, context written onto it or not.
    added_tokens = sum(
        estimate_tokens(chunk.content)
        for chunk in pending if chunk.point_id not in stored
    )
    threshold = settings.contextual_indexing_threshold_tokens
    crosses = bool(
        threshold > 0 and corpus_tokens < threshold <= corpus_tokens + added_tokens
    )

    report: Dict[str, Any] = {
        "chunks_created": len(chunks),
        "chunks_unchanged": len(chunks) - len(pending),
        "contextual_indexing": with_context or crosses,
        "context_calls": len(pending) if (with_context or crosses) else 0,
        "prompt_cache": prompt_cache_mode() if (with_context or crosses) else None,
        "corpus_tokens": corpus_tokens,
        "corpus_tokens_after": corpus_tokens + added_tokens,
        "threshold_tokens": threshold,
        "crosses_threshold": crosses,
    }

    if dry_run:
        if crosses:
            counts = await asyncio.to_thread(store.chunk_counts, tenant)
            report["chunks_left_behind"] = counts["chunks_plain"]
        semantic = settings.use_semantic_chunking
        return {
            **report,
            "status": "estimated",
            "chunks_indexed": 0,
            "chunking": "semantic" if semantic else "sentence",
            "chunks_approximate": semantic,
            "cutting_embeddings": await asyncio.to_thread(cutting_embeddings, text),
        }
    
    with_context = with_context or crosses

    if not await ingest_status.begin(
        ingest_id, len(pending) if with_context else 0, source_name, tenant
    ):
        return await stopped(len(chunks))

    async def still_wanted() -> bool:
        """
        Whether the run is still wanted, asked between chunks and from
        several coroutines at once, so it reads and never writes.
        """
        return not await ingest_status.cancelled(ingest_id)

    indexed = 0
    situated = 0
    failure: Optional[str] = None
    for start in range(0, len(pending), _INGEST_BATCH):
        batch = pending[start:start + _INGEST_BATCH]
        
        if with_context and not await allow_indexing_budget(tenant, len(batch)):
            with_context = False
            report["budget_exceeded"] = True
            logger.warning(
                "LLM budget exhausted for tenant %s: the rest of %s is indexed "
                "without context", tenant, source_name,
            )

        if with_context:
            situated += await contextualize(text, batch, should_continue=still_wanted)

        try:
            indexed += await asyncio.to_thread(store.index_chunks, batch, tenant)
        except Exception:
            failure = _with_request_id(f"indexing failed after {indexed} of {len(pending)} chunks")
            logger.error("Ingest of %s: %s", source_name, failure, exc_info=True)
            break
        entered = sum(
            estimate_tokens(chunk.content)
            for chunk in batch if chunk.point_id not in stored
        )
        if entered:
            await get_corpus_size().add(tenant, entered)

        if not await ingest_status.advance(ingest_id, indexed):
            report["cancelled"] = True
            logger.info(
                "Ingest of %s stopped on request after %d chunks", source_name, indexed
            )
            break

    report["contextual_indexing"] = situated > 0
    report["context_calls"] = situated

    report["chunks_payload_updated"] = 0
    if unchanged and failure is None and not report.get("cancelled"):
        try:
            report["chunks_payload_updated"] = await asyncio.to_thread(
                store.refresh_payloads, unchanged, stored, tenant
            )
        except Exception:
            failure = _with_request_id("metadata update failed")
            logger.error("Ingest of %s: %s", source_name, failure, exc_info=True)

    # The old version goes only once every chunk of the new one is stored:
    # until then it is what answers for the chunks that did not make it.
    if failure is not None:
        report["chunks_pruned"] = 0
        report["chunks_failed"] = len(pending) - indexed
        report["previous_version_served"] = True
        report["error"] = failure
    elif chunks and not report.get("cancelled"):
        try:
            report["chunks_pruned"], removed_tokens = await asyncio.to_thread(
                store.prune_removed_chunks,
                source_name, [chunk.point_id for chunk in chunks], tenant,
            )
        except Exception:
            failure = _with_request_id("removing the previous version failed")
            logger.error("Ingest of %s: %s", source_name, failure, exc_info=True)
            report["chunks_pruned"] = 0
            report["previous_version_served"] = True
            report["error"] = failure
        else:
            if removed_tokens:
                await get_corpus_size().add(tenant, -removed_tokens)

    status = (
        "partial" if failure is not None
        else "cancelled" if report.get("cancelled")
        else "completed"
    )
    report["chunks_contextualized"] = situated
    await ingest_status.finish(ingest_id, "done" if status == "completed" else status)

    if crosses:
        counts = await asyncio.to_thread(store.chunk_counts, tenant)
        report["chunks_left_behind"] = counts["chunks_plain"]

    return {**report, "status": status, "chunks_indexed": indexed}


def _with_request_id(text: str) -> str:
    rid = request_id()
    return f"{text} (request id {rid})" if rid else text


async def _corpus_tokens(store, tenant: str) -> int:
    """
    This tenant's corpus size, from the running total kept while indexing.

    Absent means nothing has been counted yet, which is every deployment
    that indexed before the total existed and any whose Redis was cleared.
    Those rebuild it once, from the collection, and the total carries on
    from there. Zero would have been the silent answer: a corpus that never
    reaches the threshold and a feature that never turns on.
    """
    counter = get_corpus_size()
    total = await counter.get(tenant)
    if total is None:
        total = await asyncio.to_thread(store.recount_tokens, tenant)
        await counter.set(tenant, total)
    return total


# Document routes talk to Qdrant with the synchronous client, so the
# ones that have nothing to await are declared `def`: the framework runs
# them in its threadpool and the loop stays free. Lower frequency than a
# probe, identical effect on the worker serving renders next to them.
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
    source_name = request.metadata.get("title", "uploaded_document")

    if request.dry_run:
        return await _chunk_and_index(
            request.content, request.metadata, source_name, auth.tenant,
            dry_run=True,
        )

    content_length = len(request.content)

    if content_length < 10000:
        report = await _chunk_and_index(
            request.content, request.metadata, source_name, auth.tenant
        )

        get_audit_logger().log(
            "document_upload",
            tenant=auth.tenant,
            key=auth.key_fingerprint,
            source=source_name,
            chunks_indexed=report["chunks_indexed"],
            contextualized=report.get("chunks_contextualized", 0),
        )

        return report
    else:
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


@app.post("/api/v1/documents/upload")
async def upload_document_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    dry_run: bool = Form(False),
    ingest_id: str = Form(""),
    auth: AuthContext = Depends(require_admin),
):
    """
    Upload a document as a file (PDF, DOCX, HTML, TXT, MD).

    Text is extracted server-side off the event loop, chunked, and indexed in
    the tenant's knowledge base. The optional `url` becomes part of the
    URL whitelist when the AI cites this document.
    """
    content = await _read_capped(file, extractors.max_file_size_bytes())
    source_name = title or file.filename or "uploaded_file"
    extractor = extractors.configured_backend()

    try:
        text = await asyncio.to_thread(
            extractors.extract_text, file.filename or "", content
        )
    except extractors.ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))

    metadata: Dict[str, Any] = {"title": source_name}
    if url:
        metadata["url"] = url
    if file.filename:
        metadata["file_type"] = file.filename.rsplit(".", 1)[-1].lower()

    report = await _chunk_and_index(
        text, metadata, source_name, auth.tenant,
        dry_run=dry_run, ingest_id=ingest_id,
    )

    if dry_run:
        return {**report, "source": source_name, "extractor": extractor,
                "extracted_chars": len(text)}

    get_audit_logger().log(
        "document_upload",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        source=source_name,
        file_name=file.filename,
        extractor=extractor,
        extracted_chars=len(text),
        chunks_indexed=report["chunks_indexed"],
        contextualized=report.get("chunks_contextualized", 0),
    )

    return {
        **report,
        "source": source_name,
        "extractor": extractor,
        "extracted_chars": len(text),
    }


_READ_BLOCK = 1024 * 1024


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """
    The upload's bytes, read a block at a time and refused as soon as they
    pass `limit`, so an oversized file is never held whole in memory. The
    framework has already spooled the part to a temporary file, on disk
    past its first megabyte.
    """
    content = bytearray()
    while block := await file.read(_READ_BLOCK):
        content += block
        if len(content) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: the limit is {limit // (1024 * 1024)} MB "
                       f"(MAX_UPLOAD_MB)",
            )
    return bytes(content)


async def _process_document_background(
    content: str,
    metadata: Dict[str, Any],
    tenant: str,
):
    """Background task for processing large documents."""
    try:
        report = await _chunk_and_index(
            content,
            metadata,
            metadata.get("title", "uploaded_document"),
            tenant,
        )
        logger.info(
            "Background document processing %s: %d chunks, %d with context%s",
            report["status"], report["chunks_indexed"],
            report.get("chunks_contextualized", 0),
            f", {report['error']}" if report.get("error") else "",
        )

    except Exception as e:
        logger.error(f"Background document processing failed: {e}", exc_info=True)


@app.get("/api/v1/documents/ingest/{ingest_id}")
async def read_ingest(ingest_id: str, auth: AuthContext = Depends(require_admin)):
    """
    How far a running ingest has got.

    A large document is thousands of model calls behind one request that
    answers only at the end. Without this the operator cannot tell a long
    job from a stuck one, which is the whole difference between waiting and
    pulling the plug.
    """
    status = await ingest_status.read(ingest_id, auth.tenant)
    if not status:
        return {"phase": "unknown", "done": 0, "total": 0}
    return status


@app.post("/api/v1/documents/ingest/{ingest_id}/cancel")
async def cancel_ingest(ingest_id: str, auth: AuthContext = Depends(require_admin)):
    """
    Ask a running ingest to stop.

    Closing the browser does not do this: the server is never told, and
    goes on spending to the end of the document. The run reads this flag
    between batches, so it stops with every completed batch written down
    and nothing half-indexed.
    """
    found = await ingest_status.cancel(ingest_id, auth.tenant)
    return {"cancelled": found, "ingest_id": ingest_id}


@app.exception_handler(ResponseHandlingException)
async def qdrant_unreachable_handler(request: Request, exc: ResponseHandlingException):
    logger.warning("Qdrant did not answer", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": f"The knowledge base did not answer: nothing was read or changed. Retry in {RETRY_AFTER_SECONDS}s.",
            "request_id": request_id(),
        },
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


@app.get("/api/v1/documents")
async def list_documents(auth: AuthContext = Depends(require_admin)):
    """
    List the documents in the tenant's knowledge base, with chunk counts
    and the state of the corpus they form.
    """
    store = await asyncio.to_thread(get_vector_store)
    documents = await asyncio.to_thread(store.list_documents, auth.tenant)
    counts = await asyncio.to_thread(store.chunk_counts, auth.tenant)
    corpus_tokens = await _corpus_tokens(store, auth.tenant)

    return {
        "tenant": auth.tenant,
        "documents": documents,
        "count": len(documents),
        "corpus": {
            **counts,
            "tokens": corpus_tokens,
            "threshold_tokens": settings.contextual_indexing_threshold_tokens,
            "contextual_indexing": contextual_indexing_enabled(
                auth.tenant, corpus_tokens
            ),
            "budget_per_hour": settings.llm_budget_per_hour or None,
            "max_upload_bytes": extractors.max_file_size_bytes(),
        },
    }


class BackfillRequest(BaseModel):
    """Bring the chunks indexed before the threshold up to the rest."""
    dry_run: bool = Field(
        default=False,
        description="Report what the backfill would cost without spending it"
    )
    ingest_id: str = Field(
        default="",
        description="Names this run so it can be stopped through the same "
                    "endpoint an upload uses. Without one it cannot be stopped"
    )
    max_chunks: int = Field(
        default=500, ge=1, le=5000,
        description="Chunks to work through in this run. A large corpus is "
                    "several runs: each one picks up where the last stopped"
    )


@app.post("/api/v1/documents/backfill")
async def backfill_context(
    request: BackfillRequest,
    auth: AuthContext = Depends(require_admin),
):
    """
    Index the chunks that were stored without their context behind it now.

    Never automatic: going over a whole knowledge base with the model is a
    different order of spend from an upload, and a bill nobody chose is
    the thing this project does not do. It says what it will cost, it goes
    through the same per-tenant cap as everything else, it skips what is
    already done, and it updates points in place so an interrupted run
    resumed later neither duplicates nor skips.
    """
    store = await asyncio.to_thread(get_vector_store)
    plain = await asyncio.to_thread(
        store.plain_points, auth.tenant, request.max_chunks
    )
    counts = await asyncio.to_thread(store.chunk_counts, auth.tenant)

    report: Dict[str, Any] = {
        "tenant": auth.tenant,
        "chunks_plain": counts["chunks_plain"],
        "chunks_in_this_run": len(plain),
        "context_calls": len(plain),
        "prompt_cache": prompt_cache_mode(),
    }

    if request.dry_run:
        return {**report, "status": "estimated", "chunks_contextualized": 0}

    if not plain:
        return {**report, "status": "completed", "chunks_contextualized": 0}

    if not await ingest_status.begin(
        request.ingest_id, len(plain), "backfill", auth.tenant
    ):
        return {**report, "status": "cancelled", "chunks_contextualized": 0,
                "chunks_plain_remaining": counts["chunks_plain"]}
    try:
        done, stopped_on_budget = await _backfill_documents(
            store, plain, auth.tenant, request.ingest_id
        )
    except Exception:
        await ingest_status.finish(request.ingest_id, "failed")
        raise
    stopped = await ingest_status.cancelled(request.ingest_id)
    await ingest_status.finish(
        request.ingest_id, "cancelled" if stopped else "done"
    )
    after = await asyncio.to_thread(store.chunk_counts, auth.tenant)

    if not done and stopped_on_budget:
        raise HTTPException(
            status_code=429,
            detail=f"The hourly cap (LLM_BUDGET_PER_HOUR="
                   f"{settings.llm_budget_per_hour}) has nothing left for "
                   f"this run. Nothing was indexed. Run it again when the "
                   f"window resets: it picks up where it stopped.",
        )

    get_audit_logger().log(
        "context_backfill",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        chunks_contextualized=done,
        chunks_plain=after["chunks_plain"],
    )

    return {
        **report,
        "status": (
            "completed" if after["chunks_plain"] == 0
            else "cancelled" if stopped
            else "partial"
        ),
        "chunks_contextualized": done,
        "chunks_plain_remaining": after["chunks_plain"],
        **({"budget_exceeded": True} if stopped_on_budget else {}),
    }


async def _backfill_documents(
    store,
    plain: List[Dict[str, Any]],
    tenant: str,
    ingest_id: str = "",
) -> tuple[int, bool]:
    """
    Situate and re-index the given points, one source document at a time.

    A chunk is placed inside its document, and the document is what its own
    chunks say: nothing keeps the original file after an ingest, and the
    chunks are a partition of it. Ordering them by the index in their id
    puts the document back in reading order.

    The cap is asked per batch, immediately before that batch is spent, so
    a run that cannot be afforded stops instead of charging for generations
    it will never make. Returns (chunks done, whether the cap stopped it).
    """
    async def still_wanted() -> bool:
        """Asked between chunks, from several coroutines: reads, never writes."""
        return not await ingest_status.cancelled(ingest_id)

    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for point in plain:
        by_source.setdefault(point["source_document"], []).append(point)

    done = 0
    for source, points in by_source.items():
        points.sort(key=lambda p: _chunk_index(p["chunk_id"]))
        document = "\n\n".join(point["content"] for point in points)

        for start in range(0, len(points), _INGEST_BATCH):
            window = points[start:start + _INGEST_BATCH]
            if not await ingest_status.advance(ingest_id, done):
                logger.info("Backfill stopped on request after %d chunks", done)
                return done, False
            if not await allow_indexing_budget(tenant, len(window)):
                logger.warning(
                    "LLM budget exhausted for tenant %s: backfill stops with "
                    "%d chunks done", tenant, done,
                )
                return done, True

            chunks = [
                SemanticChunk(
                    content=point["content"],
                    metadata={},
                    chunk_id=point["chunk_id"],
                    source_document=source,
                )
                for point in window
            ]
            await contextualize(document, chunks, should_continue=still_wanted)
            done += await asyncio.to_thread(
                store.recontextualize, chunks, [point["id"] for point in window]
            )

    return done, False


def _chunk_index(chunk_id: str) -> int:
    """The position a chunk id carries, or last when it carries none."""
    _, _, tail = str(chunk_id).rpartition("_")
    return int(tail) if tail.isdigit() else 1 << 30


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
    # Search itself is asynchronous end to end; only building the store (first use, or a retry after Qdrant was down) can block
    vector_store = await asyncio.to_thread(get_vector_store)
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
                "contextualized": bool(r.metadata.get("contextualized")),
            }
            for r in results
        ],
    }


@app.delete("/api/v1/documents/{source_name}")
async def delete_document(
    source_name: str,
    auth: AuthContext = Depends(require_admin),
):
    """
    Delete a document from the tenant's knowledge base by source name.
    """
    store = await asyncio.to_thread(get_vector_store)
    removed_tokens = await asyncio.to_thread(
        store.delete_by_source, source_name, auth.tenant
    )

    if removed_tokens:
        await get_corpus_size().add(auth.tenant, -removed_tokens)

    get_audit_logger().log(
        "document_delete",
        tenant=auth.tenant,
        key=auth.key_fingerprint,
        source=source_name,
    )
    return {"status": "deleted", "source": source_name}


@app.get("/api/v1/documents/stats")
def get_document_stats(auth: AuthContext = Depends(require_admin)):
    """
    Get statistics about the document knowledge base (tenant-aware).
    """
    stats = get_vector_store().get_collection_stats(tenant=auth.tenant)

    return {
        "status": "ok",
        "tenant": auth.tenant,
        "stats": stats,
    }


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
    # A render degrades to anonymous; this route cannot, because
    # storing the profile IS the request. Answering "synced" while
    # storing nothing, or storing everyone under one shared key, are
    # both worse than saying no.
    if not is_identified(request.user_id):
        raise HTTPException(
            status_code=400,
            detail="user_id must identify a person: profiles are not stored "
                   "for anonymous or placeholder identifiers",
        )
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


@app.get("/api/v1/profile/{user_id}/export")
async def export_user_data(
    user_id: str,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
    limit: int = Query(500, ge=1, le=2000, description="Audit entries per page"),
    offset: int = Query(0, ge=0),
):
    """
    Everything this deployment holds about one person (GDPR Art. 15).

    Three things, because there are only three: the stored profile, the chat sessions started while identified (recent messages and summary), and the audit entries that name this user (renders served, chat answers without the question, impressions and clicks, profile changes and erasures).
    The rest of the state is aggregate or tenant-level: cached renders belong to a segment, event counters to a zone, an experiment and an arm, themes and zone configs to the operator, and none of them is keyed by a person.
    Anonymous chat sessions name no one and are not here: they expire.

    Same identity guard as the other per-user routes: a badly guarded export route is a data breach wearing a compliance label.
    The audit side reuses the read path of the trail, so filtering and tenant scoping cannot drift from the one the audit viewer uses; when the trail lives in the host's log pipeline it says so (queryable=false) rather than reporting an empty history.
    """
    check_user_access(auth, user_id, user_token)

    store = get_profile_store()
    profile = await store.get(auth.tenant, user_id)
    # ref is the fingerprint the audit trail records for each query of the session; the id itself is a credential and stays out
    chat_sessions = [
        {"ref": fingerprint(session_id), **record}
        for session_id, record in await get_session_store().sessions_of(auth.tenant, user_id)
    ]

    reader = get_audit_reader()
    # Blocking file reads: off the event loop, like the audit viewer route
    audit = await asyncio.to_thread(
        reader.query, auth.tenant, user_id=user_id, limit=limit, offset=offset
    )

    get_audit_logger().log(
        "profile_export",
        tenant=auth.tenant,
        user_id=user_id,
        key=auth.key_fingerprint,
        profile_found=profile is not None,
        chat_sessions=len(chat_sessions),
        audit_entries=len(audit["entries"]),
    )

    return {
        "user_id": user_id,
        "tenant": auth.tenant,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "chat_sessions": chat_sessions,
        "audit": {
            "source": reader.source,
            "queryable": reader.queryable,
            "note": reader.note,
            **audit,
        },
    }


@app.delete("/api/v1/profile/{user_id}")
async def delete_profile(
    user_id: str,
    auth: AuthContext = Depends(require_client),
    user_token: Optional[str] = Security(USER_TOKEN_HEADER),
):
    """
    Erase a user profile (GDPR right-to-erasure).

    What goes: the profile and the chat sessions started while identified, which are the whole of the personalization and conversation data held about this person.
    Nothing else is keyed by a user.

    What stays: the audit trail.
    It is append-only by design, because a record of what was shown to whom is worth nothing if the party who showed it can rewrite it afterwards, and in a regulated deployment it is also the operator's evidence of their own compliance.
    Rewriting it on request would destroy the accountability it exists for, and in the production setup it is not even ours to rewrite: the lines have already left for the host's log pipeline.
    So it is bounded instead of edited, by rotation on the file sink and by the pipeline's retention policy otherwise, and the erasure itself is recorded in it, so a later export shows when the right was exercised.

    The response says which of the two happened, rather than reporting a clean "deleted" that would overstate it.
    It answers only after the stores confirmed the delete: with a store unreachable it is a 503 saying the data was NOT erased, and the attempt is on the trail.
    """
    check_user_access(auth, user_id, user_token)
    store = get_profile_store()
    try:
        sessions_erased = await get_session_store().delete_user(auth.tenant, user_id)
        existed = await store.delete(auth.tenant, user_id)
    except StoreUnavailable as e:
        get_audit_logger().log(
            "profile_delete",
            tenant=auth.tenant,
            user_id=user_id,
            key=auth.key_fingerprint,
            outcome="store_unavailable",
        )
        raise HTTPException(
            status_code=503,
            detail=f"The profile and its chat sessions were NOT erased. {e}",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )

    get_audit_logger().log(
        "profile_delete",
        tenant=auth.tenant,
        user_id=user_id,
        key=auth.key_fingerprint,
        outcome="erased",
        existed=existed,
        chat_sessions_erased=sessions_erased,
    )

    return {
        "status": "deleted",
        "user_id": user_id,
        "existed": existed,
        "profile_erased": True,
        "chat_sessions_erased": sessions_erased,
        "audit_retained": settings.audit_log_enabled,
        "note": (
            "The profile and chat sessions are erased. Audit entries naming this user are kept: "
            "the trail is append-only accountability evidence, bounded by the "
            "configured retention instead of edited."
            if settings.audit_log_enabled
            else "The profile and chat sessions are erased. Auditing is disabled on this deployment."
        ),
    }


# Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)