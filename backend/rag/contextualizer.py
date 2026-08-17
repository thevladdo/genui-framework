"""
Situating a chunk in its document before it is indexed.
Two rules decide the shape of everything here.

- THE GENERATED LINES ARE INDEXED AND NEVER RETURNED.
- IT IS BILLED, SO IT IS CAPPED AND IT IS COUNTED.
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable, List, Optional

from config import settings
from llm import create_llm_client

from .chunker import CHARS_PER_TOKEN, SemanticChunk

logger = logging.getLogger(__name__)

_CONCURRENCY = 4
_MAX_CONSECUTIVE_FAILURES = 5

_SYSTEM = (
    "You place an excerpt inside the document it was taken from, so that it "
    "can be found on its own.\n"
    "Write one or two short sentences naming what the excerpt is about: the "
    "subject it refers to, the period or the scope it holds for, and any term "
    "it uses that the document defines elsewhere.\n"
    "Use only what the document says. Never add a fact, a figure or a name "
    "that is not in it, and do not summarise the excerpt or comment on it.\n"
    'Answer as JSON: {"context": "<the sentences>"}'
)


def estimate_tokens(text: str) -> int:
    """Roughly how many tokens a piece of text is."""
    return len(text or "") // CHARS_PER_TOKEN


def contextual_indexing_enabled(tenant: str, corpus_tokens: int = 0) -> bool:
    """
    Whether this tenant indexes with context.

    Two ways in. Named explicitly, which is how it gets switched on for a
    tenant whose corpus is still small. Or by size: past the threshold the
    people who documented the technique put it at, it applies to new chunks
    without anyone turning it on, because below that size the cheaper answer
    is to put the documents in the prompt instead of working on retrieval.
    """
    enabled = {
        name.strip()
        for name in (settings.contextual_indexing_tenants or "").split(",")
        if name.strip()
    }
    if tenant and tenant in enabled:
        return True
    threshold = settings.contextual_indexing_threshold_tokens
    return threshold > 0 and corpus_tokens >= threshold


def prompt_cache_mode() -> str:
    """
    How the configured engine reuses the document across the calls about
    it. The declared cost of this technique assumes the document is paid
    for once per batch and not once per chunk, so an operator gets to see
    which of the two they are about to buy.
    """
    try:
        return create_llm_client(settings.context_model).prompt_cache
    except Exception as e:
        logger.warning("Could not resolve the prompt cache mode: %s", e)
        return "unknown"


def document_view(document: str, chunk: SemanticChunk) -> str:
    """
    As much of the document as may travel with one chunk.

    The technique assumes the document fits beside the excerpt. A large one
    does not, and sending it whole means every call is refused for exceeding
    the model's context while still spending the rate limit: a thousand
    chunks each carrying a million tokens, all of them failing. So a
    document over the budget travels as its opening, which is where the
    subject, the period and the definitions live, plus the neighbourhood of
    the chunk, which is where the local antecedents live.
    """
    budget = max(1_000, settings.context_document_max_chars)
    if len(document) <= budget:
        return document

    head = document[: budget // 2]
    start = chunk.start_char
    if start is None:
        start = document.find(chunk.content[:200])
    if start < 0:
        return head

    half = budget // 4
    window = document[max(0, start - half): start + half]
    return f"{head}\n[...]\n{window}"


async def contextualize(
    document: str,
    chunks: List[SemanticChunk],
    should_continue: Optional[Callable[[], Awaitable[bool]]] = None,
) -> int:
    """
    Fill in `chunk.context` for as many chunks as the engine answers for.

    A chunk whose call fails keeps `context` None and is indexed as it is:
    an unenriched chunk is worse than an enriched one and infinitely better
    than a missing one, so nothing here raises.

    `should_continue` is asked before each call, so a stop takes effect on
    the next chunk instead of after the whole batch. A document smaller
    than one batch is the common case, and without this the answer to a
    stop would be "when it has finished anyway".

    Returns how many chunks came back with context.
    """
    if not chunks:
        return 0

    client = create_llm_client(settings.context_model)
    gate = asyncio.Semaphore(_CONCURRENCY)
    state = {"consecutive_failures": 0, "abandoned": False}

    async def situate(chunk: SemanticChunk) -> None:
        async with gate:
            if state["abandoned"]:
                return
            if should_continue is not None and not await should_continue():
                state["abandoned"] = True
                logger.info("Context generation stopped on request")
                return
            try:
                raw = await client.complete_json_cached(
                    _SYSTEM,
                    f"<document>\n{document_view(document, chunk)}\n</document>",
                    f"<excerpt>\n{chunk.content}\n</excerpt>",
                )
                context = str(json.loads(raw).get("context", "")).strip()
            except Exception as e:
                state["consecutive_failures"] += 1
                if state["consecutive_failures"] >= _MAX_CONSECUTIVE_FAILURES:
                    state["abandoned"] = True
                    logger.error(
                        "Context generation abandoned after %d calls in a row "
                        "failed, the rest of this document is indexed as it is: %s",
                        state["consecutive_failures"], e,
                    )
                else:
                    logger.warning(
                        "Context generation failed for %s: %s", chunk.chunk_id, e
                    )
                return
            state["consecutive_failures"] = 0
            if context:
                chunk.context = context

    await asyncio.gather(*(situate(chunk) for chunk in chunks))

    written = sum(1 for chunk in chunks if chunk.context)
    logger.info("Context written for %d/%d chunks", written, len(chunks))
    return written
