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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .rag_state_repository import RAGStateConflict, RAGStateRepository

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
    
    # Chroma collections are retrieval projections only. Structured user
    # progress is intentionally absent: it is canonical Mongo state.
    PROJECTION_COLLECTIONS = [
        "learning_sessions",
        "concepts",
        "cocoding_context",
        "feedback",
    ]
    COLLECTIONS = PROJECTION_COLLECTIONS

    def __init__(self, state_repository: RAGStateRepository | None = None):
        self.client = get_chroma_client()
        self.state = state_repository or RAGStateRepository()
        self._projection_failures = 0
        self._init_collections()
    
    def _init_collections(self):
        """Initialize all collections."""
        global _collections
        for name in self.COLLECTIONS:
            full_name = f"jeeves_{name}"
            _collections[full_name] = self.client.get_or_create_collection(
                name=full_name,
                metadata={"description": f"Jeeves {name} projection"}
            )
    
    def _get_collection(self, name: str):
        """Get a rebuildable projection collection by name."""
        full_name = f"jeeves_{name}"
        if full_name not in _collections:
            _collections[full_name] = self.client.get_or_create_collection(
                name=full_name,
                metadata={"description": f"Jeeves {name} projection"}
            )
        return _collections[full_name]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _projection_metadata(values: Dict[str, Any]) -> Dict[str, Any]:
        """Keep Chroma metadata projection-safe and payload-light."""
        allowed = (str, int, float, bool)
        projected: Dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, allowed):
                projected[str(key)] = value
            else:
                projected[str(key)] = json.dumps(
                    value,
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
        return projected

    def _project_add(
        self,
        collection_name: str,
        *,
        document: str,
        metadata: Dict[str, Any],
        record_id: str,
    ) -> bool:
        """Best-effort projection after canonical state has committed."""
        try:
            collection = self._get_collection(collection_name)
            try:
                collection.delete(ids=[record_id])
            except Exception:
                pass
            collection.add(
                documents=[document],
                metadatas=[self._projection_metadata(metadata)],
                ids=[record_id],
            )
            return True
        except Exception:
            self._projection_failures += 1
            return False

    @staticmethod
    def _canonical_concept_content(row: Dict[str, Any]) -> str:
        content = f"{row.get('name', '')}\n\n{row.get('explanation', '')}\n\nExamples:\n"
        content += "\n".join(f"- {item}" for item in row.get("examples", []))
        return content

    @staticmethod
    def _canonical_cocoding_content(row: Dict[str, Any]) -> str:
        content = f"Context: {row.get('context', '')}\n\nCode:\n"
        content += "\n---\n".join(str(item) for item in row.get("code_snippets", []))
        content += "\n\nDecisions:\n"
        content += "\n".join(f"- {item}" for item in row.get("decisions", []))
        return content
    
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
        """Commit a learning session to Mongo, then project it to Chroma."""
        timestamp = self._utc_now()
        session_id = hashlib.sha256(
            f"{user_id}:{topic}:{timestamp}".encode()
        ).hexdigest()[:16]

        row = self.state.put_learning_session(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            content=content,
            duration_minutes=duration_minutes,
            mastery_delta=mastery_delta,
            timestamp=timestamp,
            metadata=metadata,
        )
        self._project_add(
            "learning_sessions",
            document=row["content"],
            metadata={
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "topic": row["topic"],
                "duration_minutes": row["duration_minutes"],
                "mastery_delta": row["mastery_delta"],
                "timestamp": row["timestamp"],
                "authority": "mongo",
            },
            record_id=row["session_id"],
        )
        return row["session_id"]

    def get_user_sessions(
        self,
        user_id: str,
        topic: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Read canonical learning sessions from Mongo.

        user_id='*' is retained only as a projection-search compatibility path
        for the legacy generic memory search helper. It is retrieval, not an
        ownership/authority read.
        """
        if user_id != "*":
            rows = self.state.list_learning_sessions(
                user_id,
                topic=topic,
                limit=limit,
            )
            return [
                {
                    "content": row["content"],
                    "metadata": {
                        "session_id": row["session_id"],
                        "user_id": row["user_id"],
                        "topic": row["topic"],
                        "duration_minutes": row["duration_minutes"],
                        "mastery_delta": row["mastery_delta"],
                        "timestamp": row["timestamp"],
                        "authority": "mongo",
                        **dict(row.get("metadata") or {}),
                    },
                }
                for row in rows
            ]

        collection = self._get_collection("learning_sessions")
        results = collection.query(
            query_texts=["learning session"],
            n_results=limit,
        )
        sessions = []
        if results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results.get("metadatas", [[]])[0][i] or {}
                sessions.append({"content": doc, "metadata": meta})
        return sessions

    def store_concept(
        self,
        concept_id: str,
        name: str,
        explanation: str,
        examples: List[str],
        domain: str,
        difficulty: float = 0.5
    ) -> str:
        """Commit a concept to Mongo before projecting it to Chroma."""
        row = self.state.put_concept(
            concept_id=concept_id,
            name=name,
            explanation=explanation,
            examples=examples,
            domain=domain,
            difficulty=difficulty,
            timestamp=self._utc_now(),
        )
        self._project_add(
            "concepts",
            document=self._canonical_concept_content(row),
            metadata={
                "concept_id": row["concept_id"],
                "name": row["name"],
                "domain": row["domain"],
                "difficulty": row["difficulty"],
                "example_count": len(row["examples"]),
                "timestamp": row["timestamp"],
                "authority": "mongo",
            },
            record_id=row["concept_id"],
        )
        return row["concept_id"]

    def search_concepts(
        self,
        query: str,
        domain: Optional[str] = None,
        max_difficulty: Optional[float] = None,
        limit: int = 5
    ) -> List[Dict]:
        """Retrieve via Chroma but validate concept hits against Mongo authority."""
        collection = self._get_collection("concepts")

        where_filter = {}
        if domain:
            where_filter["domain"] = domain

        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter if where_filter else None,
            )
        except Exception:
            results = {}

        ids = (results.get("ids") or [[]])[0] if results else []
        distances = (results.get("distances") or [[]])[0] if results else []
        concepts: List[Dict] = []
        for i, projected_id in enumerate(ids):
            canonical = self.state.get_concept(str(projected_id))
            if canonical is None:
                continue
            if domain and canonical["domain"] != domain:
                continue
            if (
                max_difficulty is not None
                and canonical["difficulty"] > max_difficulty
            ):
                continue
            concepts.append(
                {
                    "content": self._canonical_concept_content(canonical),
                    "metadata": {
                        "concept_id": canonical["concept_id"],
                        "name": canonical["name"],
                        "domain": canonical["domain"],
                        "difficulty": canonical["difficulty"],
                        "example_count": len(canonical["examples"]),
                        "timestamp": canonical["timestamp"],
                        "authority": "mongo",
                    },
                    "relevance": (
                        1 - distances[i]
                        if i < len(distances)
                        else 1.0
                    ),
                }
            )
            if len(concepts) >= limit:
                break

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
        """Update authoritative user progress in Mongo only."""
        row = self.state.upsert_user_progress(
            user_id=user_id,
            domain=domain,
            mastery_level=mastery_level,
            concepts_learned=concepts_learned,
            total_hours=total_hours,
            updated_at=self._utc_now(),
        )
        return row["progress_id"]

    def get_user_progress(self, user_id: str) -> Dict[str, Any]:
        """Get authoritative user progress from Mongo."""
        rows = self.state.get_user_progress(user_id)
        progress: Dict[str, Any] = {}
        for domain, row in rows.items():
            progress[domain] = {
                "data": {
                    "mastery_level": row["mastery_level"],
                    "concepts_learned": list(row["concepts_learned"]),
                    "total_hours": row["total_hours"],
                },
                "metadata": {
                    "progress_id": row["progress_id"],
                    "user_id": row["user_id"],
                    "domain": row["domain"],
                    "mastery_level": row["mastery_level"],
                    "concept_count": row["concept_count"],
                    "total_hours": row["total_hours"],
                    "updated_at": row["updated_at"],
                    "authority": "mongo",
                },
            }
        return progress

    def store_cocoding_context(
        self,
        session_id: str,
        user_id: str,
        pipeline: str,
        context: str,
        code_snippets: List[str],
        decisions: List[str]
    ) -> str:
        """Commit co-coding state to Mongo before semantic projection."""
        row = self.state.put_cocoding_context(
            session_id=session_id,
            user_id=user_id,
            pipeline=pipeline,
            context=context,
            code_snippets=code_snippets,
            decisions=decisions,
            timestamp=self._utc_now(),
        )
        self._project_add(
            "cocoding_context",
            document=self._canonical_cocoding_content(row),
            metadata={
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "pipeline": row["pipeline"],
                "snippet_count": len(row["code_snippets"]),
                "decision_count": len(row["decisions"]),
                "timestamp": row["timestamp"],
                "authority": "mongo",
            },
            record_id=row["session_id"],
        )
        return row["session_id"]

    def get_relevant_context(
        self,
        user_id: str,
        query: str,
        pipeline: Optional[str] = None,
        limit: int = 3
    ) -> List[Dict]:
        """Retrieve via Chroma but validate every hit against Mongo authority."""
        collection = self._get_collection("cocoding_context")
        where_filter = {"user_id": user_id}
        if pipeline:
            where_filter["pipeline"] = pipeline

        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter,
            )
        except Exception:
            results = {}

        contexts: List[Dict] = []
        ids = (results.get("ids") or [[]])[0] if results else []
        distances = (results.get("distances") or [[]])[0] if results else []

        for i, projected_id in enumerate(ids):
            canonical = self.state.get_cocoding_context(
                str(projected_id),
                user_id=user_id,
            )
            if canonical is None:
                continue
            if pipeline and canonical.get("pipeline") != pipeline:
                continue
            contexts.append({
                "content": self._canonical_cocoding_content(canonical),
                "metadata": {
                    "session_id": canonical["session_id"],
                    "user_id": canonical["user_id"],
                    "pipeline": canonical["pipeline"],
                    "timestamp": canonical["timestamp"],
                    "authority": "mongo",
                },
                "relevance": 1 - (distances[i] if i < len(distances) else 0),
            })

        if contexts:
            return contexts[:limit]

        rows = self.state.list_cocoding_context(
            user_id,
            pipeline=pipeline,
            limit=limit,
        )
        return [
            {
                "content": self._canonical_cocoding_content(row),
                "metadata": {
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "pipeline": row["pipeline"],
                    "timestamp": row["timestamp"],
                    "authority": "mongo",
                },
                "relevance": 0.0,
            }
            for row in rows
        ]

    def store_feedback(
        self,
        user_id: str,
        feedback_type: str,
        content: str,
        rating: Optional[int] = None,
        context: Optional[Dict] = None
    ) -> str:
        """Commit feedback to Mongo before semantic projection."""
        timestamp = self._utc_now()
        feedback_id = hashlib.sha256(
            f"{user_id}:{feedback_type}:{timestamp}".encode()
        ).hexdigest()[:16]
        row = self.state.put_feedback(
            feedback_id=feedback_id,
            user_id=user_id,
            feedback_type=feedback_type,
            content=content,
            rating=rating,
            context=context,
            timestamp=timestamp,
        )
        self._project_add(
            "feedback",
            document=row["content"],
            metadata={
                "feedback_id": row["feedback_id"],
                "user_id": row["user_id"],
                "feedback_type": row["feedback_type"],
                "rating": row["rating"],
                "timestamp": row["timestamp"],
                "authority": "mongo",
            },
            record_id=row["feedback_id"],
        )
        return row["feedback_id"]

    def migrate_legacy_chroma_state(self) -> Dict[str, int]:
        """Idempotently import legacy Chroma-owned product state into Mongo."""
        migrated = {
            "learning_sessions": 0,
            "concepts": 0,
            "user_progress": 0,
            "cocoding_context": 0,
            "feedback": 0,
            "conflicts": 0,
            "skipped": 0,
        }

        def legacy_rows(name: str):
            try:
                raw = self.client.get_or_create_collection(
                    name=f"jeeves_{name}",
                    metadata={"description": f"legacy Jeeves {name}"},
                ).get()
            except Exception:
                return ()
            ids = raw.get("ids") or []
            docs = raw.get("documents") or []
            metas = raw.get("metadatas") or []
            return tuple(
                (
                    str(ids[i]),
                    str(docs[i]) if i < len(docs) and docs[i] is not None else "",
                    dict(metas[i] or {}) if i < len(metas) else {},
                )
                for i in range(len(ids))
            )

        for record_id, document, meta in legacy_rows("learning_sessions"):
            try:
                self.state.put_learning_session(
                    session_id=record_id,
                    user_id=str(meta.get("user_id") or "unknown"),
                    topic=str(meta.get("topic") or "general"),
                    content=document,
                    duration_minutes=int(meta.get("duration_minutes") or 0),
                    mastery_delta=float(meta.get("mastery_delta") or 0.0),
                    timestamp=str(meta.get("timestamp") or self._utc_now()),
                    metadata={"migrated_from": "chroma"},
                )
                migrated["learning_sessions"] += 1
            except RAGStateConflict:
                migrated["conflicts"] += 1
            except Exception:
                migrated["skipped"] += 1

        for record_id, document, meta in legacy_rows("concepts"):
            try:
                name = str(meta.get("name") or "").strip()
                domain = str(meta.get("domain") or "").strip()
                if not name or not domain:
                    migrated["skipped"] += 1
                    continue
                explanation = document
                marker = "\n\nExamples:\n"
                if document.startswith(name + "\n\n"):
                    explanation = document[len(name) + 2 :]
                if marker in explanation:
                    explanation = explanation.split(marker, 1)[0]
                self.state.put_concept(
                    concept_id=record_id,
                    name=name,
                    explanation=explanation or name,
                    examples=list(meta.get("examples") or []),
                    domain=domain,
                    difficulty=float(meta.get("difficulty", 0.5)),
                    timestamp=str(meta.get("timestamp") or self._utc_now()),
                )
                migrated["concepts"] += 1
            except RAGStateConflict:
                migrated["conflicts"] += 1
            except Exception:
                migrated["skipped"] += 1

        for _, document, meta in legacy_rows("user_progress"):
            try:
                payload = json.loads(document) if document.startswith("{") else {}
                user_id = str(meta.get("user_id") or "")
                domain = str(meta.get("domain") or "")
                if not user_id or not domain:
                    migrated["skipped"] += 1
                    continue
                self.state.upsert_user_progress(
                    user_id=user_id,
                    domain=domain,
                    mastery_level=float(
                        payload.get("mastery_level", meta.get("mastery_level", 0.0))
                    ),
                    concepts_learned=list(payload.get("concepts_learned") or []),
                    total_hours=float(
                        payload.get("total_hours", meta.get("total_hours", 0.0))
                    ),
                    updated_at=str(meta.get("updated_at") or self._utc_now()),
                )
                migrated["user_progress"] += 1
            except Exception:
                migrated["skipped"] += 1

        for record_id, document, meta in legacy_rows("cocoding_context"):
            try:
                user_id = str(meta.get("user_id") or "")
                pipeline = str(meta.get("pipeline") or "unknown")
                if not user_id:
                    migrated["skipped"] += 1
                    continue
                self.state.put_cocoding_context(
                    session_id=record_id,
                    user_id=user_id,
                    pipeline=pipeline,
                    context=document,
                    code_snippets=[],
                    decisions=[],
                    timestamp=str(meta.get("timestamp") or self._utc_now()),
                )
                migrated["cocoding_context"] += 1
            except RAGStateConflict:
                migrated["conflicts"] += 1
            except Exception:
                migrated["skipped"] += 1

        for record_id, document, meta in legacy_rows("feedback"):
            try:
                user_id = str(meta.get("user_id") or "")
                feedback_type = str(meta.get("feedback_type") or "general")
                if not user_id:
                    migrated["skipped"] += 1
                    continue
                self.state.put_feedback(
                    feedback_id=record_id,
                    user_id=user_id,
                    feedback_type=feedback_type,
                    content=document,
                    rating=meta.get("rating"),
                    context={"migrated_from": "chroma"},
                    timestamp=str(meta.get("timestamp") or self._utc_now()),
                )
                migrated["feedback"] += 1
            except RAGStateConflict:
                migrated["conflicts"] += 1
            except Exception:
                migrated["skipped"] += 1

        return migrated

    def rebuild_projections_from_mongo(self) -> Dict[str, int]:
        """Rebuild all user-owned semantic projections from canonical Mongo."""
        inventory = self.state.projection_inventory()
        rebuilt = {
            "learning_sessions": 0,
            "concepts": 0,
            "cocoding_context": 0,
            "feedback": 0,
            "failed": 0,
        }

        for row in inventory["learning_sessions"]:
            ok = self._project_add(
                "learning_sessions",
                document=row["content"],
                metadata={
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "topic": row["topic"],
                    "duration_minutes": row["duration_minutes"],
                    "mastery_delta": row["mastery_delta"],
                    "timestamp": row["timestamp"],
                    "authority": "mongo",
                },
                record_id=row["session_id"],
            )
            rebuilt["learning_sessions" if ok else "failed"] += 1

        for row in inventory["concepts"]:
            ok = self._project_add(
                "concepts",
                document=self._canonical_concept_content(row),
                metadata={
                    "concept_id": row["concept_id"],
                    "name": row["name"],
                    "domain": row["domain"],
                    "difficulty": row["difficulty"],
                    "example_count": len(row.get("examples") or []),
                    "timestamp": row["timestamp"],
                    "authority": "mongo",
                },
                record_id=row["concept_id"],
            )
            rebuilt["concepts" if ok else "failed"] += 1

        for row in inventory["cocoding_context"]:
            ok = self._project_add(
                "cocoding_context",
                document=self._canonical_cocoding_content(row),
                metadata={
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "pipeline": row["pipeline"],
                    "snippet_count": len(row.get("code_snippets") or []),
                    "decision_count": len(row.get("decisions") or []),
                    "timestamp": row["timestamp"],
                    "authority": "mongo",
                },
                record_id=row["session_id"],
            )
            rebuilt["cocoding_context" if ok else "failed"] += 1

        for row in inventory["feedback"]:
            ok = self._project_add(
                "feedback",
                document=row["content"],
                metadata={
                    "feedback_id": row["feedback_id"],
                    "user_id": row["user_id"],
                    "feedback_type": row["feedback_type"],
                    "rating": row.get("rating"),
                    "timestamp": row["timestamp"],
                    "authority": "mongo",
                },
                record_id=row["feedback_id"],
            )
            rebuilt["feedback" if ok else "failed"] += 1

        return rebuilt

    def get_stats(self) -> Dict[str, Any]:
        """Expose canonical authority and rebuildable projection statistics."""
        projection_counts: Dict[str, int] = {}
        total_projection_documents = 0
        for name in self.PROJECTION_COLLECTIONS:
            try:
                count = int(self._get_collection(name).count())
            except Exception:
                count = -1
            projection_counts[name] = count
            if count > 0:
                total_projection_documents += count

        authority_counts = self.state.stats()
        return {
            "status": "healthy",
            "authority": {
                "store": "mongo",
                "collections": authority_counts,
                "total_records": sum(authority_counts.values()),
            },
            "projection": {
                "store": "chroma",
                "rebuildable": True,
                "collections": projection_counts,
                "total_documents": total_projection_documents,
                "write_failures": self._projection_failures,
            },
            "collections": projection_counts,
            "total_documents": total_projection_documents,
        }


# =============================================================================
# Global Instance
# =============================================================================

rag_service = RAGService()


# =============================================================================
# Convenience Functions
# =============================================================================

def store_memory(memory_type: str, content: str, metadata: Optional[Dict] = None) -> str:
    """Store a supported memory type without allowing projection-only authority.

    User-owned memory types must commit to their Mongo authority first. Unknown
    types fail closed rather than falling back to a Chroma-only write.
    """
    kind = str(memory_type).strip()
    if not kind:
        raise ValueError("memory_type is required")
    details = dict(metadata or {})

    if kind == "learning_session":
        user_id = str(details.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("learning_session memory requires user_id")
        return rag_service.store_learning_session(
            user_id=user_id,
            topic=str(details.get("topic") or "general"),
            content=content,
            duration_minutes=int(details.get("duration_minutes") or 0),
            mastery_delta=float(details.get("mastery_delta") or 0.0),
            metadata=details.get("metadata"),
        )
    if kind == "concept":
        # Concepts are content/catalog retrieval material, not canonical
        # user-memory authority. Keep this explicit instead of treating an
        # arbitrary unknown memory type as a projection-backed concept.
        return rag_service.store_concept(
            concept_id=str(
                details.get("concept_id")
                or hashlib.sha256(content.encode()).hexdigest()[:8]
            ),
            name=str(details.get("name") or "Unnamed Concept"),
            explanation=content,
            examples=list(details.get("examples") or []),
            domain=str(details.get("domain") or "general"),
            difficulty=float(details.get("difficulty", 0.5)),
        )
    if kind == "feedback":
        user_id = str(details.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("feedback memory requires user_id")
        return rag_service.store_feedback(
            user_id=user_id,
            feedback_type=str(details.get("feedback_type") or "general"),
            content=content,
            rating=details.get("rating"),
            context=details.get("context"),
        )

    raise ValueError(
        f"unsupported memory_type {kind!r}; projection-only generic memory writes are forbidden"
    )


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
