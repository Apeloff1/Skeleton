"""RAG stores — TF-IDF + ChromaDB — split from the memory monolith (v16.2)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import RagUnavailableError, RagQueryError

from .types import MemoryChunk, MemoryQueryResult
from .store import MemoryStore

# =============================================================================
# RAG — RETRIEVAL-AUGMENTED GENERATION
# =============================================================================

class InMemoryTFIDFStore(MemoryStore):
    """
    Fully implemented in-memory TF-IDF vector store.
    No external dependencies. Deterministic. Testable.
    """

    def __init__(self) -> None:
        self._chunks: Dict[str, MemoryChunk] = {}
        self._doc_freq: Dict[str, int] = defaultdict(int)
        self._total_docs: int = 0

    def _tokenize(self, text: str) -> List[str]:
        """Simple but effective tokenisation."""
        return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())

    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Term frequency with log normalisation."""
        freq: Dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        max_freq = max(freq.values()) if freq else 1
        return {t: 0.5 + 0.5 * (f / max_freq) for t, f in freq.items()}

    def _compute_idf(self) -> Dict[str, float]:
        """Inverse document frequency."""
        return {
            t: math.log((self._total_docs + 1) / (df + 1)) + 1
            for t, df in self._doc_freq.items()
        }

    def _vectorise(self, text: str, idf: Dict[str, float]) -> Dict[str, float]:
        """TF-IDF vector as sparse dict."""
        tokens = self._tokenize(text)
        tf = self._compute_tf(tokens)
        return {t: tf.get(t, 0) * idf.get(t, 0) for t in set(tokens)}

    def _cosine_similarity(
        self, v1: Dict[str, float], v2: Dict[str, float]
    ) -> float:
        """Cosine similarity between two sparse vectors."""
        dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) & set(v2))
        norm1 = math.sqrt(sum(v * v for v in v1.values()))
        norm2 = math.sqrt(sum(v * v for v in v2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def add(self, chunk: MemoryChunk) -> None:
        if not isinstance(chunk, MemoryChunk):
            raise TypeError("chunk must be MemoryChunk")

        previous = self._chunks.get(chunk.id)
        if previous is not None:
            for token in set(self._tokenize(previous.text)):
                self._doc_freq[token] -= 1
                if self._doc_freq[token] <= 0:
                    del self._doc_freq[token]
        else:
            self._total_docs += 1

        self._chunks[chunk.id] = chunk
        for token in set(self._tokenize(chunk.text)):
            self._doc_freq[token] += 1

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
            raise TypeError("min_score must be numeric")
        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a mapping")
        if top_k == 0 or not self._chunks:
            return []

        idf = self._compute_idf()
        query_vec = self._vectorise(query_text, idf)

        results: List[Tuple[float, MemoryChunk]] = []
        for chunk in self._chunks.values():
            # Metadata filtering
            if metadata_filter:
                skip = False
                for k, v in metadata_filter.items():
                    if chunk.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            chunk_vec = self._vectorise(chunk.text, idf)
            score = self._cosine_similarity(query_vec, chunk_vec)
            if score >= min_score:
                results.append((score, chunk))

        results.sort(key=lambda item: (-item[0], item[1].id))
        return [
            MemoryQueryResult(chunk=chunk, score=score, rank=i + 1)
            for i, (score, chunk) in enumerate(results[:top_k])
        ]

    def query_scoped(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        scope: Dict[str, str],
    ) -> List[MemoryQueryResult]:
        """Apply exact metadata scope before TF-IDF scoring."""
        if not isinstance(scope, dict) or not scope:
            raise ValueError("scope must be a non-empty mapping")
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in scope.items()
        ):
            raise ValueError("scope keys and values must be non-empty strings")
        return self.query(
            query_text,
            top_k=top_k,
            metadata_filter=dict(scope),
        )

    def delete(self, chunk_id: str) -> bool:
        if chunk_id not in self._chunks:
            return False
        chunk = self._chunks.pop(chunk_id)
        tokens = set(self._tokenize(chunk.text))
        for t in tokens:
            self._doc_freq[t] -= 1
            if self._doc_freq[t] <= 0:
                del self._doc_freq[t]
        self._total_docs -= 1
        return True

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "rag",
            "backend": "in_memory_tfidf",
            "chunks": len(self._chunks),
            "vocabulary": len(self._doc_freq),
            "status": "healthy",
        }


