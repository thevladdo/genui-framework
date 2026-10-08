"""
Qdrant Vector Store Module
Handles embedding storage, retrieval, and similarity search.
"""

import hashlib
import json
import logging
import re
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from functools import lru_cache
from collections import Counter
from zlib import crc32
import uuid
import asyncio

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http import models as qmodels

from auth.keys import DEFAULT_TENANT
from config import settings
from llm.embeddings import EmbeddingClient, EmbeddingConfigError, create_embedding_client
from .chunker import SemanticChunk
from .contextualizer import estimate_tokens

logger = logging.getLogger(__name__)

# Hard cap when scanning the collection for document listings
_LIST_SCROLL_PAGE = 256
_LIST_MAX_POINTS = 50_000
DENSE_VECTOR = ""
LEXICAL_VECTOR = "lexical"
_FUSION_CANDIDATES = 20
_TOKEN = re.compile(r"[a-z0-9]{2,}")

# Payload keys the server owns. Document metadata travels with a chunk and
# reaches the payload, so these are written last: a metadata field named
# "tenant" would otherwise label a point for a tenant the writer does not
# hold a key for, and the search filter, reading that label, would serve it.
RESERVED_PAYLOAD_FIELDS = frozenset({
    "content", "chunk_id", "source_document", "tenant", "contextualized",
})

# Payload keys that say nothing about the document: the time of the upload,
# and the node ids the splitter draws at random on every cut. Left in, every
# upload of an unchanged document would read as a change of metadata.
_UNCOMPARED_PAYLOAD_FIELDS = frozenset({
    "content", "contextualized", "indexed_at", "node_id", "relationships",
})


def content_hash(text: str) -> str:
    """
    Fingerprint of a chunk's source text.

    Taken over the chunk's own content and never over the situating lines,
    which are derived from it.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def point_id_for(
    tenant: Optional[str],
    source_document: str,
    digest: str,
    occurrence: int = 0,
) -> str:
    """
    The id of a chunk's point, derived from the text it holds rather than
    from where that text happens to sit.

    A random id made every upload an insert, so uploading a document twice
    stored it twice and a search then found the same passage under two
    points. Deriving it from the position fixed that but tied a chunk's
    identity to its index, so inserting a section near the top of a
    document renumbered everything below it: text that had not changed
    landed on a different id, and was embedded and situated again for
    nothing. Deriving it from the content instead means a passage that only
    moved is already stored, under the same id, and the upload has nothing
    to do with it.

    The occurrence separates chunks that repeat word for word inside one
    document, which boilerplate does. Without it the second copy would be
    written over the first and the document would quietly hold fewer
    points than it has chunks.
    """
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"genui:{tenant or DEFAULT_TENANT}:{source_document}:{digest}:{occurrence}",
    ))


def assign_point_ids(tenant: Optional[str], chunks: List[SemanticChunk]) -> None:
    """
    Work out where each of these chunks belongs, in place.

    Repeats have to be counted across the whole document: given one slice
    of it at a time, two identical chunks in different slices would both
    count as the first and collide.
    """
    seen: Dict[str, int] = {}
    for chunk in chunks:
        digest = content_hash(chunk.content)
        occurrence = seen.get(digest, 0)
        seen[digest] = occurrence + 1
        chunk.point_id = point_id_for(
            tenant, chunk.source_document, digest, occurrence
        )


def payload_for(chunk: SemanticChunk, tenant: Optional[str]) -> Dict[str, Any]:
    """What a chunk's point carries: its metadata, then the fields the server owns."""
    colliding = RESERVED_PAYLOAD_FIELDS.intersection(chunk.metadata)
    if colliding:
        logger.warning(
            "Metadata of %s names reserved payload fields %s: the "
            "server values are kept",
            chunk.chunk_id, sorted(colliding),
        )
    return {
        **chunk.metadata,
        "content": chunk.content,
        "chunk_id": chunk.chunk_id,
        "source_document": chunk.source_document,
        "tenant": tenant or DEFAULT_TENANT,
        "contextualized": bool(chunk.context),
    }


