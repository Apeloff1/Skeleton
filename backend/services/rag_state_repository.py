"""Canonical Mongo authority for Jeeves RAG product state.

Chroma/vector stores are retrieval projections.  User progress, learning-session
ownership/content, co-coding session ownership/content, and feedback are
canonical product state and therefore commit to Mongo first.

The repository is synchronous to preserve the historical RAGService API. It uses
the backend's single shared lazy PyMongo funnel (core.databases.get_sync_db)
rather than creating another client/pool.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping


class RAGStateError(RuntimeError):
    """Base canonical RAG product-state repository error."""


class RAGStateConflict(RAGStateError):
    """An immutable identity was reused with conflicting ownership/content."""


def _required_text(value: object, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RAGStateError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > max_len:
        raise RAGStateError(f"{field} is too long")
    return normalized


def _utc_iso(value: datetime | str | None = None) -> str:
    if value is None:
        instant = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise RAGStateError("timestamp must be timezone-aware")
        instant = value.astimezone(timezone.utc)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise RAGStateError("timestamp is required")
        try:
            instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RAGStateError("timestamp must be ISO-8601") from exc
        if instant.tzinfo is None or instant.utcoffset() is None:
            # Legacy RAG timestamps were naive UTC. Normalize them explicitly at
            # this migration boundary instead of persisting ambiguous time.
            instant = instant.replace(tzinfo=timezone.utc)
        else:
            instant = instant.astimezone(timezone.utc)
    else:
        raise RAGStateError("timestamp must be datetime, ISO-8601 string, or None")
    return instant.isoformat().replace("+00:00", "Z")


def _safe_mapping(value: Mapping[str, Any] | None, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RAGStateError(f"{field} must be a mapping")
    return copy.deepcopy(dict(value))


class RAGStateRepository:
    """Mongo-backed canonical authority for user-owned RAG product state."""

    LEARNING = "rag_learning_sessions"
    CONCEPTS = "rag_concepts"
    PROGRESS = "rag_user_progress"
    COCODING = "rag_cocoding_context"
    FEEDBACK = "rag_feedback"

    def __init__(self, database: Any | None = None) -> None:
        self._database = database

    @property
    def database(self):
        if self._database is None:
            from core.databases import get_sync_db

            self._database = get_sync_db()
        return self._database

    def _collection(self, name: str):
        return self.database[name]

    @staticmethod
    def _without_native_id(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = copy.deepcopy(dict(row))
        result.pop("_id", None)
        return result

    @staticmethod
    def _assert_identity_match(
        existing: Mapping[str, Any] | None,
        candidate: Mapping[str, Any],
        *,
        immutable_fields: tuple[str, ...],
        identity: str,
    ) -> None:
        if existing is None:
            return
        for field in immutable_fields:
            if existing.get(field) != candidate.get(field):
                raise RAGStateConflict(
                    f"{identity} identity reused with conflicting {field}"
                )

    def ensure_indexes(self) -> None:
        self._collection(self.LEARNING).create_index("session_id", unique=True)
        self._collection(self.LEARNING).create_index(
            [("user_id", 1), ("timestamp", -1)]
        )
        self._collection(self.CONCEPTS).create_index("concept_id", unique=True)
        self._collection(self.CONCEPTS).create_index(
            [("domain", 1), ("name", 1)]
        )
        self._collection(self.PROGRESS).create_index(
            [("user_id", 1), ("domain", 1)],
            unique=True,
        )
        self._collection(self.COCODING).create_index("session_id", unique=True)
        self._collection(self.COCODING).create_index(
            [("user_id", 1), ("timestamp", -1)]
        )
        self._collection(self.FEEDBACK).create_index("feedback_id", unique=True)
        self._collection(self.FEEDBACK).create_index(
            [("user_id", 1), ("timestamp", -1)]
        )

    def put_learning_session(
        self,
        *,
        session_id: str,
        user_id: str,
        topic: str,
        content: str,
        duration_minutes: int,
        mastery_delta: float,
        timestamp: datetime | str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate = {
            "session_id": _required_text(session_id, "session_id"),
            "user_id": _required_text(user_id, "user_id"),
            "topic": _required_text(topic, "topic"),
            "content": str(content),
            "duration_minutes": int(duration_minutes),
            "mastery_delta": float(mastery_delta),
            "timestamp": _utc_iso(timestamp),
            "metadata": _safe_mapping(metadata, "metadata"),
            "authority": "mongo",
            "schema_version": 1,
        }
        coll = self._collection(self.LEARNING)
        existing = self._without_native_id(coll.find_one({"session_id": candidate["session_id"]}))
        self._assert_identity_match(
            existing,
            candidate,
            immutable_fields=("user_id", "topic", "content"),
            identity="learning session",
        )
        if existing is not None:
            return existing
        coll.insert_one(copy.deepcopy(candidate))
        return copy.deepcopy(candidate)

    def list_learning_sessions(
        self,
        user_id: str,
        *,
        topic: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        user = _required_text(user_id, "user_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise RAGStateError("limit must be between 1 and 200")
        query: dict[str, Any] = {"user_id": user}
        if topic is not None:
            query["topic"] = _required_text(topic, "topic")
        cursor = self._collection(self.LEARNING).find(query).sort("timestamp", -1).limit(limit)
        return [
            self._without_native_id(row) or {}
            for row in cursor
        ]

    def put_concept(
        self,
        *,
        concept_id: str,
        name: str,
        explanation: str,
        examples: list[str],
        domain: str,
        difficulty: float,
        timestamp: datetime | str | None = None,
    ) -> dict[str, Any]:
        candidate = {
            "concept_id": _required_text(concept_id, "concept_id"),
            "name": _required_text(name, "name"),
            "explanation": _required_text(
                explanation,
                "explanation",
                max_len=100_000,
            ),
            "examples": [str(item) for item in examples],
            "domain": _required_text(domain, "domain"),
            "difficulty": float(difficulty),
            "timestamp": _utc_iso(timestamp),
            "authority": "mongo",
            "schema_version": 1,
        }
        if not 0.0 <= candidate["difficulty"] <= 1.0:
            raise RAGStateError("difficulty must be between 0 and 1")
        coll = self._collection(self.CONCEPTS)
        existing = self._without_native_id(
            coll.find_one({"concept_id": candidate["concept_id"]})
        )
        self._assert_identity_match(
            existing,
            candidate,
            immutable_fields=(
                "name",
                "explanation",
                "examples",
                "domain",
                "difficulty",
            ),
            identity="concept",
        )
        if existing is not None:
            return existing
        coll.insert_one(copy.deepcopy(candidate))
        return copy.deepcopy(candidate)

    def get_concept(self, concept_id: str) -> dict[str, Any] | None:
        concept = _required_text(concept_id, "concept_id")
        row = self._collection(self.CONCEPTS).find_one(
            {"concept_id": concept}
        )
        return self._without_native_id(row)

    def list_concepts(
        self,
        *,
        domain: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
            raise RAGStateError("limit must be between 1 and 5000")
        query: dict[str, Any] = {}
        if domain is not None:
            query["domain"] = _required_text(domain, "domain")
        cursor = self._collection(self.CONCEPTS).find(query)
        if hasattr(cursor, "sort"):
            cursor = cursor.sort("name", 1)
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(limit)
        return [
            self._without_native_id(row) or {}
            for row in cursor
        ][:limit]

    def upsert_user_progress(
        self,
        *,
        user_id: str,
        domain: str,
        mastery_level: float,
        concepts_learned: list[str],
        total_hours: float,
        updated_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        user = _required_text(user_id, "user_id")
        normalized_domain = _required_text(domain, "domain")
        concepts = tuple(
            dict.fromkeys(_required_text(item, "concept") for item in concepts_learned)
        )
        row = {
            "progress_id": f"{user}:{normalized_domain}",
            "user_id": user,
            "domain": normalized_domain,
            "mastery_level": float(mastery_level),
            "concepts_learned": list(concepts),
            "concept_count": len(concepts),
            "total_hours": float(total_hours),
            "updated_at": _utc_iso(updated_at),
            "authority": "mongo",
            "schema_version": 1,
        }
        self._collection(self.PROGRESS).replace_one(
            {"user_id": user, "domain": normalized_domain},
            copy.deepcopy(row),
            upsert=True,
        )
        return copy.deepcopy(row)

    def get_user_progress(self, user_id: str) -> dict[str, dict[str, Any]]:
        user = _required_text(user_id, "user_id")
        rows = self._collection(self.PROGRESS).find({"user_id": user})
        result: dict[str, dict[str, Any]] = {}
        for raw in rows:
            row = self._without_native_id(raw) or {}
            domain = str(row["domain"])
            result[domain] = row
        return result

    def put_cocoding_context(
        self,
        *,
        session_id: str,
        user_id: str,
        pipeline: str,
        context: str,
        code_snippets: list[str],
        decisions: list[str],
        timestamp: datetime | str | None = None,
    ) -> dict[str, Any]:
        candidate = {
            "session_id": _required_text(session_id, "session_id"),
            "user_id": _required_text(user_id, "user_id"),
            "pipeline": _required_text(pipeline, "pipeline"),
            "context": str(context),
            "code_snippets": [str(item) for item in code_snippets],
            "decisions": [str(item) for item in decisions],
            "timestamp": _utc_iso(timestamp),
            "authority": "mongo",
            "schema_version": 1,
        }
        coll = self._collection(self.COCODING)
        existing = self._without_native_id(coll.find_one({"session_id": candidate["session_id"]}))
        self._assert_identity_match(
            existing,
            candidate,
            immutable_fields=("user_id", "pipeline"),
            identity="co-coding session",
        )
        coll.replace_one(
            {"session_id": candidate["session_id"]},
            copy.deepcopy(candidate),
            upsert=True,
        )
        return copy.deepcopy(candidate)

    def get_cocoding_context(
        self,
        session_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any] | None:
        session = _required_text(session_id, "session_id")
        user = _required_text(user_id, "user_id")
        row = self._collection(self.COCODING).find_one(
            {"session_id": session, "user_id": user}
        )
        return self._without_native_id(row)

    def list_cocoding_context(
        self,
        user_id: str,
        *,
        pipeline: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        user = _required_text(user_id, "user_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise RAGStateError("limit must be between 1 and 200")
        query: dict[str, Any] = {"user_id": user}
        if pipeline is not None:
            query["pipeline"] = _required_text(pipeline, "pipeline")
        cursor = self._collection(self.COCODING).find(query).sort("timestamp", -1).limit(limit)
        return [self._without_native_id(row) or {} for row in cursor]

    def put_feedback(
        self,
        *,
        feedback_id: str,
        user_id: str,
        feedback_type: str,
        content: str,
        rating: int | None,
        context: Mapping[str, Any] | None = None,
        timestamp: datetime | str | None = None,
    ) -> dict[str, Any]:
        candidate = {
            "feedback_id": _required_text(feedback_id, "feedback_id"),
            "user_id": _required_text(user_id, "user_id"),
            "feedback_type": _required_text(feedback_type, "feedback_type"),
            "content": str(content),
            "rating": rating,
            "context": _safe_mapping(context, "context"),
            "timestamp": _utc_iso(timestamp),
            "authority": "mongo",
            "schema_version": 1,
        }
        coll = self._collection(self.FEEDBACK)
        existing = self._without_native_id(coll.find_one({"feedback_id": candidate["feedback_id"]}))
        self._assert_identity_match(
            existing,
            candidate,
            immutable_fields=("user_id", "feedback_type", "content"),
            identity="feedback",
        )
        if existing is not None:
            return existing
        coll.insert_one(copy.deepcopy(candidate))
        return copy.deepcopy(candidate)

    def projection_inventory(self) -> dict[str, list[dict[str, Any]]]:
        """Return canonical rows eligible to rebuild semantic projections."""
        return {
            "learning_sessions": [
                self._without_native_id(row) or {}
                for row in self._collection(self.LEARNING).find({})
            ],
            "concepts": [
                self._without_native_id(row) or {}
                for row in self._collection(self.CONCEPTS).find({})
            ],
            "cocoding_context": [
                self._without_native_id(row) or {}
                for row in self._collection(self.COCODING).find({})
            ],
            "feedback": [
                self._without_native_id(row) or {}
                for row in self._collection(self.FEEDBACK).find({})
            ],
        }

    def stats(self) -> dict[str, int]:
        return {
            "learning_sessions": int(
                self._collection(self.LEARNING).count_documents({})
            ),
            "concepts": int(
                self._collection(self.CONCEPTS).count_documents({})
            ),
            "user_progress": int(
                self._collection(self.PROGRESS).count_documents({})
            ),
            "cocoding_context": int(
                self._collection(self.COCODING).count_documents({})
            ),
            "feedback": int(
                self._collection(self.FEEDBACK).count_documents({})
            ),
        }


__all__ = [
    "RAGStateConflict",
    "RAGStateError",
    "RAGStateRepository",
]
