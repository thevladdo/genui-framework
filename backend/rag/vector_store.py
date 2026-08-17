"""
Qdrant Vector Store Module
Handles embedding storage, retrieval, and similarity search.
"""

import logging
import re
from typing import List, Optional, Dict, Any
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
from utils.cache import cacheable, clear_cache

logger = logging.getLogger(__name__)

# Hard cap when scanning the collection for document listings
_LIST_SCROLL_PAGE = 256
_LIST_MAX_POINTS = 50_000
DENSE_VECTOR = ""
LEXICAL_VECTOR = "lexical"
_FUSION_CANDIDATES = 20
_TOKEN = re.compile(r"[a-z0-9]{2,}")


def point_id_for(tenant: Optional[str], chunk_id: str) -> str:
    """
    The id of a chunk's point, derived from what the chunk is rather than
    drawn at random.

    A random id made every upload an insert, so uploading a document twice
    stored it twice and a search then found the same passage under two
    points. Deriving it means the second upload overwrites the first, which
    is what an upsert is for.
    """
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"genui:{tenant or DEFAULT_TENANT}:{chunk_id}",
    ))


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
            Number of chunks successfully indexed
        """
        if not chunks:
            logger.warning("No chunks provided for indexing")
            return 0
        
        indexed_count = 0
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            # What gets indexed is the chunk with its context in front; what gets stored is the chunk.
            texts = [indexable_text(chunk) for chunk in batch]
            try:
                embeddings = self._generate_embeddings_batch(texts)
            except EmbeddingConfigError:
                raise
            except Exception as e:
                logger.error(f"Embedding generation failed for batch {i}: {e}")
                continue
            if embeddings:
                self._check_dimension(embeddings[0])
            
            # Prepare points for Qdrant
            points = []
            for chunk, embedding in zip(batch, embeddings):
                point_id = point_id_for(tenant, chunk.chunk_id)
                
                payload = {
                    "content": chunk.content,
                    "chunk_id": chunk.chunk_id,
                    "source_document": chunk.source_document,
                    "tenant": tenant or DEFAULT_TENANT,
                    **chunk.metadata,
                    "contextualized": bool(chunk.context),
                }

                indexed_text = indexable_text(chunk)
                points.append(qmodels.PointStruct(
                    id=point_id,
                    vector=(
                        {
                            DENSE_VECTOR: embedding,
                            LEXICAL_VECTOR: lexical_vector(indexed_text),
                        }
                        if self.has_lexical else embedding
                    ),
                    payload=payload,
                ))
            
            # Upsert to Qdrant
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
                indexed_count += len(points)
                logger.info(f"Indexed batch {i//batch_size + 1}: {len(points)} chunks")
                
            except Exception as e:
                logger.error(f"Failed to upsert batch {i}: {e}")
                continue
        
        logger.info(f"Total indexed: {indexed_count}/{len(chunks)} chunks")

        if indexed_count:
            # Cached search results may not include the new content
            clear_cache()

        return indexed_count
    
    @cacheable()
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

        # Perform search using async client
        try:
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
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
        
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
        Negative means the deletion failed.
        """
        removed_tokens = self._source_tokens(source_document, tenant)
        try:
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
            # Cached search results may still reference the deleted content
            clear_cache()
            return removed_tokens

        except Exception as e:
            logger.error(f"Deletion failed for {source_document}: {e}")
            return -1

    def _source_tokens(self, source_document: str, tenant: Optional[str]) -> int:
        """
        Tokens held by one document, read before it is deleted.

        One scroll over one document's payloads, on an operation that
        happens rarely and is already scanning to delete.
        """
        total = 0
        offset = None
        try:
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
        except Exception as e:
            logger.warning(f"Could not size {source_document} before deleting: {e}")
            return 0

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

        try:
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

        except Exception as e:
            logger.error(f"Document listing failed: {e}")

        return sorted(documents.values(), key=lambda d: d["source_document"])

    def prune_removed_chunks(
        self,
        source_document: str,
        chunk_ids: List[str],
        tenant: Optional[str] = None,
    ) -> int:
        """
        Drop this document's points that the version just indexed no longer
        accounts for.

        Two of them. A document edited down to fewer chunks leaves a tail
        that nothing overwrites, and its text would go on grounding numbers
        and URLs that the document no longer contains. And a document
        indexed before point ids were derived is stored under random ones,
        so the new write lands beside it instead of on top.

        Only safe when the whole document was just written: a resumed
        upload indexes part of it, and the rest is work already paid for.
        """
        if not chunk_ids:
            return 0
        try:
            current = [point_id_for(tenant, chunk_id) for chunk_id in chunk_ids]
            before = self.client.count(
                collection_name=self.collection_name,
                count_filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(
                        key="source_document",
                        match=qmodels.MatchValue(value=source_document),
                    ),
                    self._tenant_condition(tenant),
                ]),
                exact=True,
            ).count

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
                        ],
                        must_not=[qmodels.HasIdCondition(has_id=current)],
                    )
                ),
            )
            removed = before - len(current)
            if removed > 0:
                logger.info(
                    "Pruned %d stale points from %s", removed, source_document
                )
                clear_cache()
            return max(0, removed)

        except Exception as e:
            logger.warning(f"Could not prune stale points of {source_document}: {e}")
            return 0

    def contextualized_chunk_ids(
        self,
        source_document: str,
        tenant: Optional[str] = None,
    ) -> set:
        """
        The chunk ids of this document already indexed WITH their context.

        A large document is thousands of model calls, and an upload that
        dies halfway has already paid for the ones it made. Re-uploading
        skips those instead of buying them again, which is what makes the
        work resumable rather than restartable. Chunks indexed without
        context are not listed: they still have their call to make.
        """
        found = set()
        offset = None
        try:
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=qmodels.Filter(must=[
                        qmodels.FieldCondition(
                            key="source_document",
                            match=qmodels.MatchValue(value=source_document),
                        ),
                        qmodels.FieldCondition(
                            key="contextualized",
                            match=qmodels.MatchValue(value=True),
                        ),
                        self._tenant_condition(tenant),
                    ]),
                    limit=_LIST_SCROLL_PAGE,
                    offset=offset,
                    with_payload=["chunk_id"],
                    with_vectors=False,
                )
                found.update(
                    (point.payload or {}).get("chunk_id")
                    for point in points
                    if (point.payload or {}).get("chunk_id")
                )
                if offset is None:
                    break
        except Exception as e:
            logger.warning(f"Could not read indexing progress for {source_document}: {e}")

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
        try:
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
        except Exception as e:
            logger.warning(f"Chunk counts failed: {e}")
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
        try:
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
        except Exception as e:
            logger.error(f"Could not list the points without context: {e}")

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

        try:
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
        except Exception as e:
            logger.error(f"Backfill update failed: {e}")
            return 0

        clear_cache()
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
        try:
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
        except Exception as e:
            logger.warning(f"Could not rebuild the corpus size: {e}")

        return total

    def get_collection_stats(self, tenant: Optional[str] = None) -> Dict[str, Any]:
        """Collection statistics; includes the tenant's point count when given."""
        try:
            info = self.client.get_collection(self.collection_name)
            stats = {
                "points_count": info.points_count,
                "vectors_count": getattr(info, "vectors_count", None),
                "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
                "status": info.status,
                "retrieval_mode": "hybrid" if self.hybrid else "dense",
            }
            if tenant is not None:
                try:
                    counted = self.client.count(
                        collection_name=self.collection_name,
                        count_filter=qmodels.Filter(must=[self._tenant_condition(tenant)]),
                        exact=True,
                    )
                    stats["tenant_points_count"] = counted.count
                except Exception as e:
                    logger.warning(f"Tenant count failed: {e}")
            return stats
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    def clear_collection(self) -> bool:
        """Delete and recreate the collection (use with caution)."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            self._ensure_collection()
            clear_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
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
