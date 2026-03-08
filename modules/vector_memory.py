"""
LADA v11.0 - Vector Memory System
Semantic memory using ChromaDB for intelligent retrieval with temporal decay.

Replaces pickle-based memory with embedding-powered semantic search,
importance weighting, and automatic memory consolidation.
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# Conditional imports
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_OK = True
except ImportError:
    chromadb = None
    CHROMADB_OK = False

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_OK = True
except ImportError:
    SentenceTransformer = None
    EMBEDDINGS_OK = False


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""
    content: str
    memory_type: str = "conversation"  # conversation, fact, preference, task, observation
    importance: float = 0.5  # 0.0 to 1.0
    source: str = "user"
    tags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "memory_type": self.memory_type,
            "importance": self.importance,
            "source": self.source,
            "tags": json.dumps(self.tags),
            "timestamp": self.timestamp,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "created_date": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class EmbeddingProvider:
    """Manages embedding generation with fallback strategies."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._use_chromadb_default = False

        if EMBEDDINGS_OK:
            try:
                self._model = SentenceTransformer(model_name)
                logger.info(f"[VectorMemory] Loaded embedding model: {model_name}")
            except Exception as e:
                logger.warning(f"[VectorMemory] SentenceTransformer failed: {e}, using ChromaDB default")
                self._use_chromadb_default = True
        else:
            logger.info("[VectorMemory] sentence-transformers not installed, using ChromaDB default embeddings")
            self._use_chromadb_default = True

    @property
    def uses_custom_embeddings(self) -> bool:
        return self._model is not None

    def encode(self, texts: List[str]) -> Optional[List[List[float]]]:
        if self._model is None:
            return None
        try:
            embeddings = self._model.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"[VectorMemory] Embedding error: {e}")
            return None


