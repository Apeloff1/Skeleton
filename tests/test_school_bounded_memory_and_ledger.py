"""Bounded learning memory and adversarial ledger canonicalization."""
import math
import pytest

from skeleton.learning.school.memory import LearnerMemory, MemoryKind, MemoryStore
from skeleton.learning.school.decision_ledger import _digest


def memory(key, **kwargs):
    return LearnerMemory(key, "lesson " + key, MemoryKind.PROCEDURAL, **kwargs)


def test_memory_batch_is_atomic_on_invalid_item():
    store = MemoryStore([memory("first")])
    with pytest.raises(TypeError):
        store.extend([memory("second"), object()])
    assert [item.key for item in store.memories] == ["first"]


def test_memory_confidence_age_and_immutable_skills():
    with pytest.raises(ValueError):
        memory("x", age_hours=math.nan)
    with pytest.raises(ValueError):
        memory("x", confidence=True)
    with pytest.raises(ValueError):
        memory("x", access_count=True)
    skills = ["python"]
    item = memory("x", skill_ids=skills)
    skills.append("untrusted")
    assert item.skill_ids == ("python",)


def test_memory_query_caps_and_stable_tie_break():
    store = MemoryStore([memory("z"), memory("a")])
    assert [row.memory.key for row in store.retrieve()] == ["a", "z"]
    with pytest.raises(ValueError):
        store.retrieve(limit=True)
    with pytest.raises(ValueError):
        store.retrieve(query_terms=["term"] * 129)


def test_decision_digest_rejects_cycles_and_large_integers():
    value = []
    value.append(value)
    with pytest.raises(ValueError, match="structural"):
        _digest(value)
    with pytest.raises(ValueError, match="integer"):
        _digest(1 << 5000)
    assert _digest({"z": 1, "a": ["ok"]}) == _digest({"a": ["ok"], "z": 1})
