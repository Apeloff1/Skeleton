"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              RAG SERVICE v15.0 - Long-Term Memory for Jeeves                 ║
║                                                                              ║
║  ChromaDB-powered Retrieval-Augmented Generation for:                        ║
║  • Learning session memory                                                   ║
║  • User progress tracking                                                    ║
║  • Concept explanations caching                                              ║
║  • Co-coding context preservation                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Lazy import ChromaDB to handle missing dependency gracefully
_chroma_client = None
_collections: Dict[str, Any] = {}


def get_chroma_client():
    """Get or create ChromaDB client (lazy initialization)."""
    global _chroma_client
    
    if _chroma_client is None:
        try:
            import chromadb
            from chromadb.config import Settings
            
            persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
            
            _chroma_client = chromadb.Client(Settings(
                anonymized_telemetry=False,
                is_persistent=True,
                persist_directory=persist_dir
            ))
        except ImportError:
            # ChromaDB not installed - use mock
            _chroma_client = MockChromaClient()
        except Exception as e:
            print(f"ChromaDB initialization error: {e}")
            _chroma_client = MockChromaClient()
    
    return _chroma_client


class MockChromaClient:
    """Mock ChromaDB client for when ChromaDB is not available."""
    
    def __init__(self):
        self._collections: Dict[str, "MockCollection"] = {}
    
    def get_or_create_collection(self, name: str, **kwargs) -> "MockCollection":
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]
    
    def list_collections(self) -> List[str]:
        return list(self._collections.keys())


class MockCollection:
    """Mock collection for when ChromaDB is not available."""
    
    def __init__(self, name: str):
        self.name = name
        self._documents: List[Dict] = []
    
    def add(self, documents: List[str], metadatas: List[Dict], ids: List[str]):
        for doc, meta, id_ in zip(documents, metadatas, ids):
            self._documents.append({
                "id": id_,
                "document": doc,
                "metadata": meta
            })
    
    def query(self, query_texts: List[str], n_results: int = 5, where: Optional[Dict] = None):
        # Simple mock - return most recent documents
        filtered = self._documents
        if where:
            filtered = [d for d in self._documents 
                       if all(d["metadata"].get(k) == v for k, v in where.items())]
        
        results = filtered[-n_results:]
        return {
            "documents": [[d["document"] for d in results]],
            "metadatas": [[d["metadata"] for d in results]],
            "distances": [[0.1] * len(results)],
            "ids": [[d["id"] for d in results]]
        }
    
    def count(self) -> int:
        return len(self._documents)
    
    def get(self, ids: Optional[List[str]] = None, where: Optional[Dict] = None):
        if ids:
            results = [d for d in self._documents if d["id"] in ids]
        elif where:
            results = [d for d in self._documents 
                      if all(d["metadata"].get(k) == v for k, v in where.items())]
        else:
            results = self._documents
        
        return {
            "documents": [d["document"] for d in results],
            "metadatas": [d["metadata"] for d in results],
            "ids": [d["id"] for d in results]
        }
    
    def delete(self, ids: Optional[List[str]] = None, where: Optional[Dict] = None):
        if ids:
            self._documents = [d for d in self._documents if d["id"] not in ids]
        elif where:
            self._documents = [d for d in self._documents 
                             if not all(d["metadata"].get(k) == v for k, v in where.items())]


# =============================================================================
# RAG Service Class
# =============================================================================

