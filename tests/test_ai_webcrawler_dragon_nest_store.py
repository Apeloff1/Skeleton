"""Integration checks for signed, owner-scoped Dragon nest persistence."""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.webcrawler.dragon_nest_progression import AcquiredKnowledge
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore

T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"
KEY = b"production-test-signing-key-32-bytes-long"


@pytest.fixture
def store():
    db = sqlite3.connect(":memory:")
    try:
        yield DragonNestStore(db, signing_key=KEY)
    finally:
        db.close()


def initialize(store, owner="owner-a"):
    return store.initialize(owner, ("source-a", "source-b"),
                            focus_tags=("game-code",),
                            adjacent_tags=("software-debug",),
                            at=T0, authorized=True)


def adult(store, owner="owner-a"):
    initialize(store, owner)
    store.record_parent(owner, "source-a", content_sha256="a" * 64, at=T0,
                        authorized=True, reviewed=True, lawful=True)
    return store.record_parent(owner, "source-b", content_sha256="b" * 64,
                               at=T0, authorized=True, reviewed=True, lawful=True)


def article():
    return AcquiredKnowledge("research/source", "c" * 64, T1,
                             ("game-code",), True, True, .99,
                             "2026-10-11T00:00:00Z")


def test_full_lifecycle_survives_new_store_handle(store):
    assert store.view("owner-a", authorized=True) is None
    state = adult(store)
    assert state.stage == "adult" and len(state.children) == 3
    state = store.record_idle("owner-a", "article", article(), at=T1,
                              idle_since=T0, consented=True,
                              background_allowed=True, authorized=True)
    other = DragonNestStore(store.db, signing_key=KEY)
    restored = other.read("owner-a", authorized=True)
    assert restored == state
    assert restored.children[0].level == 1
    ui = other.view("owner-a", authorized=True)
    assert ui["last_changed_at"].endswith("Z")
    assert ui["history_head"] == restored.head
    assert ui["children"][0]["knowledge_items"] == 1


def test_duplicate_parent_and_hatchling_receipts_are_noop(store):
    first = adult(store)
    duplicate = store.record_parent(
        "owner-a", "source-a", content_sha256="b" * 64, at=T1,
        authorized=True, reviewed=True, lawful=True)
    assert duplicate == first
    first_child = store.record_idle("owner-a", "article", article(), at=T1,
                                   idle_since=T0, consented=True,
                                   background_allowed=True, authorized=True)
    second_child = store.record_idle("owner-a", "article", article(), at=T1,
                                    idle_since=T0, consented=True,
                                    background_allowed=True, authorized=True)
    assert first_child == second_child
    count = store.db.execute("SELECT COUNT(*) FROM dragon_nest_history WHERE owner=?",
                             ("owner-a",)).fetchone()[0]
    assert count == len(first_child.changes)


def test_different_owners_never_share_progress_or_receipts(store):
    adult(store, "owner-a")
    initialize(store, "owner-b")
    assert store.view("owner-a", authorized=True)["stage"] == "adult"
    assert store.view("owner-b", authorized=True)["stage"] == "egg"
    with pytest.raises(PermissionError):
        store.view("owner-b", authorized=False)
    with pytest.raises(PermissionError):
        store.record_idle("owner-b", "video", article(), at=T1,
                          idle_since=T0, consented=True,
                          background_allowed=True, authorized=False)


def test_existing_census_cannot_be_replaced_or_reset(store):
    initialize(store)
    with pytest.raises(ValueError, match="cannot be replaced"):
        initialize(store)
    assert store.view("owner-a", authorized=True)["sources_consumed"] == 0


def test_missing_signature_and_edited_history_are_rejected(store):
    adult(store)
    store.db.execute(
        "UPDATE dragon_nest_state SET state_json='{}' WHERE owner='owner-a'"
    )
    store.db.commit()
    with pytest.raises(ValueError, match="signature"):
        store.read("owner-a", authorized=True)


def test_verified_mac_still_requires_every_audit_event(store):
    adult(store)
    store.db.execute(
        "DELETE FROM dragon_nest_history WHERE owner='owner-a' AND sequence=2"
    )
    store.db.commit()
    with pytest.raises(ValueError, match="sequence|missing"):
        store.read("owner-a", authorized=True)


def test_wrong_signing_key_fails_closed(store):
    adult(store)
    different = DragonNestStore(store.db, signing_key=b"alternate-secret-" * 4)
    with pytest.raises(ValueError, match="signature"):
        different.read("owner-a", authorized=True)


def test_failed_idle_commit_is_atomic_and_auditable(store):
    adult(store)
    first = store.read("owner-a", authorized=True)
    with pytest.raises(PermissionError):
        store.record_idle("owner-a", "article", article(), at=T1,
                          idle_since="2026-10-12T12:09:50Z",
                          consented=True, background_allowed=True,
                          authorized=True)
    assert store.read("owner-a", authorized=True) == first
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_nest_history WHERE owner=?", ("owner-a",)
    ).fetchone()[0] == len(first.changes)


def test_no_unsigned_initialization_or_progress(store):
    with pytest.raises(PermissionError):
        store.initialize("owner-x", ("x",), focus_tags=("game-code",),
                         at=T0, authorized=False)
    with pytest.raises(PermissionError):
        store.record_parent("owner-a", "source-a",
                            content_sha256="a"*64, at=T1, authorized=False,
                            reviewed=True, lawful=True)
    assert store.view("owner-x", authorized=True) is None


def test_invalid_mac_secret_is_rejected():
    with pytest.raises(ValueError):
        DragonNestStore(sqlite3.connect(":memory:"), signing_key=b"short")
