"""Updating a document body must not wipe tags, and a negative limit is not the tail."""

import pytest

from skeleton.intelligence.knowledge_base import KnowledgeBase


def test_put_keeps_tags_when_the_update_omits_them(tmp_path) -> None:
    base = KnowledgeBase(root=tmp_path)
    base.put("runbook", "Restart API", "stop then start", tags=["ops"], subsystems=["api"])
    updated = base.put("runbook", "Restart API", "stop, wait, start")
    assert updated.version == 2
    assert updated.tags == ["ops"]
    assert updated.subsystems == ["api"]
    cleared = base.put("runbook", "Restart API", "stop, wait, start", tags=[], subsystems=[])
    assert cleared.tags == []
    assert cleared.subsystems == []


def test_negative_search_limit_is_rejected(tmp_path) -> None:
    base = KnowledgeBase(root=tmp_path)
    base.put("a", "Alpha guide", "alpha details", tags=["guide"])
    with pytest.raises(ValueError):
        base.search("alpha", limit=-1)
    assert base.search("alpha", limit=0) == []