class RAGService:
    """
    RAG Service for Jeeves long-term memory.
    
    Collections:
    - learning_sessions: User learning session history
    - concepts: Concept explanations and examples
    - user_progress: User progress and mastery data
    - cocoding_context: Co-coding session context
    - feedback: User feedback and ratings
    """
    
    COLLECTIONS = [
        "learning_sessions",
        "concepts",
        "user_progress",
        "cocoding_context",
        "feedback"
    ]
    
    def __init__(self):
        self.client = get_chroma_client()
        self._init_collections()
    
    def _init_collections(self):
        """Initialize all collections."""
        global _collections
        for name in self.COLLECTIONS:
            _collections[name] = self.client.get_or_create_collection(
                name=f"jeeves_{name}",
                metadata={"description": f"Jeeves {name} memory"}
            )
    
    def _get_collection(self, name: str):
        """Get a collection by name."""
        full_name = f"jeeves_{name}"
        if full_name not in _collections:
            _collections[full_name] = self.client.get_or_create_collection(
                name=full_name,
                metadata={"description": f"Jeeves {name} memory"}
            )
        return _collections[full_name]
    
    # =========================================================================
    # Learning Sessions
    # =========================================================================
    
    def store_learning_session(
        self,
        user_id: str,
        topic: str,
        content: str,
        duration_minutes: int,
        mastery_delta: float = 0.0,
        metadata: Optional[Dict] = None
    ) -> str:
        """Store a learning session in memory."""
        collection = self._get_collection("learning_sessions")
        
        session_id = hashlib.md5(
            f"{user_id}:{topic}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        full_metadata = {
            "user_id": user_id,
            "topic": topic,
            "duration_minutes": duration_minutes,
            "mastery_delta": mastery_delta,
            "timestamp": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        
        collection.add(
            documents=[content],
            metadatas=[full_metadata],
            ids=[session_id]
        )
        
        return session_id
    
    def get_user_sessions(
        self,
        user_id: str,
        topic: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Retrieve user's learning sessions."""
        collection = self._get_collection("learning_sessions")
        
        where_filter = {"user_id": user_id}
        if topic:
            where_filter["topic"] = topic
        
        results = collection.query(
            query_texts=["learning session"],
            n_results=limit,
            where=where_filter
        )
        
        sessions = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                sessions.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                })
        
        return sessions
    
    # =========================================================================
    # Concepts
    # =========================================================================
    
    def store_concept(
        self,
        concept_id: str,
        name: str,
        explanation: str,
        examples: List[str],
        domain: str,
        difficulty: float = 0.5
    ) -> str:
        """Store a concept explanation."""
        collection = self._get_collection("concepts")
        
        content = f"{name}\n\n{explanation}\n\nExamples:\n" + "\n".join(f"- {e}" for e in examples)
        
        metadata = {
            "concept_id": concept_id,
            "name": name,
            "domain": domain,
            "difficulty": difficulty,
            "example_count": len(examples),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[concept_id]
        )
        
        return concept_id
    
    def search_concepts(
        self,
        query: str,
        domain: Optional[str] = None,
        max_difficulty: Optional[float] = None,
        limit: int = 5
    ) -> List[Dict]:
        """Search for relevant concepts."""
        collection = self._get_collection("concepts")
        
        where_filter = {}
        if domain:
            where_filter["domain"] = domain
        
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_filter if where_filter else None
        )
        
        concepts = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                if max_difficulty and meta.get("difficulty", 0) > max_difficulty:
                    continue
                concepts.append({
                    "content": doc,
                    "metadata": meta,
                    "relevance": 1 - (results["distances"][0][i] if results["distances"] else 0)
                })
        
        return concepts
    
    # =========================================================================
    # User Progress
    # =========================================================================
    
    def update_user_progress(
        self,
        user_id: str,
        domain: str,
        mastery_level: float,
        concepts_learned: List[str],
        total_hours: float
    ) -> str:
        """Update user progress for a domain."""
        collection = self._get_collection("user_progress")
        
        progress_id = f"{user_id}:{domain}"
        
        content = json.dumps({
            "mastery_level": mastery_level,
            "concepts_learned": concepts_learned,
            "total_hours": total_hours
        })
        
        metadata = {
            "user_id": user_id,
            "domain": domain,
            "mastery_level": mastery_level,
            "concept_count": len(concepts_learned),
            "total_hours": total_hours,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Delete existing and add new (upsert)
        try:
            collection.delete(ids=[progress_id])
        except Exception:
            pass
        
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[progress_id]
        )
        
        return progress_id
    
    def get_user_progress(self, user_id: str) -> Dict[str, Any]:
        """Get all progress for a user."""
        collection = self._get_collection("user_progress")
        
        results = collection.get(where={"user_id": user_id})
        
        progress = {}
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                domain = meta.get("domain", "unknown")
                progress[domain] = {
                    "data": json.loads(doc) if doc.startswith("{") else {},
                    "metadata": meta
                }
        
        return progress
    
    # =========================================================================
    # Co-coding Context
    # =========================================================================
    
    def store_cocoding_context(
        self,
        session_id: str,
        user_id: str,
        pipeline: str,
        context: str,
        code_snippets: List[str],
        decisions: List[str]
    ) -> str:
        """Store co-coding session context."""
        collection = self._get_collection("cocoding_context")
        
        content = f"Context: {context}\n\nCode:\n" + "\n---\n".join(code_snippets)
        content += "\n\nDecisions:\n" + "\n".join(f"- {d}" for d in decisions)
        
        metadata = {
            "session_id": session_id,
            "user_id": user_id,
            "pipeline": pipeline,
            "snippet_count": len(code_snippets),
            "decision_count": len(decisions),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[session_id]
        )
        
        return session_id
    
    def get_relevant_context(
        self,
        user_id: str,
        query: str,
        pipeline: Optional[str] = None,
        limit: int = 3
    ) -> List[Dict]:
        """Get relevant co-coding context for a query."""
        collection = self._get_collection("cocoding_context")
        
        where_filter = {"user_id": user_id}
        if pipeline:
            where_filter["pipeline"] = pipeline
        
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_filter
        )
        
        contexts = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                contexts.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "relevance": 1 - (results["distances"][0][i] if results["distances"] else 0)
                })
        
        return contexts
    
    # =========================================================================
    # Feedback
    # =========================================================================
    
    def store_feedback(
        self,
        user_id: str,
        feedback_type: str,
        content: str,
        rating: Optional[int] = None,
        context: Optional[Dict] = None
    ) -> str:
        """Store user feedback."""
        collection = self._get_collection("feedback")
        
        feedback_id = hashlib.md5(
            f"{user_id}:{feedback_type}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        metadata = {
            "user_id": user_id,
            "feedback_type": feedback_type,
            "rating": rating,
            "timestamp": datetime.utcnow().isoformat(),
            **(context or {})
        }
        
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[feedback_id]
        )
        
        return feedback_id
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG service statistics."""
        stats = {
            "collections": {},
            "total_documents": 0,
            "status": "healthy"
        }
        
        for name in self.COLLECTIONS:
            collection = self._get_collection(name)
            count = collection.count()
            stats["collections"][name] = count
            stats["total_documents"] += count
        
        return stats


# =============================================================================
# Global Instance
# =============================================================================

rag_service = RAGService()


# =============================================================================
# Convenience Functions
# =============================================================================

def store_memory(memory_type: str, content: str, metadata: Optional[Dict] = None) -> str:
    """Store a memory of any type."""
    if memory_type == "learning_session":
        return rag_service.store_learning_session(
            user_id=metadata.get("user_id", "unknown"),
            topic=metadata.get("topic", "general"),
            content=content,
            duration_minutes=metadata.get("duration_minutes", 0)
        )
    elif memory_type == "concept":
        return rag_service.store_concept(
            concept_id=metadata.get("concept_id", hashlib.md5(content.encode()).hexdigest()[:8]),
            name=metadata.get("name", "Unnamed Concept"),
            explanation=content,
            examples=metadata.get("examples", []),
            domain=metadata.get("domain", "general")
        )
    elif memory_type == "feedback":
        return rag_service.store_feedback(
            user_id=metadata.get("user_id", "unknown"),
            feedback_type=metadata.get("feedback_type", "general"),
            content=content,
            rating=metadata.get("rating")
        )
    else:
        # Generic storage
        collection = rag_service._get_collection("learning_sessions")
        memory_id = hashlib.md5(content.encode()).hexdigest()[:16]
        collection.add(
            documents=[content],
            metadatas=[{"type": memory_type, **(metadata or {})}],
            ids=[memory_id]
        )
        return memory_id


def search_memory(query: str, memory_type: Optional[str] = None, limit: int = 5) -> List[Dict]:
    """Search memories."""
    if memory_type == "concept":
        return rag_service.search_concepts(query, limit=limit)
    else:
        # Generic search across learning sessions
        return rag_service.get_user_sessions(
            user_id="*",  # All users
            limit=limit
        )


def get_rag_stats() -> Dict[str, Any]:
    """Get RAG service statistics."""
    return rag_service.get_stats()
