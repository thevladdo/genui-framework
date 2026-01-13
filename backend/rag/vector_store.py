"""
Qdrant Vector Store Module
Handles embedding storage, retrieval, and similarity search.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import uuid
import asyncio

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from llama_index.embeddings.openai import OpenAIEmbedding

from config import settings
from .chunker import SemanticChunk
from utils.cache import cacheable

logger = logging.getLogger(__name__)


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
        embedding_model: Optional[OpenAIEmbedding] = None,
    ):
        """
        Initialize connection to Qdrant.
        
        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Name of the vector collection
            embedding_model: Model for generating embeddings
        """
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection_name = collection_name or settings.qdrant_collection
        
        # Initialize Qdrant client (both sync and async)
        self.client = QdrantClient(host=self.host, port=self.port)
        self.async_client = AsyncQdrantClient(host=self.host, port=self.port)
        
        # Embedding model
        self.embed_model = embedding_model or OpenAIEmbedding(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=settings.qdrant_vector_size,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                
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
            else:
                logger.info(f"Collection {self.collection_name} already exists")
                
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        return self.embed_model.get_text_embedding(text)
    
    async def _generate_embedding_async(self, text: str) -> List[float]:
        """Generate embedding for a text string asynchronously."""
        # OpenAI embeddings are already async-capable
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_model.get_text_embedding, text)
    
    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return self.embed_model.get_text_embedding_batch(texts)
    
    def index_chunks(
        self,
        chunks: List[SemanticChunk],
        batch_size: int = 100
    ) -> int:
        """
        Index semantic chunks into Qdrant.
        
        Args:
            chunks: List of SemanticChunk objects to index
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
            
            # Generate embeddings for batch
            texts = [chunk.content for chunk in batch]
            try:
                embeddings = self._generate_embeddings_batch(texts)
            except Exception as e:
                logger.error(f"Embedding generation failed for batch {i}: {e}")
                continue
            
            # Prepare points for Qdrant
            points = []
            for chunk, embedding in zip(batch, embeddings):
                point_id = str(uuid.uuid4())
                
                payload = {
                    "content": chunk.content,
                    "chunk_id": chunk.chunk_id,
                    "source_document": chunk.source_document,
                    **chunk.metadata,
                }
                
                points.append(qmodels.PointStruct(
                    id=point_id,
                    vector=embedding,
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
        return indexed_count
    
    def search(
        self,
        query: str,
        top_k: int = None,
        score_threshold: float = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.search_async(query, top_k, score_threshold, filters))
    
    @cacheable()
    async def search_async(
        self,
        query: str,
        top_k: int = None,
        score_threshold: float = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """
        Perform semantic search asynchronously.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Optional metadata filters
            
        Returns:
            List of RetrievalResult objects
        """
        top_k = top_k or settings.top_k_retrieval
        score_threshold = score_threshold or settings.similarity_threshold
        
        # Generate query embedding asynchronously
        query_embedding = await self._generate_embedding_async(query)
        
        # Build filter conditions if provided
        qdrant_filter = None
        if filters:
            conditions = []
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
    
    def delete_by_source(self, source_document: str) -> bool:
        """
        Delete all chunks from a specific source document.
        
        Args:
            source_document: The source identifier to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="source_document",
                                match=qmodels.MatchValue(value=source_document),
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted chunks from source: {source_document}")
            return True
            
        except Exception as e:
            logger.error(f"Deletion failed for {source_document}: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    def clear_collection(self) -> bool:
        """Delete and recreate the collection (use with caution)."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            self._ensure_collection()
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False


# Convenience functions
def create_vector_store(**kwargs) -> QdrantVectorStore:
    """Factory function to create a vector store instance."""
    return QdrantVectorStore(**kwargs)


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
