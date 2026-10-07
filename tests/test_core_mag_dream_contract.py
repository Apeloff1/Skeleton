"""Genesis' legacy core MAG must satisfy the canonical dream contract."""

from skeleton.intelligence.dream import DreamEngine
from skeleton.memory.core import MAGStore
from skeleton.memory.rag import InMemoryTFIDFStore


def test_core_mag_exposes_user_identity_and_deterministic_clusters() -> None:
    mag = MAGStore("user-1")
    mag.record("e2", "second", tags=["theme", "other"])
    mag.record("e1", "first", tags=["theme"])

    assert mag.user_id == "user-1"
    assert mag.clusters(min_size=2) == (("theme", ("e1", "e2")),)


def test_core_mag_replacement_repairs_old_tag_membership() -> None:
    mag = MAGStore("user-1")
    mag.record("e1", "first", tags=["old"])
    mag.record("e1", "replacement", tags=["new"])

    assert mag.recall_by_tag("old") == []
    assert mag.recall_by_tag("new") == [mag._episodes["e1"]]


def test_dream_engine_accepts_core_mag_used_by_genesis() -> None:
    mag = MAGStore("user-1")
    rag = InMemoryTFIDFStore()
    dream = DreamEngine(mag, rag)

    mag.record("e1", "first", tags=["theme"])
    mag.record("e2", "second", tags=["theme"])
    themes = dream.dream(min_cluster=2)

    assert len(themes) == 1
    assert themes[0]["tag"] == "theme"
    assert themes[0]["episode_ids"] == ["e1", "e2"]