def payload_signature(payload: Dict[str, Any]) -> str:
    """
    The part of a payload that describes the document, as canonical JSON:
    key order and tuple-versus-list do not make two payloads differ.
    """
    return json.dumps(
        {k: v for k, v in payload.items() if k not in _UNCOMPARED_PAYLOAD_FIELDS},
        sort_keys=True, default=str,
    )


def indexable_text(chunk: SemanticChunk) -> str:
    """
    What the vectors are built from: the chunk, preceded by the lines that
    situate it when it has them.

    The payload keeps `chunk.content` untouched, so this text reaches the
    index and nothing else. That is the whole safety argument of the
    technique here: the corpus the URL whitelist and the numeric grounding
    judge from is built out of retrieved content, and generated lines never
    get into it.
    """
    return f"{chunk.context}\n\n{chunk.content}" if chunk.context else chunk.content


def lexical_vector(text: str) -> qmodels.SparseVector:
    """
    A chunk (or a query) as term frequencies, keyed by a stable hash of the
    term.

    Dense embeddings are good at paraphrase and blind to the exact token: a
    product code, an acronym, the name of a clause, a word that means one
    precise thing in the customer's domain. This is the other half of that.

    The corpus statistic that turns raw counts into a ranking (IDF) is
    computed by the engine over the collection itself. Nothing here keeps a
    term table in step with documents entering and leaving, which is the
    state that would drift out of sync in silence.
    """
    counts = Counter(crc32(token.encode()) for token in _TOKEN.findall(text.lower()))
    return qmodels.SparseVector(
        indices=list(counts.keys()),
        values=[float(count) for count in counts.values()],
    )


@dataclass
class RetrievalResult:
    """Result from a similarity search."""
    content: str
    score: float
    metadata: Dict[str, Any]
    chunk_id: str


