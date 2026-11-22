"""Extraction nodes: depletion and faucet caps."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.industry.errors import ExtractionCapped, NodeDepleted
from skeleton.economy.gameplay.industry.tests.conftest import build_system


def test_window_cap_trims_and_cooldown_blocks():
    s = build_system()
    assert s.extract("ana", "vein_a", tick=0) == 20
    assert s.extract("bo", "vein_a", tick=1) == 10  # 30-unit window cap trims
    with pytest.raises(ExtractionCapped):
        s.extract("ana", "vein_a", tick=3)  # cooldown
    with pytest.raises(ExtractionCapped):
        s.extract("bo", "vein_a", tick=6)  # window still full
    assert s.extract("ana", "vein_a", tick=10) == 20
    report = s.econ.item_report("ore")
    assert report["by_source"] == {"extract:vein_a": 50}


def test_window_cap_never_exceeded_over_many_ticks():
    s = build_system()
    got: list[tuple[int, int]] = []
    for t in range(0, 200):
        for owner in ("ana", "bo"):
            try:
                got.append((t, s.extract(owner, "vein_a", tick=t)))
            except (ExtractionCapped, NodeDepleted):
                pass
    for t, _ in got:
        assert sum(q for u, q in got if t <= u < t + 10) <= 30


def test_node_depletes_and_mints_exactly_reserve():
    s = build_system()
    total = 0
    tick = 0
    while not s.nodes["seam_b"].depleted:
        total += s.extract("ana", "seam_b", tick=tick)
        tick += 1
    assert total == 40
    with pytest.raises(NodeDepleted):
        s.extract("bo", "seam_b", tick=tick)
    assert s.econ.item_report("coal")["minted"] == 40
    assert s.audit()["ok"]


def test_partial_last_yield():
    s = build_system()
    node = s.nodes["vein_a"]
    node.remaining, node.extracted = 7, 93
    assert s.extract("ana", "vein_a", tick=0) == 7
    assert node.depleted


def test_refused_extraction_changes_nothing():
    s = build_system()
    s.extract("ana", "seam_b", tick=0)
    before = s.digest()
    with pytest.raises(ExtractionCapped):
        s.extract("ana", "seam_b", tick=0)
    with pytest.raises(Exception):
        s.extract("ana", "nowhere", tick=0)
    assert s.digest() == before
