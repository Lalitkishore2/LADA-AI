"""
LADA v11.0 - RAG (Retrieval Augmented Generation) Engine
Ground LLM responses in local documents and knowledge base.

Supports: PDF, DOCX, TXT, MD, JSON, CSV ingestion with chunking,
embedding, and context-aware retrieval for LLM prompts.
"""

import os
import re
import json
import hashlib
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from modules.vector_memory import VectorMemorySystem, get_vector_memory, CHROMADB_OK
    VECTOR_OK = True
except ImportError:
    VECTOR_OK = False
    CHROMADB_OK = False

try:
    import fitz as pymupdf  # PyMuPDF
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from docx import Document as DocxDocument
    DOCX_OK = True
except ImportError:
    DOCX_OK = False


@dataclass
class DocumentChunk:
    """A chunk of text from a document."""
    content: str
    source_file: str
    page_number: int = 0
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentChunker:
    """Split documents into overlapping chunks for embedding."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str, source_file: str = "",
                   page_number: int = 0) -> List[DocumentChunk]:
        """Split text into overlapping word-based chunks."""
        if not text or not text.strip():
            return []

        # Clean text
        text = re.sub(r'\s+', ' ', text).strip()
        words = text.split()

        if len(words) <= self.chunk_size:
            return [DocumentChunk(
                content=text, source_file=source_file,
                page_number=page_number, chunk_index=0, total_chunks=1
            )]

        chunks = []
        start = 0

        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk_text = ' '.join(words[start:end])

            chunks.append(DocumentChunk(
                content=chunk_text,
                source_file=source_file,
                page_number=page_number,
                chunk_index=len(chunks),
            ))

            if end >= len(words):
                break

            start = end - self.chunk_overlap

        for c in chunks:
            c.total_chunks = len(chunks)

        return chunks


class DocumentIngester:
    """Ingest documents from various formats."""

    def __init__(self):
        self.chunker = DocumentChunker()

    def ingest_file(self, file_path: str) -> List[DocumentChunk]:
        """Ingest a single file and return chunks."""
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[RAG] File not found: {file_path}")
            return []

        ext = path.suffix.lower()
        try:
            if ext == '.pdf':
                return self._ingest_pdf(file_path)
            elif ext == '.docx':
                return self._ingest_docx(file_path)
            elif ext in ('.txt', '.md', '.log', '.py', '.js', '.ts', '.json', '.csv', '.yaml', '.yml'):
                return self._ingest_text(file_path)
            else:
                logger.warning(f"[RAG] Unsupported format: {ext}")
                return []
        except Exception as e:
            logger.error(f"[RAG] Ingest error for {file_path}: {e}")
            return []

    def ingest_directory(self, dir_path: str,
                         extensions: Optional[List[str]] = None) -> List[DocumentChunk]:
        """Ingest all matching files from a directory."""
        default_exts = {'.pdf', '.docx', '.txt', '.md', '.json', '.csv'}
        allowed = set(extensions) if extensions else default_exts

        all_chunks = []
        dir_p = Path(dir_path)

        if not dir_p.exists():
            return []

        for fp in dir_p.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in allowed:
                chunks = self.ingest_file(str(fp))
                all_chunks.extend(chunks)

        logger.info(f"[RAG] Ingested {len(all_chunks)} chunks from {dir_path}")
        return all_chunks

    def _ingest_pdf(self, file_path: str) -> List[DocumentChunk]:
        if not PDF_OK:
            logger.warning("[RAG] PyMuPDF not installed for PDF reading")
            return []

        chunks = []
        doc = pymupdf.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                page_chunks = self.chunker.chunk_text(
                    text, source_file=file_path, page_number=page_num + 1
                )
                chunks.extend(page_chunks)
        doc.close()
        return chunks

    def _ingest_docx(self, file_path: str) -> List[DocumentChunk]:
        if not DOCX_OK:
            logger.warning("[RAG] python-docx not installed")
            return []

        doc = DocxDocument(file_path)
        full_text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
        return self.chunker.chunk_text(full_text, source_file=file_path)

    def _ingest_text(self, file_path: str) -> List[DocumentChunk]:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        return self.chunker.chunk_text(text, source_file=file_path)


class RAGEngine:
    """
    Retrieval Augmented Generation Engine.

    Ingests documents, stores them in vector memory,
    and retrieves relevant context for LLM prompts.

    Features:
    - Multi-format document ingestion (PDF, DOCX, TXT, MD, etc.)
    - Semantic chunking with overlap
    - Context-aware retrieval with source tracking
    - Token-budget-aware context assembly
    - Document management (add, remove, list)
    - Hybrid search (semantic + keyword)
    """

    def __init__(self, data_dir: str = "data/rag_knowledge"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.ingester = DocumentIngester()
        self.vector_memory = get_vector_memory(
            data_dir=os.path.join(data_dir, "vectors")
        )

        # Track ingested documents
        self._doc_index_path = os.path.join(data_dir, "document_index.json")
        self._doc_index: Dict[str, Dict[str, Any]] = self._load_doc_index()

    def _load_doc_index(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self._doc_index_path):
            try:
                with open(self._doc_index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_doc_index(self):
        try:
            with open(self._doc_index_path, 'w', encoding='utf-8') as f:
                json.dump(self._doc_index, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[RAG] Failed to save doc index: {e}")

    def ingest(self, file_path: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Ingest a document into the RAG knowledge base.

        Returns result dict with status and chunk count.
        """
        file_path = os.path.abspath(file_path)
        file_hash = self._file_hash(file_path)

        # Check if already ingested
        if file_hash in self._doc_index:
            return {
                "status": "already_ingested",
                "file": file_path,
                "chunks": self._doc_index[file_hash].get("chunks", 0),
            }

        # Ingest and chunk
        chunks = self.ingester.ingest_file(file_path)
        if not chunks:
            return {"status": "no_content", "file": file_path, "chunks": 0}

        # Store chunks in vector memory
        chunk_ids = []
        for chunk in chunks:
            chunk_tags = list(tags or []) + [
                os.path.basename(file_path),
                Path(file_path).suffix.lstrip('.'),
            ]

            mem_id = self.vector_memory.store(
                content=chunk.content,
                memory_type="fact",
                importance=0.6,
                source=f"rag:{file_path}",
                tags=chunk_tags,
            )
            if mem_id:
                chunk_ids.append(mem_id)

        # Track in index
        self._doc_index[file_hash] = {
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "chunks": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "tags": tags or [],
            "ingested_at": time.time(),
            "file_size": os.path.getsize(file_path),
        }
        self._save_doc_index()

        logger.info(f"[RAG] Ingested {file_path}: {len(chunk_ids)} chunks")
        return {
            "status": "success",
            "file": file_path,
            "chunks": len(chunk_ids),
        }

    def ingest_directory(self, dir_path: str,
                         extensions: Optional[List[str]] = None,
                         tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Ingest all documents from a directory."""
        default_exts = ['.pdf', '.docx', '.txt', '.md']
        exts = extensions or default_exts

        results = []
        dir_p = Path(dir_path)
        if not dir_p.exists():
            return {"status": "directory_not_found", "results": []}

        for fp in dir_p.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in exts:
                result = self.ingest(str(fp), tags=tags)
                results.append(result)

        total_chunks = sum(r.get("chunks", 0) for r in results)
        return {
            "status": "success",
            "files_processed": len(results),
            "total_chunks": total_chunks,
            "results": results,
        }

    def query(self, question: str, n_results: int = 5,
              max_context_tokens: int = 2000) -> Dict[str, Any]:
        """
        Query the RAG knowledge base.

        Returns relevant context chunks with sources.
        """
        results = self.vector_memory.search(
            query=question,
            n_results=n_results,
            memory_type="fact",
            recency_weight=0.1,  # Facts don't decay much
        )

        if not results:
            return {
                "context": "",
                "sources": [],
                "chunks_found": 0,
            }

        # Assemble context within token budget
        context_parts = []
        sources = set()
        estimated_tokens = 0

        for r in results:
            entry = r["content"]
            entry_tokens = len(entry.split()) * 1.3

            if estimated_tokens + entry_tokens > max_context_tokens:
                break

            context_parts.append(entry)
            estimated_tokens += entry_tokens

            source = r.get("source", "")
            if source.startswith("rag:"):
                sources.add(source[4:])

        context = "\n\n".join(context_parts)

        return {
            "context": context,
            "sources": list(sources),
            "chunks_found": len(results),
            "chunks_used": len(context_parts),
        }

    def build_augmented_prompt(self, user_query: str,
                               system_prompt: str = "",
                               max_context_tokens: int = 1500) -> str:
        """
        Build a RAG-augmented prompt for LLM.

        Injects relevant document context into the prompt.
        """
        rag_result = self.query(user_query, max_context_tokens=max_context_tokens)

        if not rag_result["context"]:
            return ""

        sources_str = ""
        if rag_result["sources"]:
            source_names = [os.path.basename(s) for s in rag_result["sources"]]
            sources_str = f"\n[Sources: {', '.join(source_names)}]"

        augmented = (
            f"Use the following knowledge base context to help answer the user's question. "
            f"If the context doesn't contain relevant information, say so.\n\n"
            f"--- KNOWLEDGE BASE CONTEXT ---\n"
            f"{rag_result['context']}\n"
            f"--- END CONTEXT ---{sources_str}\n\n"
            f"User question: {user_query}"
        )

        return augmented

    def list_documents(self) -> List[Dict[str, Any]]:
        """List all ingested documents."""
        docs = []
        for file_hash, info in self._doc_index.items():
            docs.append({
                "filename": info.get("filename", "unknown"),
                "file_path": info.get("file_path", ""),
                "chunks": info.get("chunks", 0),
                "tags": info.get("tags", []),
                "ingested_at": info.get("ingested_at", 0),
                "file_size": info.get("file_size", 0),
                "hash": file_hash,
            })
        return docs

    def remove_document(self, file_path: str) -> bool:
        """Remove a document from the knowledge base."""
        file_path = os.path.abspath(file_path)
        file_hash = self._file_hash(file_path)

        if file_hash not in self._doc_index:
            return False

        # Remove chunks from vector memory
        chunk_ids = self._doc_index[file_hash].get("chunk_ids", [])
        if CHROMADB_OK and chunk_ids:
            try:
                fact_collection = self.vector_memory._collections.get("fact")
                if fact_collection:
                    fact_collection.delete(ids=chunk_ids)
                all_collection = self.vector_memory._collections.get("all")
                if all_collection:
                    all_collection.delete(ids=chunk_ids)
            except Exception as e:
                logger.error(f"[RAG] Remove chunks error: {e}")

        del self._doc_index[file_hash]
        self._save_doc_index()
        return True

    def _file_hash(self, file_path: str) -> str:
        """Generate hash for file identity tracking."""
        try:
            stat = os.stat(file_path)
            key = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(key.encode()).hexdigest()
        except Exception:
            return hashlib.md5(file_path.encode()).hexdigest()

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG engine statistics."""
        return {
            "documents_ingested": len(self._doc_index),
            "total_chunks": sum(d.get("chunks", 0) for d in self._doc_index.values()),
            "vector_memory_stats": self.vector_memory.get_stats(),
            "supported_formats": [".pdf", ".docx", ".txt", ".md", ".json", ".csv"],
        }


# Singleton
_rag_instance: Optional[RAGEngine] = None

def get_rag_engine(data_dir: str = "data/rag_knowledge") -> RAGEngine:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGEngine(data_dir=data_dir)
    return _rag_instance
