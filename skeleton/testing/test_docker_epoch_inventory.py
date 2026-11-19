"""Bounded read-only canonical actor/epoch migration inventory tests.

Fake PyMongo collections preserve query contracts without a daemon. No
migration, index, collection or actor epoch is written by these tests.
"""
from __future__ import annotations

from collections.abc import Mapping
from unittest import mock

import pytest

from skeleton.persistence import docker_epoch_inventory as inventory
from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def find(self, query, **kwargs):
        self.calls.append((query, kwargs))
        assert kwargs["limit"] <= inventory._MAX_RECORDS + 1
        assert kwargs["max_time_ms"] == 5000
        return iter(self.rows[:kwargs["limit"]])


class _Epoch:
    def __init__(self, epochs):
        self.epochs = epochs
        self.calls = []
    def find_one(self, selector, **kwargs):
        self.calls.append((selector, kwargs))
        assert kwargs["max_time_ms"] == 2000
        return self.epochs.get(selector["_id"])


class _DB:
    def __init__(self, collection):
        self.collection = collection
        self.calls = []
    def get_collection(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return self.collection


class _Client:
    def __init__(self, conversations, memories, epochs):
        self.conversations = _Rows(conversations)
        self.memories = _Rows(memories)
        self.epoch = _Epoch(epochs)
        self.databases = {
            "tutolage": _DB(self.conversations),
            "skeleton": _DB(self.memories),
            "skeleton_guarded_source": _DB(self.epoch),
        }
    def __getitem__(self, name):
        return self.databases[name]


def _key(tenant, actor):
    return MongoCanonicalSourceEpoch._key(tenant, actor)


def _stable(tenant, actor, n=2):
    return {
        "_id": _key(tenant, actor),
        "tenant_id": tenant,
        "actor_id": actor,
        "phase": "stable",
        "writer_token": None,
        "epoch": n,
    }


def _scan(client, limit=16):
    with mock.patch.object(inventory, "probe_epoch_capability", return_value={"ok": True}):
        return inventory.audit_epoch_inventory(
            client, backend_database="tutolage",
            engine_database="skeleton", max_records=limit,
        )


def test_complete_inventory_counts_both_sources_without_exposing_actor_ids() -> None:
    client = _Client(
        [{"tenant_id": "private-t", "owner_id": "actor-a"}],
        [{"tenant_id": "private-t", "subject_id": "actor-a"},
         {"tenant_id": "private-t", "subject_id": "actor-b"}],
        {
            _key("private-t", "actor-a"): _stable("private-t", "actor-a"),
            _key("private-t", "actor-b"): _stable("private-t", "actor-b", 4),
        },
    )
    result = _scan(client)
    assert result["unique_actor_count"] == 2
    assert result["conversation_records_scanned"] == 1
    assert result["memory_records_scanned"] == 2
    assert result["actors_without_epoch"] == 0
    assert result["actors_unstable_or_quarantined"] == 0
    assert result["all_sampled_actor_epochs_stable"] is True
    assert result["writer_quiescence_verified"] is False
    assert result["external_writers_excluded"] is False
    assert result["actor_migration_complete"] is False
    assert result["collections_modified"] is False
    assert "private-t" not in str(result)
    assert "actor-a" not in str(result)
    assert len(client.epoch.calls) == 2
    assert all(row[1]["read_concern"].level == "majority" for row in (
        client.databases["tutolage"].calls[0],
        client.databases["skeleton"].calls[0],
    ))


def test_missing_or_writing_epoch_is_never_clean() -> None:
    client = _Client(
        [{"tenant_id": "t", "owner_id": "a"}],
        [{"tenant_id": "t", "subject_id": "b"}],
        {_key("t", "b"): {**_stable("t", "b"), "phase": "writing", "epoch": 3}},
    )
    result = _scan(client)
    assert result["actors_without_epoch"] == 1
    assert result["actors_unstable_or_quarantined"] == 1
    assert result["all_sampled_actor_epochs_stable"] is False
    assert result["guarded_chat_qualified"] is False


def test_records_over_limit_must_never_claim_complete_migration() -> None:
    rows = [{"tenant_id": "t", "owner_id": f"actor-{n}"} for n in range(4)]
    client = _Client(rows, [], {})
    result = _scan(client, limit=2)
    assert result["conversation_scan_truncated"] is True
    assert result["bounded_complete_for_selected_collections"] is False
    assert result["actors_without_epoch"] is None
    assert result["actors_unstable_or_quarantined"] is None
    assert result["all_sampled_actor_epochs_stable"] is False
    assert client.epoch.calls == []


@pytest.mark.parametrize("field", ["tenant_id", "owner_id"])
@pytest.mark.parametrize("malformed", [None, "", " ", 1, "\x00", "x" * 513])
def test_malformed_canonical_actor_record_fails_closed(field, malformed) -> None:
    row = {"tenant_id": "t", "owner_id": "a"}
    row[field] = malformed
    with pytest.raises(inventory.DockerEpochInventoryError):
        _scan(_Client([row], [], {}))


@pytest.mark.parametrize("database,engine,limit", [
    ("tutolage", "tutolage", 1),
    ("skeleton_guarded_source", "skeleton", 1),
    ("tutolage", "skeleton_guarded_source", 1),
    ("tutolage", "skeleton", 0),
    ("tutolage", "skeleton", 4097),
    ("bad name", "skeleton", 1),
])
def test_unbounded_or_colliding_inventory_names_are_denied(database, engine, limit) -> None:
    with pytest.raises(inventory.DockerEpochInventoryError):
        _scan(_Client([], [], {}), limit=limit) if (
            database == "tutolage" and engine == "skeleton"
        ) else inventory.audit_epoch_inventory(
            _Client([], [], {}), backend_database=database,
            engine_database=engine, max_records=limit,
        )


def test_no_source_record_does_not_prove_quiescence() -> None:
    result = _scan(_Client([], [], {}))
    assert result["all_sampled_actor_epochs_stable"] is True
    assert result["actor_migration_complete"] is False
    assert result["writer_quiescence_verified"] is False
    assert result["external_writers_excluded"] is False
