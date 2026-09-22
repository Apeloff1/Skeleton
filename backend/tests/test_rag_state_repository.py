from __future__ import annotations

from copy import deepcopy

import pytest

from services.rag_state_repository import (
    RAGStateConflict,
    RAGStateRepository,
)


def _matches(row: dict, query: dict) -> bool:
    return all(row.get(key) == value for key, value in query.items())


class _Cursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = [deepcopy(row) for row in rows]

    def sort(self, key: str, direction: int):
        reverse = direction < 0
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=reverse)
        return self

    def limit(self, limit: int):
        self.rows = self.rows[:limit]
        return self

    def __iter__(self):
        return iter([deepcopy(row) for row in self.rows])


class _Collection:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.indexes: list[tuple] = []

    def create_index(self, spec, **kwargs):
        self.indexes.append((spec, kwargs))
        return str(spec)

    def find_one(self, query: dict):
        for row in self.rows:
            if _matches(row, query):
                return deepcopy(row)
        return None

    def insert_one(self, document: dict):
        self.rows.append(deepcopy(document))
        return object()

    def replace_one(self, query: dict, document: dict, upsert: bool = False):
        for index, row in enumerate(self.rows):
            if _matches(row, query):
                self.rows[index] = deepcopy(document)
                return object()
        if upsert:
            self.rows.append(deepcopy(document))
        return object()

    def find(self, query: dict):
        return _Cursor([row for row in self.rows if _matches(row, query)])

    def count_documents(self, query: dict):
        return sum(1 for row in self.rows if _matches(row, query))


class _Database:
    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}

    def __getitem__(self, name: str) -> _Collection:
        if name not in self.collections:
            self.collections[name] = _Collection()
        return self.collections[name]


def test_learning_session_identity_is_idempotent_but_conflicts_fail_closed() -> None:
    db = _Database()
    repo = RAGStateRepository(db)

    first = repo.put_learning_session(
        session_id="s1",
        user_id="u1",
        topic="python",
        content="canonical",
        duration_minutes=10,
        mastery_delta=0.2,
        timestamp="2026-09-21T18:00:00Z",
    )
    second = repo.put_learning_session(
        session_id="s1",
        user_id="u1",
        topic="python",
        content="canonical",
        duration_minutes=99,
        mastery_delta=0.9,
        timestamp="2026-09-21T19:00:00Z",
    )

    assert first == second
    assert db[repo.LEARNING].count_documents({}) == 1

    with pytest.raises(RAGStateConflict, match="content"):
        repo.put_learning_session(
            session_id="s1",
            user_id="u1",
            topic="python",
            content="conflicting",
            duration_minutes=10,
            mastery_delta=0.2,
            timestamp="2026-09-21T18:00:00Z",
        )


def test_progress_is_mongo_authoritative_upsert() -> None:
    db = _Database()
    repo = RAGStateRepository(db)

    repo.upsert_user_progress(
        user_id="u1",
        domain="python",
        mastery_level=0.3,
        concepts_learned=["loops"],
        total_hours=1.0,
        updated_at="2026-09-21T18:00:00Z",
    )
    repo.upsert_user_progress(
        user_id="u1",
        domain="python",
        mastery_level=0.8,
        concepts_learned=["loops", "asyncio"],
        total_hours=5.0,
        updated_at="2026-09-21T19:00:00Z",
    )

    progress = repo.get_user_progress("u1")
    assert list(progress) == ["python"]
    assert progress["python"]["mastery_level"] == 0.8
    assert progress["python"]["concepts_learned"] == ["loops", "asyncio"]
    assert db[repo.PROGRESS].count_documents({}) == 1


def test_cocoding_lookup_is_bound_to_user_ownership() -> None:
    db = _Database()
    repo = RAGStateRepository(db)
    repo.put_cocoding_context(
        session_id="code-1",
        user_id="owner-a",
        pipeline="python",
        context="ctx",
        code_snippets=["print(1)"],
        decisions=["ship"],
        timestamp="2026-09-21T18:00:00Z",
    )

    assert repo.get_cocoding_context("code-1", user_id="owner-a") is not None
    assert repo.get_cocoding_context("code-1", user_id="owner-b") is None


def test_feedback_identity_is_idempotent_and_stats_cover_authority() -> None:
    db = _Database()
    repo = RAGStateRepository(db)
    repo.put_feedback(
        feedback_id="f1",
        user_id="u1",
        feedback_type="rating",
        content="useful",
        rating=5,
        timestamp="2026-09-21T18:00:00Z",
    )
    repo.put_feedback(
        feedback_id="f1",
        user_id="u1",
        feedback_type="rating",
        content="useful",
        rating=5,
        timestamp="2026-09-21T18:00:00Z",
    )

    assert repo.stats() == {
        "learning_sessions": 0,
        "user_progress": 0,
        "cocoding_context": 0,
        "feedback": 1,
    }


def test_ensure_indexes_declares_unique_identity_constraints() -> None:
    db = _Database()
    repo = RAGStateRepository(db)

    repo.ensure_indexes()

    assert db[repo.LEARNING].indexes
    assert db[repo.PROGRESS].indexes
    assert db[repo.COCODING].indexes
    assert db[repo.FEEDBACK].indexes
    assert any(kwargs.get("unique") for _, kwargs in db[repo.PROGRESS].indexes)