class QdrantVectorStore:
    """
    Qdrant-based vector store for GenUI RAG system.
    Handles document indexing and semantic retrieval.
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        collection_name: str = None,
        embedder: Optional[EmbeddingClient] = None,
    ):
        """
        Initialize connection to Qdrant.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Name of the vector collection
            embedder: EmbeddingClient (created from config if not provided;
                raises EmbeddingConfigError when embedding is unconfigured)
        """
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection_name = collection_name or settings.qdrant_collection

        # Initialize Qdrant client (both sync and async). The timeout is what keeps a hung Qdrant from turning into a hung caller
        timeout = settings.qdrant_timeout_seconds
        self.client = QdrantClient(host=self.host, port=self.port, timeout=timeout)
        self.async_client = AsyncQdrantClient(
            host=self.host, port=self.port, timeout=timeout
        )

        # Embedding goes through the provider abstraction
        self.embed_model = embedder or create_embedding_client()

        # Vector size of the collection actually in Qdrant (set below).
        # Embeddings are checked against it so a model/collection mismatch
        # fails loudly instead of corrupting or silently skipping batches
        self._collection_dim: Optional[int] = None

        # Whether the collection carries the lexical vector (capability) and whether searches fuse the two rankings (behavior).
        self.has_lexical = False
        self.hybrid = False
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist; validate its dimension."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)

            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                # The vector size follows the configured embedding model
                self._collection_dim = self.embed_model.dimension
                try:
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=qmodels.VectorParams(
                            size=self._collection_dim,
                            distance=qmodels.Distance.COSINE,
                        ),
                        sparse_vectors_config={
                            LEXICAL_VECTOR: qmodels.SparseVectorParams(
                                modifier=qmodels.Modifier.IDF,
                            ),
                        },
                    )
                    self.has_lexical = True

                    # Create payload indices for filtering
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="source_document",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="file_type",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )

                    logger.info(f"Collection {self.collection_name} created successfully")
                except Exception as create_err:
                    # Multi-worker boot race
                    if (
                        getattr(create_err, "status_code", None) != 409
                        and "already exists" not in str(create_err)
                    ):
                        raise
                    logger.info(
                        f"Collection {self.collection_name} created by another worker"
                    )
                    exists = True

            if exists:
                logger.info(f"Collection {self.collection_name} already exists")
                self.has_lexical = self._declares_lexical()
                self._collection_dim = self._existing_vector_size()
                known = self.embed_model.dimension_if_known()
                if self._collection_dim and known and known != self._collection_dim:
                    raise EmbeddingConfigError(
                        f"Embedding model '{self.embed_model.model}' produces "
                        f"{known}-dimensional vectors but collection "
                        f"'{self.collection_name}' was created with dimension "
                        f"{self._collection_dim}. Re-index into a new collection "
                        f"(change QDRANT_COLLECTION) or switch back to a "
                        f"{self._collection_dim}-dimensional embedding model."
                    )

            # Tenant index: created unconditionally so existing collections gain it on upgrade
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tenant",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # already exists

            self.hybrid = self.has_lexical and settings.hybrid_retrieval
            logger.info(
                "Retrieval mode for %s: %s",
                self.collection_name,
                "hybrid (dense + lexical)" if self.hybrid else "dense only",
            )

        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise

    def _declares_lexical(self) -> bool:
        """
        Whether the collection carries the lexical vector.

        A collection created before that vector existed cannot gain it:
        Qdrant refuses to add a vector name to a live collection. Such a
        deployment keeps serving dense-only searches and moves to hybrid by
        indexing into a new collection (QDRANT_COLLECTION), never through a
        silent forced reindex hidden behind an upgrade.
        """
        try:
            params = self.client.get_collection(self.collection_name).config.params
            return LEXICAL_VECTOR in (getattr(params, "sparse_vectors", None) or {})
        except Exception as e:
            logger.warning(f"Could not read the sparse vector config: {e}")
            return False

    def _existing_vector_size(self) -> Optional[int]:
        """Vector size of the existing collection; None if undeterminable."""
        try:
            info = self.client.get_collection(self.collection_name)
            vectors = info.config.params.vectors
            return getattr(vectors, "size", None)  # named-vector configs: skip
        except Exception as e:
            logger.warning(f"Could not read collection vector size: {e}")
            return None

    def _check_dimension(self, vector: List[float]) -> None:
        """
        A produced vector must match the collection: a mismatch means the
        operator changed embedding model over an existing index — raise a
        readable error instead of letting Qdrant fail batch-by-batch.
        """
        if self._collection_dim and len(vector) != self._collection_dim:
            raise EmbeddingConfigError(
                f"Embedding model '{self.embed_model.model}' produced a "
                f"{len(vector)}-dimensional vector but collection "
                f"'{self.collection_name}' expects {self._collection_dim}. "
                f"Re-index into a new collection (change QDRANT_COLLECTION) "
                f"or switch back to a {self._collection_dim}-dimensional "
                f"embedding model."
            )

    def _tenant_condition(self, tenant: Optional[str]):
        """
        Filter condition scoping an operation to a tenant.

        Documents indexed before tenant isolation have no `tenant` field:
        they are treated as belonging to the default tenant, so existing
        single-tenant deployments keep working unchanged.
        """
        tenant = tenant or DEFAULT_TENANT
        if tenant == DEFAULT_TENANT:
            return qmodels.Filter(
                should=[
                    qmodels.FieldCondition(
                        key="tenant",
                        match=qmodels.MatchValue(value=tenant),
                    ),
                    qmodels.IsEmptyCondition(
                        is_empty=qmodels.PayloadField(key="tenant"),
                    ),
                ]
            )
        return qmodels.FieldCondition(
            key="tenant",
            match=qmodels.MatchValue(value=tenant),
        )
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        return self.embed_model.embed([text])[0]

    async def _generate_embedding_async(self, text: str) -> List[float]:
        """Generate embedding for a text string asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._generate_embedding, text)

    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return self.embed_model.embed(texts)
    
    def index_chunks(
        self,
        chunks: List[SemanticChunk],
        tenant: str = DEFAULT_TENANT,
        batch_size: int = 100,
    ) -> int:
        """
        Index semantic chunks into Qdrant, scoped to a tenant.

        Args:
            chunks: List of SemanticChunk objects to index
            tenant: Tenant owning these documents (isolation boundary)
            batch_size: Number of chunks to process at once

        Returns:
            Number of chunks indexed, which is all of them: a failed
            embedding or upsert raises, and the batches before it stay
            written. The caller decides what a partial write means: it
            may prune a document's old version only once the new one is
            stored in full.
        """
        if not chunks:
            logger.warning("No chunks provided for indexing")
            return 0

        if any(chunk.point_id is None for chunk in chunks):
            assign_point_ids(tenant, chunks)

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            # What gets indexed is the chunk with its context in front; what gets stored is the chunk.
            texts = [indexable_text(chunk) for chunk in batch]
            embeddings = self._generate_embeddings_batch(texts)
            if embeddings:
                self._check_dimension(embeddings[0])

            points = [
                qmodels.PointStruct(
                    id=chunk.point_id,
                    vector=(
                        {
                            DENSE_VECTOR: embedding,
                            LEXICAL_VECTOR: lexical_vector(text),
                        }
                        if self.has_lexical else embedding
                    ),
                    payload=payload_for(chunk, tenant),
                )
                for chunk, embedding, text in zip(batch, embeddings, texts)
            ]
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Indexed batch {i//batch_size + 1}: {len(points)} chunks")

        return len(chunks)

    def refresh_payloads(
        self,
        chunks: List[SemanticChunk],
        stored: Dict[str, Dict[str, Any]],
        tenant: str = DEFAULT_TENANT,
    ) -> int:
        """
        Rewrite the payload of stored chunks whose text is unchanged but
        whose metadata is not, without embedding anything.

        The point id is derived from the text, so a corrected URL or title
        on identical text lands on the same id and would otherwise be
        skipped: the old URL would stay the one the whitelist allows.
        The stored context flag is kept, since the vectors stay as they are.
        Returns how many payloads were rewritten; a failed write raises.
        """
        operations = []
        for chunk in chunks:
            current = stored.get(chunk.point_id)
            if current is None:
                continue
            payload = payload_for(chunk, tenant)
            if payload_signature(payload) == payload_signature(current):
                continue
            payload["contextualized"] = bool(current.get("contextualized"))
            operations.append(qmodels.OverwritePayloadOperation(
                overwrite_payload=qmodels.SetPayload(
                    payload=payload, points=[chunk.point_id],
                ),
            ))
        if operations:
            self.client.batch_update_points(
                collection_name=self.collection_name,
                update_operations=operations,
            )
        return len(operations)

    async def search_async(
        self,
        query: str,
        top_k: int = None,
        score_threshold: float = None,
        filters: Optional[Dict[str, Any]] = None,
        tenant: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """
        Perform semantic search asynchronously, scoped to a tenant.

        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Optional metadata filters
            tenant: Tenant scope (None = default tenant, which also
                matches legacy documents indexed without a tenant)

        Returns:
            List of RetrievalResult objects
        """
        top_k = top_k or settings.top_k_retrieval
        if score_threshold is None:
            score_threshold = settings.similarity_threshold

        query_embedding = await self._generate_embedding_async(query)
        self._check_dimension(query_embedding)

        # Build filter conditions: tenant isolation is always applied
        conditions = [self._tenant_condition(tenant)]
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    conditions.append(qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchAny(any=value),
                    ))
                else:
                    conditions.append(qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchValue(value=value),
                    ))
        qdrant_filter = qmodels.Filter(must=conditions)

        # A Qdrant failure raises: "no passage matched" and "the store did not answer" are different answers
        if self.hybrid:
            results = await self.async_client.query_points(
                collection_name=self.collection_name,
                prefetch=self._fusion_branches(
                    query, query_embedding, qdrant_filter, score_threshold, top_k
                ),
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=top_k,
            )
        else:
            results = await self.async_client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qdrant_filter,
            )
        points = results.points
        
        # Convert to RetrievalResult objects
        retrieval_results = []
        for hit in points:
            result = RetrievalResult(
                content=hit.payload.get("content", ""),
                score=hit.score,
                metadata={k: v for k, v in hit.payload.items() if k != "content"},
                chunk_id=hit.payload.get("chunk_id", ""),
            )
            retrieval_results.append(result)
        
        return retrieval_results
    
    def _fusion_branches(
        self,
        query: str,
        query_embedding: List[float],
        qdrant_filter: qmodels.Filter,
        score_threshold: Optional[float],
        top_k: int,
    ) -> List[qmodels.Prefetch]:
        """
        The two candidate lists the engine fuses, in the engine: fusing them
        here would mean carrying both full rankings back and reordering them
        in Python.

        Both branches carry the tenant filter. A lexical branch that forgot
        it would be a leak across tenants, not a relevance defect.

        The similarity threshold stays on the dense branch, where it means
        what it was configured to mean. The fused score is a rank score on a
        different scale entirely, and cutting that with a cosine number would
        empty every result set.
        """
        depth = max(_FUSION_CANDIDATES, top_k)
        branches = [
            qmodels.Prefetch(
                query=query_embedding,
                using=DENSE_VECTOR,
                limit=depth,
                filter=qdrant_filter,
                score_threshold=score_threshold,
            ),
        ]

        lexical = lexical_vector(query)
        if lexical.indices:
            branches.append(qmodels.Prefetch(
                query=lexical,
                using=LEXICAL_VECTOR,
                limit=depth,
                filter=qdrant_filter,
            ))
        return branches

    def delete_by_source(self, source_document: str, tenant: Optional[str] = None) -> int:
        """
        Delete all chunks from a specific source document, within a tenant.

        Returns the tokens removed, so the caller can take them off the
        corpus total. Without that the total only ever grows, and a corpus
        that has shrunk below the threshold goes on paying to index with
        context because a number nobody maintains says it is still large.
        """
        removed_tokens = self._source_tokens(source_document, tenant)
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_document",
                            match=qmodels.MatchValue(value=source_document),
                        ),
                        self._tenant_condition(tenant),
                    ]
                )
            ),
        )
        logger.info(f"Deleted chunks from source: {source_document} (tenant: {tenant or DEFAULT_TENANT})")
        return removed_tokens


    def _source_tokens(self, source_document: str, tenant: Optional[str]) -> int:
        """
        Tokens held by one document, read before it is deleted.

        One scroll over one document's payloads, on an operation that
        happens rarely and is already scanning to delete.
        """
        total = 0
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(
                        key="source_document",
                        match=qmodels.MatchValue(value=source_document),
                    ),
                    self._tenant_condition(tenant),
                ]),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=["content"],
                with_vectors=False,
            )
            total += sum(
                estimate_tokens((point.payload or {}).get("content", ""))
                for point in points
            )
            if offset is None:
                break

        return total

    def list_documents(self, tenant: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List the documents indexed for a tenant, with chunk counts.

        Scans the collection payloads (no vectors) and aggregates by
        source_document. Bounded scan: very large collections are
        truncated at _LIST_MAX_POINTS with a logged warning.
        """
        documents: Dict[str, Dict[str, Any]] = {}
        scanned = 0
        offset = None

        while scanned < _LIST_MAX_POINTS:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qmodels.Filter(must=[self._tenant_condition(tenant)]),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=["source_document", "title", "url", "file_type", "indexed_at"],
                with_vectors=False,
            )

            for point in points:
                payload = point.payload or {}
                source = payload.get("source_document", "unknown")
                entry = documents.setdefault(source, {
                    "source_document": source,
                    "chunks": 0,
                    "title": payload.get("title"),
                    "url": payload.get("url"),
                    "file_type": payload.get("file_type"),
                    "indexed_at": payload.get("indexed_at"),
                })
                entry["chunks"] += 1

            scanned += len(points)
            if offset is None:
                break

        if scanned >= _LIST_MAX_POINTS:
            logger.warning(
                "list_documents truncated at %d points for tenant %s",
                _LIST_MAX_POINTS, tenant or DEFAULT_TENANT,
            )


        return sorted(documents.values(), key=lambda d: d["source_document"])

    def prune_removed_chunks(
        self,
        source_document: str,
        point_ids: List[str],
        tenant: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Drop this document's points that the version just indexed no longer
        accounts for.

        Two of them. A document edited down to fewer chunks leaves a tail
        that nothing overwrites, and its text would go on grounding numbers
        and URLs that the document no longer contains. And a document whose
        points were stored under ids worked out some other way is not
        overwritten by the new write, which lands beside it instead of on
        top.

        Only safe when every chunk of the new version is stored: anything
        else removes the text still answering for the chunks that failed.
        Returns (points removed, tokens they held), so the caller can take
        the tokens off the corpus total. The points read are the points
        deleted, by id. A failed read or delete raises: the stale points are
        still served, and returning zero would report them as gone.
        """
        if not point_ids:
            return 0, 0
        stale: List[Any] = []
        tokens = 0
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_document",
                            match=qmodels.MatchValue(value=source_document),
                        ),
                        self._tenant_condition(tenant),
                    ],
                    must_not=[qmodels.HasIdCondition(has_id=list(point_ids))],
                ),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=["content"],
                with_vectors=False,
            )
            for point in points:
                stale.append(point.id)
                tokens += estimate_tokens((point.payload or {}).get("content", ""))
            if offset is None:
                break

        if stale:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.PointIdsList(points=stale),
            )
            logger.info("Pruned %d stale points from %s", len(stale), source_document)
        return len(stale), tokens

    def indexed_state(
        self,
        source_document: str,
        tenant: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        What is already indexed for this document: each point's payload
        without its text, keyed by point id. The payload says whether the
        chunk stored there carries its context, and what metadata it holds.

        The id is the answer to "is this the same text", since it is
        derived from that text, so a chunk whose id is missing here is one
        the index has never held: either new, or a version of a passage
        that has since been corrected. Points stored under ids worked out
        some other way are missing too, which is what makes an older
        document get rewritten rather than skipped and then pruned.
        """
        found: Dict[str, Dict[str, Any]] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(
                        key="source_document",
                        match=qmodels.MatchValue(value=source_document),
                    ),
                    self._tenant_condition(tenant),
                ]),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=qmodels.PayloadSelectorExclude(exclude=["content"]),
                with_vectors=False,
            )
            for point in points:
                found[str(point.id)] = point.payload or {}
            if offset is None:
                break

        return found

    def chunk_counts(self, tenant: Optional[str] = None) -> Dict[str, int]:
        """
        How many of this tenant's chunks carry their context and how many
        do not.

        A corpus with both is a corpus where the older documents lose
        comparisons for a reason that has nothing to do with how relevant
        they are, so the split is worth one cheap pair of counts.
        """
        counts = {"chunks_total": 0, "chunks_contextualized": 0, "chunks_plain": 0}
        tenant_filter = qmodels.Filter(must=[self._tenant_condition(tenant)])
        counts["chunks_total"] = self.client.count(
            collection_name=self.collection_name,
            count_filter=tenant_filter,
            exact=True,
        ).count
        counts["chunks_contextualized"] = self.client.count(
            collection_name=self.collection_name,
            count_filter=qmodels.Filter(must=[
                self._tenant_condition(tenant),
                qmodels.FieldCondition(
                    key="contextualized",
                    match=qmodels.MatchValue(value=True),
                ),
            ]),
            exact=True,
        ).count
        counts["chunks_plain"] = counts["chunks_total"] - counts["chunks_contextualized"]
        return counts

    def _plain_condition(self, tenant: Optional[str]) -> qmodels.Filter:
        """
        This tenant's points that carry no context. `must_not` on the flag
        also catches the points indexed before the flag existed, which have
        no such field at all and are exactly the ones left behind.
        """
        return qmodels.Filter(
            must=[self._tenant_condition(tenant)],
            must_not=[qmodels.FieldCondition(
                key="contextualized",
                match=qmodels.MatchValue(value=True),
            )],
        )

    def plain_points(
        self,
        tenant: Optional[str] = None,
        max_points: int = _LIST_MAX_POINTS,
    ) -> List[Dict[str, Any]]:
        """
        The points still indexed without context: id, chunk id, source and
        content. What a backfill has left to do, and the reason it is
        idempotent: a point that has been done no longer appears here.
        """
        found: List[Dict[str, Any]] = []
        offset = None
        while len(found) < max_points:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=self._plain_condition(tenant),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=["content", "chunk_id", "source_document"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                found.append({
                    "id": point.id,
                    "chunk_id": payload.get("chunk_id", ""),
                    "source_document": payload.get("source_document", ""),
                    "content": payload.get("content", ""),
                })
            if offset is None:
                break

        return found[:max_points]

    def recontextualize(self, chunks: List[SemanticChunk], point_ids: List[Any]) -> int:
        """
        Re-index existing points behind their new context, in place.

        The vectors are replaced and the flag is set on the point that is
        already there: no new point is written, so an interrupted backfill
        resumed later neither duplicates nor skips. A chunk that came back
        without context is left alone and will be picked up next time.
        """
        pending = [
            (point_id, chunk)
            for point_id, chunk in zip(point_ids, chunks)
            if chunk.context
        ]
        if not pending:
            return 0

        texts = [indexable_text(chunk) for _, chunk in pending]
        embeddings = self._generate_embeddings_batch(texts)
        if embeddings:
            self._check_dimension(embeddings[0])

        self.client.update_vectors(
            collection_name=self.collection_name,
            points=[
                qmodels.PointVectors(
                    id=point_id,
                    vector=(
                        {
                            DENSE_VECTOR: embedding,
                            LEXICAL_VECTOR: lexical_vector(text),
                        }
                        if self.has_lexical else embedding
                    ),
                )
                for (point_id, _), embedding, text in zip(pending, embeddings, texts)
            ],
        )
        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"contextualized": True},
            points=[point_id for point_id, _ in pending],
        )

        return len(pending)

    def recount_tokens(self, tenant: Optional[str] = None) -> int:
        """
        Rebuild the corpus size by reading it, for when the running total
        is not there: a deployment that indexed before the total existed,
        or one whose Redis was cleared.

        The normal path never comes here. Without it the size would read as
        zero on every existing deployment and the threshold would never be
        reached, which is a feature that silently never turns on.
        """
        total = 0
        scanned = 0
        offset = None
        while scanned < _LIST_MAX_POINTS:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qmodels.Filter(must=[self._tenant_condition(tenant)]),
                limit=_LIST_SCROLL_PAGE,
                offset=offset,
                with_payload=["content"],
                with_vectors=False,
            )
            total += sum(
                estimate_tokens((point.payload or {}).get("content", ""))
                for point in points
            )
            scanned += len(points)
            if offset is None:
                break

        return total

    def get_collection_stats(self, tenant: Optional[str] = None) -> Dict[str, Any]:
        """Collection statistics; includes the tenant's point count when given."""
        info = self.client.get_collection(self.collection_name)
        stats = {
            "points_count": info.points_count,
            "vectors_count": getattr(info, "vectors_count", None),
            "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
            "status": info.status,
            "retrieval_mode": "hybrid" if self.hybrid else "dense",
        }
        if tenant is not None:
            counted = self.client.count(
                collection_name=self.collection_name,
                count_filter=qmodels.Filter(must=[self._tenant_condition(tenant)]),
                exact=True,
            )
            stats["tenant_points_count"] = counted.count
        return stats

    def clear_collection(self) -> bool:
        """Delete and recreate the collection (use with caution)."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            self._ensure_collection()
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}", exc_info=True)
            return False


# Convenience functions
def create_vector_store(**kwargs) -> QdrantVectorStore:
    """Factory function to create a vector store instance."""
    return QdrantVectorStore(**kwargs)


# One store per process. Constructing one is expensive and stateful. 
# Rebuilding it per request meant paying those round-trips on every health probe and every document route.
#
# A failed construction is deliberately NOT remembered (the cache only
# stores return values): a Qdrant that is not up yet raises, the caller
# reports the dependency as down, and the next call tries again instead
# of pinning the process to a lie for its whole lifetime.
@lru_cache(maxsize=None)
def get_vector_store() -> QdrantVectorStore:
    """The process-wide vector store, built on first use."""
    return QdrantVectorStore()


def build_context_from_results(
    results: List[RetrievalResult],
    max_tokens: int = 2000,
    include_metadata: bool = True
) -> str:
    """
    Build a context string from retrieval results for LLM prompting.
    
    Args:
        results: List of RetrievalResult objects
        max_tokens: Approximate maximum context length (chars * 0.25)
        include_metadata: Whether to include source metadata
        
    Returns:
        Formatted context string
    """
    if not results:
        return ""
    
    context_parts = []
    current_length = 0
    max_chars = max_tokens * 4  # Rough token-to-char conversion
    
    for i, result in enumerate(results):
        if include_metadata:
            source = result.metadata.get("source_document", "Unknown")
            part = f"[Source: {source}]\n{result.content}\n"
        else:
            part = f"{result.content}\n"
        
        if current_length + len(part) > max_chars:
            break
            
        context_parts.append(part)
        current_length += len(part)
    
    return "\n---\n".join(context_parts)