class ChromaDBStore(MemoryStore):
    """
    ChromaDB-backed store with graceful fallback to in-memory.
    Attempts import; if unavailable, raises RagUnavailableError.
    """

    def __init__(self, collection_name: str = "skeleton_memory") -> None:
        self._collection_name = collection_name
        self._fallback = InMemoryTFIDFStore()
        self._client: Any = None
        self._collection: Any = None
        self._available = False
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            self._client = chromadb.Client()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
        except ImportError:
            self._available = False
        except Exception as exc:
            raise RagUnavailableError(
                "ChromaDB initialisation failed",
                context={"exception": str(exc)},
            ) from exc

    def add(self, chunk: MemoryChunk) -> None:
        if self._available and self._collection:
            self._collection.add(
                ids=[chunk.id],
                documents=[chunk.text],
                metadatas=[chunk.metadata],
                embeddings=[chunk.embedding] if chunk.embedding else None,
            )
        else:
            self._fallback.add(chunk)

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if not isinstance(query_text, str) or not query_text.strip():
            raise ValueError("query is required")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if isinstance(min_score, bool) or not isinstance(min_score, (int, float)) or not 0.0 <= float(min_score) <= 1.0:
            raise ValueError("min_score must be in [0, 1]")
        if self._available and self._collection:
            try:
                results = self._collection.query(
                    query_texts=[query_text],
                    n_results=top_k,
                    where=metadata_filter,
                )
            except Exception as exc:
                raise RagQueryError(
                    f"ChromaDB query failed: {exc}",
                    context={"query": query_text, "top_k": top_k},
                ) from exc
            ids = results.get("ids") if isinstance(results, dict) else None
            distances = results.get("distances") if isinstance(results, dict) else None
            documents = results.get("documents") if isinstance(results, dict) else None
            metadatas = results.get("metadatas") if isinstance(results, dict) else None
            if not isinstance(ids, list) or not ids or not isinstance(ids[0], list):
                raise RagQueryError("query ids are required", context={"query": query_text})
            row = ids[0]
            if (
                not isinstance(distances, list)
                or not distances
                or not isinstance(distances[0], list)
                or len(distances[0]) != len(row)
            ):
                raise RagQueryError("query distances are required", context={"query": query_text})
            if not isinstance(documents, list) or not documents or not isinstance(documents[0], list) or len(documents[0]) != len(row):
                raise RagQueryError("query documents are required", context={"query": query_text})
            if not isinstance(metadatas, list) or not metadatas or not isinstance(metadatas[0], list) or len(metadatas[0]) != len(row):
                raise RagQueryError("query metadata is required", context={"query": query_text})
            memory_results: List[MemoryQueryResult] = []
            for i, chunk_id in enumerate(row):
                distance = distances[0][i]
                if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(float(distance)):
                    raise RagQueryError("query distance must be finite", context={"query": query_text})
                similarity = 1.0 - float(distance)
                if similarity >= min_score:
                    chunk = MemoryChunk(
                        id=chunk_id,
                        text=documents[0][i],
                        metadata=metadatas[0][i],
                        source_tier="rag",
                        confidence=similarity,
                    )
                    memory_results.append(
                        MemoryQueryResult(chunk=chunk, score=similarity, rank=i + 1)
                    )
            return memory_results
        return self._fallback.query(
            query_text, top_k=top_k, metadata_filter=metadata_filter, min_score=min_score
        )

    def query_scoped(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        scope: Dict[str, str],
    ) -> List[MemoryQueryResult]:
        """Apply Chroma/fallback metadata scope before nearest-neighbor ranking."""
        if not isinstance(scope, dict) or not scope:
            raise ValueError("scope must be a non-empty mapping")
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in scope.items()
        ):
            raise ValueError("scope keys and values must be non-empty strings")
        return self.query(
            query_text,
            top_k=top_k,
            metadata_filter=dict(scope),
        )

    def delete(self, chunk_id: str) -> bool:
        if self._available and self._collection:
            try:
                self._collection.delete(ids=[chunk_id])
                return True
            except Exception:
                return False
        else:
            return self._fallback.delete(chunk_id)

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "rag",
            "backend": "chromadb" if self._available else "in_memory_tfidf_fallback",
            "available": self._available,
            "fallback_health": self._fallback.health(),
            "status": "healthy" if self._available else "degraded",
        }
