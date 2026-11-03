"""The laptop-to-engine bridge must not accept mixed-generation receipts."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.studio_engine import StudioEngineStore
from skeleton.jeeves.worlds.world_canon import CanonError, digest
from skeleton.testing.test_jeeves_world_studio_engine import fixture as engine_fixture

ERA = "eight_bit_tile_1983"


def prepared(tmp_path):
    engine_fixture(tmp_path)
    flow = LaptopFlow(tmp_path)
    world = flow.worlds.read("harbor")
    reviewed = flow.approve_current(
        "harbor", digest(world), "Reviewed canonical harbor source for engine handoff.")
    flow.compile("harbor", reviewed["source_digest"])
    return flow


def test_engine_compile_returns_matching_verified_receipts(tmp_path):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    result = flow.engine_compile(
        "harbor", ERA, preview["engine"]["source_digests"])
    assert result == flow.engine_verify("harbor")
    assert result["engine"]["source_digests"]["world"] == result["laptop"]["source_digest"]
    assert result["laptop"] == preview["laptop"]


def test_engine_compile_rejects_interleaved_laptop_revision(tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    original = flow.verify
    seen = 0

    def raced(world_id):
        nonlocal seen
        seen += 1
        result = original(world_id)
        if seen == 2:
            # Simulate another writer replacing a valid, reviewed laptop
            # artifact between engine verification and the final handoff.
            return {**result, "source_digest": "0" * 64}
        return result

    monkeypatch.setattr(flow, "verify", raced)
    with pytest.raises(CanonError) as error:
        flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    assert error.value.code == "laptop_engine_source_mismatch"
    assert seen == 2
    # The engine receipt may exist, but the composite handoff is never
    # advertised as verified. A subsequent fresh verification is required.
    monkeypatch.setattr(flow, "verify", original)
    assert flow.engine_verify("harbor")["engine"]["source_digests"] == preview["engine"]["source_digests"]


def test_engine_compile_rejects_interleaved_review_receipt(tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    original = flow.verify
    seen = 0

    def raced(world_id):
        nonlocal seen
        seen += 1
        result = original(world_id)
        if seen == 2:
            return {**result, "review_digest": "f" * 64}
        return result

    monkeypatch.setattr(flow, "verify", raced)
    with pytest.raises(CanonError) as error:
        flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    assert error.value.code == "laptop_engine_source_mismatch"
    assert seen == 2