class VectorMemorySystem:
    """
    Semantic vector memory with ChromaDB backend.

    Features:
    - Embedding-based semantic search
    - Importance-weighted retrieval
    - Temporal decay (recent memories rank higher)
    - Automatic memory consolidation
    - Multiple memory collections (conversations, facts, preferences)
    - Gravity indexing (frequently accessed memories boost)
    """

    MEMORY_TYPES = ["conversation", "fact", "preference", "task", "observation", "summary"]

    def __init__(self, data_dir: str = "data/vector_memory", embedding_model: str = "all-MiniLM-L6-v2"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self._embedder = EmbeddingProvider(embedding_model)
        self._client = None
        self._collections: Dict[str, Any] = {}
        self._initialized = False
        self._stats = {"total_memories": 0, "queries": 0, "consolidations": 0}

        self._init_chromadb()

    def _init_chromadb(self):
        """Initialize ChromaDB client and collections."""
        if not CHROMADB_OK:
            logger.warning("[VectorMemory] ChromaDB not installed. Using in-memory fallback.")
            self._init_fallback()
            return

        try:
            self._client = chromadb.PersistentClient(
                path=self.data_dir,
            )

            # Create collections for each memory type
            for mem_type in self.MEMORY_TYPES:
                collection_name = f"lada_{mem_type}"
                self._collections[mem_type] = self._client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )

            # Main unified collection for cross-type search
            self._collections["all"] = self._client.get_or_create_collection(
                name="lada_all_memories",
                metadata={"hnsw:space": "cosine"}
            )

            self._initialized = True
            total = sum(c.count() for c in self._collections.values())
            self._stats["total_memories"] = total
            logger.info(f"[VectorMemory] Initialized ChromaDB with {total} total memories")

        except Exception as e:
            logger.error(f"[VectorMemory] ChromaDB init failed: {e}")
            self._init_fallback()

    def _init_fallback(self):
        """Fallback to in-memory storage when ChromaDB unavailable."""
        self._fallback_store: List[Dict[str, Any]] = []
        fallback_file = os.path.join(self.data_dir, "fallback_memory.json")
        if os.path.exists(fallback_file):
            try:
                with open(fallback_file, "r", encoding="utf-8") as f:
                    self._fallback_store = json.load(f)
                logger.info(f"[VectorMemory] Loaded {len(self._fallback_store)} memories from fallback")
            except Exception:
                self._fallback_store = []
        self._initialized = True

    def _save_fallback(self):
        """Persist fallback store to disk."""
        fallback_file = os.path.join(self.data_dir, "fallback_memory.json")
        try:
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump(self._fallback_store, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[VectorMemory] Fallback save error: {e}")

    def store(self, content: str, memory_type: str = "conversation",
              importance: float = 0.5, source: str = "user",
              tags: Optional[List[str]] = None) -> str:
        """
        Store a memory with semantic embedding.

        Returns the memory ID.
        """
        if not content or not content.strip():
            return ""

        entry = MemoryEntry(
            content=content.strip(),
            memory_type=memory_type,
            importance=max(0.0, min(1.0, importance)),
            source=source,
            tags=tags or [],
        )

        # Generate deterministic ID
        mem_id = hashlib.sha256(
            f"{content}:{entry.timestamp}".encode()
        ).hexdigest()[:16]

        if not CHROMADB_OK:
            # Fallback storage
            self._fallback_store.append({
                "id": mem_id, "content": content,
                **entry.to_metadata()
            })
            self._save_fallback()
            self._stats["total_memories"] += 1
            return mem_id

        metadata = entry.to_metadata()

        try:
            # Store in type-specific collection
            if memory_type in self._collections:
                if self._embedder.uses_custom_embeddings:
                    embeddings = self._embedder.encode([content])
                    self._collections[memory_type].upsert(
                        ids=[mem_id],
                        documents=[content],
                        metadatas=[metadata],
                        embeddings=embeddings,
                    )
                else:
                    self._collections[memory_type].upsert(
                        ids=[mem_id],
                        documents=[content],
                        metadatas=[metadata],
                    )

            # Also store in unified collection
            if self._embedder.uses_custom_embeddings:
                embeddings = self._embedder.encode([content])
                self._collections["all"].upsert(
                    ids=[mem_id],
                    documents=[content],
                    metadatas=[metadata],
                    embeddings=embeddings,
                )
            else:
                self._collections["all"].upsert(
                    ids=[mem_id],
                    documents=[content],
                    metadatas=[metadata],
                )

            self._stats["total_memories"] += 1
            logger.debug(f"[VectorMemory] Stored memory {mem_id}: {content[:50]}...")
            return mem_id

        except Exception as e:
            logger.error(f"[VectorMemory] Store error: {e}")
            return ""

    def search(self, query: str, n_results: int = 5,
               memory_type: Optional[str] = None,
               min_importance: float = 0.0,
               recency_weight: float = 0.3) -> List[Dict[str, Any]]:
        """
        Semantic search across memories with importance and recency weighting.

        Args:
            query: Natural language search query
            n_results: Max results to return
            memory_type: Filter by type (None = search all)
            min_importance: Minimum importance threshold
            recency_weight: How much to boost recent memories (0-1)

        Returns:
            List of memory dicts sorted by relevance score
        """
        if not query or not query.strip():
            return []

        self._stats["queries"] += 1

        if not CHROMADB_OK:
            return self._search_fallback(query, n_results, memory_type, min_importance)

        try:
            collection = self._collections.get(memory_type or "all")
            if collection is None:
                collection = self._collections["all"]

            # Fetch more than needed for re-ranking
            fetch_n = min(n_results * 3, collection.count()) or n_results
            if fetch_n == 0:
                return []

            if self._embedder.uses_custom_embeddings:
                query_embedding = self._embedder.encode([query])
                results = collection.query(
                    query_embeddings=query_embedding,
                    n_results=fetch_n,
                    where={"importance": {"$gte": min_importance}} if min_importance > 0 else None,
                )
            else:
                results = collection.query(
                    query_texts=[query],
                    n_results=fetch_n,
                    where={"importance": {"$gte": min_importance}} if min_importance > 0 else None,
                )

            if not results or not results["documents"] or not results["documents"][0]:
                return []

            # Re-rank with temporal decay and importance weighting
            now = time.time()
            scored_results = []

            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0

                # Cosine similarity (chromadb returns distance, lower is better)
                semantic_score = max(0, 1.0 - distance)

                # Importance boost
                importance = metadata.get("importance", 0.5)

                # Temporal decay (exponential, half-life = 7 days)
                timestamp = metadata.get("timestamp", now)
                age_days = (now - timestamp) / 86400
                recency_score = 2 ** (-age_days / 7)

                # Access frequency boost (logarithmic)
                access_count = metadata.get("access_count", 0)
                frequency_boost = min(0.2, 0.05 * (access_count ** 0.5))

                # Combined score
                final_score = (
                    semantic_score * (1 - recency_weight)
                    + recency_score * recency_weight
                    + importance * 0.15
                    + frequency_boost
                )

                scored_results.append({
                    "content": doc,
                    "score": round(final_score, 4),
                    "semantic_score": round(semantic_score, 4),
                    "recency_score": round(recency_score, 4),
                    "importance": importance,
                    "memory_type": metadata.get("memory_type", "unknown"),
                    "source": metadata.get("source", "unknown"),
                    "tags": json.loads(metadata.get("tags", "[]")),
                    "timestamp": timestamp,
                    "created_date": metadata.get("created_date", ""),
                    "id": results["ids"][0][i] if results["ids"] else "",
                })

            # Sort by final score
            scored_results.sort(key=lambda x: x["score"], reverse=True)

            # Update access counts for returned results
            for r in scored_results[:n_results]:
                self._bump_access(r["id"], memory_type)

            return scored_results[:n_results]

        except Exception as e:
            logger.error(f"[VectorMemory] Search error: {e}")
            return []

    def _search_fallback(self, query: str, n_results: int,
                         memory_type: Optional[str],
                         min_importance: float) -> List[Dict[str, Any]]:
        """Simple keyword-based fallback search."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        results = []

        for mem in self._fallback_store:
            if memory_type and mem.get("memory_type") != memory_type:
                continue
            if mem.get("importance", 0) < min_importance:
                continue

            content_lower = mem["content"].lower()
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)

            if overlap > 0 or query_lower in content_lower:
                keyword_score = overlap / max(len(query_words), 1)
                if query_lower in content_lower:
                    keyword_score += 0.5

                results.append({
                    "content": mem["content"],
                    "score": round(min(1.0, keyword_score), 4),
                    "importance": mem.get("importance", 0.5),
                    "memory_type": mem.get("memory_type", "unknown"),
                    "source": mem.get("source", "unknown"),
                    "tags": json.loads(mem.get("tags", "[]")) if isinstance(mem.get("tags"), str) else mem.get("tags", []),
                    "id": mem.get("id", ""),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n_results]

    def _bump_access(self, mem_id: str, memory_type: Optional[str] = None):
        """Increment access count for gravity indexing."""
        if not CHROMADB_OK or not mem_id:
            return
        try:
            collection = self._collections.get(memory_type or "all")
            if collection is None:
                return
            result = collection.get(ids=[mem_id])
            if result and result["metadatas"]:
                meta = result["metadatas"][0]
                meta["access_count"] = meta.get("access_count", 0) + 1
                meta["last_accessed"] = time.time()
                collection.update(ids=[mem_id], metadatas=[meta])
        except Exception:
            pass

    def consolidate(self, older_than_days: int = 30, min_entries: int = 5) -> int:
        """
        Consolidate old memories into summaries.
        Groups similar old memories and creates summary entries.

        Returns number of consolidated entries.
        """
        if not CHROMADB_OK:
            return 0

        cutoff = time.time() - (older_than_days * 86400)
        consolidated = 0

        try:
            for mem_type in self.MEMORY_TYPES:
                collection = self._collections.get(mem_type)
                if collection is None or collection.count() < min_entries:
                    continue

                # Get old, low-importance memories
                results = collection.get(
                    where={
                        "$and": [
                            {"timestamp": {"$lt": cutoff}},
                            {"importance": {"$lt": 0.3}},
                        ]
                    }
                )

                if not results or not results["documents"]:
                    continue

                # Group into chunks and summarize
                docs = results["documents"]
                ids_to_remove = results["ids"]

                if len(docs) < min_entries:
                    continue

                # Create summary
                chunk_size = 10
                for i in range(0, len(docs), chunk_size):
                    chunk = docs[i:i + chunk_size]
                    chunk_ids = ids_to_remove[i:i + chunk_size]

                    summary = f"[Consolidated {len(chunk)} {mem_type} memories from before {datetime.fromtimestamp(cutoff).strftime('%Y-%m-%d')}]: "
                    summary += " | ".join(c[:100] for c in chunk)

                    # Store summary
                    self.store(
                        summary[:2000],
                        memory_type="summary",
                        importance=0.4,
                        source="consolidation",
                        tags=["consolidated", mem_type],
                    )

                    # Remove originals
                    collection.delete(ids=chunk_ids)
                    consolidated += len(chunk_ids)

            self._stats["consolidations"] += 1
            logger.info(f"[VectorMemory] Consolidated {consolidated} memories")
            return consolidated

        except Exception as e:
            logger.error(f"[VectorMemory] Consolidation error: {e}")
            return 0

    def get_context_for_query(self, query: str, max_tokens: int = 2000) -> str:
        """
        Get relevant memory context formatted for LLM injection.
        Optimized for token budget.
        """
        memories = self.search(query, n_results=10, recency_weight=0.4)

        if not memories:
            return ""

        context_parts = ["[Relevant memories:]"]
        estimated_tokens = 5

        for mem in memories:
            entry = f"- [{mem['memory_type']}] {mem['content']}"
            entry_tokens = len(entry.split()) * 1.3  # rough estimate

            if estimated_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(entry)
            estimated_tokens += entry_tokens

        return "\n".join(context_parts)

    def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        stats = dict(self._stats)
        stats["chromadb_available"] = CHROMADB_OK
        stats["custom_embeddings"] = self._embedder.uses_custom_embeddings
        stats["initialized"] = self._initialized

        if CHROMADB_OK and self._collections:
            stats["collections"] = {
                name: col.count()
                for name, col in self._collections.items()
            }

        return stats

    def clear(self, memory_type: Optional[str] = None):
        """Clear memories (specific type or all)."""
        if not CHROMADB_OK:
            if memory_type:
                self._fallback_store = [
                    m for m in self._fallback_store
                    if m.get("memory_type") != memory_type
                ]
            else:
                self._fallback_store.clear()
            self._save_fallback()
            return

        try:
            if memory_type and memory_type in self._collections:
                self._client.delete_collection(f"lada_{memory_type}")
                self._collections[memory_type] = self._client.get_or_create_collection(
                    name=f"lada_{memory_type}",
                    metadata={"hnsw:space": "cosine"}
                )
            elif not memory_type:
                for name in list(self._collections.keys()):
                    coll_name = f"lada_{name}" if name != "all" else "lada_all_memories"
                    self._client.delete_collection(coll_name)
                self._init_chromadb()
        except Exception as e:
            logger.error(f"[VectorMemory] Clear error: {e}")


# Singleton
_instance: Optional[VectorMemorySystem] = None

def get_vector_memory(data_dir: str = "data/vector_memory") -> VectorMemorySystem:
    global _instance
    if _instance is None:
        _instance = VectorMemorySystem(data_dir=data_dir)
    return _instance
