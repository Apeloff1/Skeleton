"""Procedural seed tests."""
from skeleton.jeeves.ecosystem.procedural.seed_001 import rooms, edges, loot

def test_rooms_and_edges():
    rs = rooms(5, 0.94)
    assert len(rs) == 5
    assert rs[-1]["kind"] == "boss"
    es = edges(5)
    assert [0, 1] in es

def test_loot():
    assert loot(0.96) == "epic"
    assert loot(0.8) == "common"
