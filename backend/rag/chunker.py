"""
Semantic Chunking Module using LlamaIndex
Implements content-aware document splitting based on semantic similarity
rather than fixed character counts.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from llama_index.core import Document, SimpleDirectoryReader
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceSplitter,
)
from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from config import settings
from llm.embeddings import EmbeddingClient, create_embedding_client

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4


class _ClientEmbedding(BaseEmbedding):
    """
    LlamaIndex adapter over the provider-neutral EmbeddingClient, so the
    semantic splitter embeds through the configured endpoint too — never
    through a hardwired OpenAI call.
    """

    _client: EmbeddingClient = PrivateAttr()

    def __init__(self, client: EmbeddingClient, **kwargs):
        super().__init__(model_name=client.model, **kwargs)
        self._client = client

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._client.embed([query])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._client.embed([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._client.embed(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)


@dataclass
class SemanticChunk:
    """Represents a semantically coherent chunk of text with metadata."""
    content: str
    metadata: Dict[str, Any]
    chunk_id: str
    source_document: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    context: Optional[str] = None
    point_id: Optional[str] = None


class SemanticChunker:
    """
    LlamaIndex-based semantic chunker that splits documents
    based on semantic similarity between sentences.
    
    The key insight: adjacent sentences with similar embeddings
    likely belong to the same conceptual unit and should stay together.
    """
    
    def __init__(
        self,
        embed_model: Optional[EmbeddingClient] = None,
        breakpoint_percentile: int = None,
        buffer_size: int = None,
        semantic: bool = True,
    ):
        """
        Initialize the semantic chunker.

        Args:
            embed_model: EmbeddingClient for semantic similarity (created
                from config if not provided; raises EmbeddingConfigError
                when embedding is unconfigured — no silent OpenAI fallback)
            breakpoint_percentile: Percentile threshold for detecting breakpoints Higher = fewer, larger chunks
            buffer_size: Number of sentences to include around breakpoints
            semantic: False cuts at sentences only, with no embedding client
                built and nothing embedded
        """
        self.breakpoint_percentile = (
            breakpoint_percentile or settings.breakpoint_percentile_threshold
        )
        self.buffer_size = buffer_size or settings.buffer_size

        self.embed_model = None
        self.semantic_splitter = None
        if semantic:
            self.embed_model = _ClientEmbedding(embed_model or create_embedding_client())
            self.semantic_splitter = SemanticSplitterNodeParser(
                buffer_size=self.buffer_size,
                breakpoint_percentile_threshold=self.breakpoint_percentile,
                embed_model=self.embed_model,
            )
        
        # Fallback splitter for very long documents or edge cases
        self.fallback_splitter = SentenceSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    
    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        source_name: str = "unknown"
    ) -> List[SemanticChunk]:
        """
        Split raw text into semantic chunks.
        
        Args:
            text: The text content to chunk
            metadata: Additional metadata to attach to each chunk
            source_name: Identifier for the source document
            
        Returns:
            List of SemanticChunk objects
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for chunking from {source_name}")
            return []
        
        metadata = metadata or {}
        
        # Create a LlamaIndex Document
        doc = Document(
            text=text,
            metadata={
                "source": source_name,
                **metadata
            }
        )
        
        if self.semantic_splitter is None:
            nodes = self.fallback_splitter.get_nodes_from_documents([doc])
        else:
            try:
                nodes = self.semantic_splitter.get_nodes_from_documents([doc])
                logger.info(f"Semantic chunking produced {len(nodes)} chunks from {source_name}")

            except Exception as e:
                logger.warning(f"Semantic chunking failed, using fallback: {e}")
                nodes = self.fallback_splitter.get_nodes_from_documents([doc])

        nodes = self._within_chunk_size(nodes)

        # Convert to our SemanticChunk format
        chunks = []
        for i, node in enumerate(nodes):
            chunk = SemanticChunk(
                content=node.get_content(),
                metadata={
                    **metadata,
                    "node_id": node.node_id,
                    "relationships": str(node.relationships) if node.relationships else None,
                },
                chunk_id=f"{source_name}_{i}",
                source_document=source_name,
                start_char=node.start_char_idx,
                end_char=node.end_char_idx,
            )
            chunks.append(chunk)
        
        return chunks
    
    def _within_chunk_size(self, nodes: List[Any]) -> List[Any]:
        """
        Cut the nodes that came back too large, with the sentence splitter
        already built for the fallback.

        The semantic splitter decides where meaning changes and has no size
        limit at all, so a document whose meaning barely shifts comes back
        as a few enormous nodes. Measured on real documents: a median chunk
        of 439 tokens next to a largest of 3654, which is more than twice
        the whole context budget a zone render gives its retrieved passages.
        A chunk like that scores a perfect recall and leaves no room for any
        other result, which is why the size cannot be left to meaning alone.

        `chunk_size` is the ceiling, not the target: a node under it keeps
        the boundary the semantic splitter chose. That setting used to reach
        the fallback path only, so it read as a lie on every deployment.
        """
        limit = settings.chunk_size * CHARS_PER_TOKEN
        sized = []

        for node in nodes:
            text = node.get_content()
            if len(text) <= limit:
                sized.append(node)
                continue

            parent_start = node.start_char_idx or 0
            pieces = self.fallback_splitter.get_nodes_from_documents(
                [Document(text=text, metadata=dict(node.metadata or {}))]
            )
            if not pieces:
                logger.warning("Re-cutting returned nothing; keeping the node whole")
                sized.append(node)
                continue

            for piece in pieces:
                if piece.start_char_idx is not None:
                    piece.start_char_idx += parent_start
                if piece.end_char_idx is not None:
                    piece.end_char_idx += parent_start
            sized.extend(pieces)

        if len(sized) != len(nodes):
            logger.info(
                "Chunks over %d chars re-cut: %d nodes became %d",
                limit, len(nodes), len(sized),
            )
        return sized

    def chunk_document(
        self,
        file_path: Path,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SemanticChunk]:
        """
        Load and chunk a document file.
        
        Supports: PDF, DOCX, TXT, MD, HTML
        
        Args:
            file_path: Path to the document
            additional_metadata: Extra metadata (e.g., document title, URL)
            
        Returns:
            List of SemanticChunk objects
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        # Use LlamaIndex's reader for document loading
        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
        )
        
        documents = reader.load_data()
        
        if not documents:
            logger.warning(f"No content extracted from {file_path}")
            return []
        
        # Combine all document parts and chunk
        all_chunks = []
        for doc in documents:
            base_metadata = {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_type": file_path.suffix.lower(),
                **(additional_metadata or {}),
                **doc.metadata,
            }
            
            chunks = self.chunk_text(
                text=doc.text,
                metadata=base_metadata,
                source_name=file_path.stem,
            )
            all_chunks.extend(chunks)
        
        logger.info(f"Total chunks from {file_path.name}: {len(all_chunks)}")
        return all_chunks
    
    def chunk_directory(
        self,
        directory_path: Path,
        recursive: bool = True,
        file_extensions: Optional[List[str]] = None
    ) -> List[SemanticChunk]:
        """
        Chunk all documents in a directory.
        
        Args:
            directory_path: Path to the directory
            recursive: Whether to process subdirectories
            file_extensions: List of extensions to process (e.g., ['.pdf', '.docx'])
            
        Returns:
            List of SemanticChunk objects from all documents
        """
        directory_path = Path(directory_path)
        
        if not directory_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory_path}")
        
        # Default supported extensions
        if file_extensions is None:
            file_extensions = ['.pdf', '.docx', '.txt', '.md', '.html']
        
        # Find all matching files
        pattern = "**/*" if recursive else "*"
        files = [
            f for f in directory_path.glob(pattern)
            if f.is_file() and f.suffix.lower() in file_extensions
        ]
        
        logger.info(f"Found {len(files)} documents to process in {directory_path}")
        
        all_chunks = []
        for file_path in files:
            try:
                chunks = self.chunk_document(file_path)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}", exc_info=True)
                continue
        
        return all_chunks


# Factory function for easy instantiation
def create_chunker(
    use_semantic: bool = None,
    **kwargs
) -> SemanticChunker:
    """
    Factory function to create a chunker based on settings.
    
    Args:
        use_semantic: Override settings.use_semantic_chunking
        **kwargs: Additional arguments for SemanticChunker
        
    Returns:
        Configured SemanticChunker instance
    """
    if use_semantic is None:
        use_semantic = settings.use_semantic_chunking
    
    return SemanticChunker(semantic=use_semantic, **kwargs)


def cutting_embeddings(text: str) -> int:
    """
    Texts the configured chunking embeds to cut `text`: the semantic splitter
    embeds one group per sentence, the sentence splitter embeds nothing.
    Counted with the tokenizer the semantic splitter uses by default, so
    nothing is embedded to find out.
    """
    if not settings.use_semantic_chunking or not text or not text.strip():
        return 0
    from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer

    return len(split_by_sentence_tokenizer()(text))
