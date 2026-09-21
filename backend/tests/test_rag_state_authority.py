from __future__ import annotations

from copy import deepcopy

from services import rag_service as rag_module
from services.rag_service import RAGService
from services.rag_state_repository import RAGStateRepository


def _matches(row: dict, query: dict) -> bool:
    return all(row.get(key) == value for key, value in query.items())


class _Cursor:
    def __init__(self, rows):
        self.rows = [deepcopy(row) for row in rows]

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key, ""), reverse=direction < 0)
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    def __iter__(self):
        return iter([deepcopy(row) for row in self.rows])


class _Collection:
    def __init__(self):
        self.rows = []

    def create_index(self, *args, **kwargs):
        return "idx"

    def find_one(self, query):
        for row in self.rows:
            if _matches(row, query):
                return deepcopy(row)
        return None

    def insert_one(self, document):
        self.rows.append(deepcopy(document))
        return object()

    def replace_one(self, query, document, upsert=False):
        for index, row in enumerate(self.rows):
            if _matches(row, query):
                self.rows[index] = deepcopy(document)
                return object()
        if upsert:
            self.rows.append(deepcopy(document))
        return object()

    def find(self, query):
        return _Cursor([row for row in self.rows if _matches(row, query)])

    def count_documents(self, query):
        return sum(1 for row in self.rows if _matches(row, query))


class _Database:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


class _Projection:
    def __init__(self, *, fail_add=False):
        self.rows = {}
        self.fail_add = fail_add

    def add(self, documents, metadatas, ids):
        if self.fail_add:
            raise RuntimeError("projection unavailable")
        for document, metadata, record_id in zip(documents, metadatas, ids):
            self.rows[str(record_id)] = {
                "document": document,
                "metadata": deepcopy(metadata),
            }

    def delete(self, ids=None, where=None):
        if ids:
            for record_id in ids:
                self.rows.pop(str(record_id), None)

    def count(self):
        return len(self.rows)

    def get(self, ids=None, where=None):
        selected = []
        for record_id, row in self.rows.items():
            if ids and record_id not in ids:
                continue
            if where and not all(row["metadata"].get(k) == v for k, v in where.items()):
                continue
            selected.append((record_id, row))
        return {
            "ids": [record_id for record_id, _ in selected],
            "documents": [row["document"] for _, row in selected],
            "metadatas": [deepcopy(row["metadata"]) for _, row in selected],
        }

    def query(self, query_texts, n_results=5, where=None):
        selected = []
        for record_id, row in self.rows.items():
            if where and not all(row["metadata"].get(k) == v for k, v in where.items()):
                continue
            selected.append((record_id, row))
        selected = selected[:n_results]
        return {
            "ids": [[record_id for record_id, _ in selected]],
            "documents": [[row["document"] for _, row in selected]],
            "metadatas": [[deepcopy(row["metadata"]) for _, row in selected]],
            "distances": [[0.1 for _ in selected]],
        }


class _ProjectionClient:
    def __init__(self):
        self.collections = {}
        self.fail_names = set()

    def get_or_create_collection(self, name, **kwargs):
        if name not in self.collections:
            self.collections[name] = _Projection(
                fail_add=name in self.fail_names,
            )
        return self.collections[name]


def _service():
    db = _Database()
    state = RAGStateRepository(db)
    service = RAGService(state_repository=state)
    client = _ProjectionClient()
    rag_module._collections.clear()
    service.client = client
    service._init_collections()
    return service, state, db, client


def test_projection_failure_does_not_rollback_canonical_learning_session() -> None:
    service, state, _, client = _service()
    client.collections["jeeves_learning_sessions"].fail_add = True

    session_id = service.store_learning_session(
        "u1",
        "python",
        "canonical survives",
        15,
        mastery_delta=0.2,
    )

    rows = state.list_learning_sessions("u1")
    assert rows[0]["session_id"] == session_id
    assert rows[0]["content"] == "canonical survives"
    assert service._projection_failures == 1


def test_user_progress_never_uses_chroma_as_authority() -> None:
    service, state, _, client = _service()
    client.collections["jeeves_learning_sessions"].fail_add = True

    progress_id = service.update_user_progress(
        "u1",
        "python",
        0.7,
        ["loops", "asyncio"],
        4.5,
    )
    result = service.get_user_progress("u1")

    assert progress_id == "u1:python"
    assert result["python"]["data"]["mastery_level"] == 0.7
    assert result["python"]["metadata"]["authority"] == "mongo"
    assert state.get_user_progress("u1")["python"]["total_hours"] == 4.5


def test_stale_cocoding_projection_cannot_resurrect_missing_canonical_state() -> None:
    service, state, _, client = _service()
    projection = client.collections["jeeves_cocoding_context"]
    projection.add(
        documents=["stale"],
        metadatas=[{"user_id": "u1", "pipeline": "python"}],
        ids=["stale-id"],
    )

    assert service.get_relevant_context("u1", "anything", pipeline="python") == []

    service.store_cocoding_context(
        "live-id",
        "u1",
        "python",
        "canonical context",
        ["print(1)"],
        ["keep Mongo authoritative"],
    )
    results = service.get_relevant_context("u1", "anything", pipeline="python")

    assert len(results) == 1
    assert results[0]["metadata"]["session_id"] == "live-id"
    assert results[0]["metadata"]["authority"] == "mongo"
    assert "canonical context" in results[0]["content"]


def test_legacy_chroma_migration_is_idempotent_for_authoritative_rows() -> None:
    service, state, db, client = _service()

    client.collections["jeeves_learning_sessions"].add(
        documents=["legacy lesson"],
        metadatas=[{
            "user_id": "u1",
            "topic": "python",
            "duration_minutes": 10,
            "mastery_delta": 0.1,
            "timestamp": "2026-09-20T10:00:00",
        }],
        ids=["legacy-session"],
    )
    client.collections.setdefault("jeeves_user_progress", _Projection()).add(
        documents=['{"mastery_level":0.4,"concepts_learned":["loops"],"total_hours":2.0}'],
        metadatas=[{
            "user_id": "u1",
            "domain": "python",
            "updated_at": "2026-09-20T10:00:00",
        }],
        ids=["u1:python"],
    )
    client.collections["jeeves_feedback"].add(
        documents=["legacy feedback"],
        metadatas=[{
            "user_id": "u1",
            "feedback_type": "rating",
            "rating": 4,
            "timestamp": "2026-09-20T10:00:00",
        }],
        ids=["feedback-1"],
    )

    first = service.migrate_legacy_chroma_state()
    second = service.migrate_legacy_chroma_state()

    assert first["learning_sessions"] == 1
    assert first["user_progress"] == 1
    assert first["feedback"] == 1
    assert second["conflicts"] == 0
    assert db[state.LEARNING].count_documents({}) == 1
    assert db[state.PROGRESS].count_documents({}) == 1
    assert db[state.FEEDBACK].count_documents({}) == 1


def test_stats_distinguish_mongo_authority_from_rebuildable_projection() -> None:
    service, _, _, _ = _service()
    service.update_user_progress("u1", "python", 0.5, ["loops"], 2.0)

    stats = service.get_stats()

    assert stats["authority"]["store"] == "mongo"
    assert stats["authority"]["collections"]["user_progress"] == 1
    assert stats["projection"]["store"] == "chroma"
    assert stats["projection"]["rebuildable"] is True
