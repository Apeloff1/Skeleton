"""The laptop and engine receipts must share one canonical source lease."""
from __future__ import annotations

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
    result = flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    assert result == flow.engine_verify("harbor")
    assert result["engine"]["source_digests"]["world"] == result["laptop"]["source_digest"]
    assert result["laptop"] == preview["laptop"]


def test_engine_verify_holds_one_world_lease_across_both_artifacts(tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    original = StudioEngineStore._verify_snapshot
    attempted = []

    def guarded(self, fd, world_id):
        assert (tmp_path / "harbor.lock").exists()
        world = flow.worlds.read(world_id)
        changed = dict(world, prompt=world["prompt"] + " concurrent edit")
        with pytest.raises(CanonError) as error:
            flow.worlds.publish(changed, expected_digest=digest(world))
        attempted.append(error.value.code)
        return original(self, fd, world_id)

    monkeypatch.setattr(StudioEngineStore, "_verify_snapshot", guarded)
    verified = flow.engine_verify("harbor")
    assert verified["laptop"]["source_digest"] == verified["engine"]["source_digests"]["world"]
    assert attempted == ["lease_busy"]
    assert not (tmp_path / "harbor.lock").exists()


def test_engine_compile_rejects_interleaved_laptop_revision(tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    original = flow.engine_verify
    seen = 0

    def raced(world_id):
        nonlocal seen
        seen += 1
        result = original(world_id)
        # Simulate a newer laptop publication at the final composite boundary.
        return {**result, "laptop": {**result["laptop"], "source_digest": "0" * 64}}

    monkeypatch.setattr(flow, "engine_verify", raced)
    with pytest.raises(CanonError) as error:
        flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    assert error.value.code == "laptop_engine_source_mismatch"
    assert seen == 1
    monkeypatch.setattr(flow, "engine_verify", original)
    assert flow.engine_verify("harbor")["engine"]["source_digests"] == preview["engine"]["source_digests"]


def test_engine_compile_rejects_interleaved_review_receipt(tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    original = flow.engine_verify

    def raced(world_id):
        result = original(world_id)
        return {**result, "laptop": {**result["laptop"], "review_digest": "f" * 64}}

    monkeypatch.setattr(flow, "engine_verify", raced)
    with pytest.raises(CanonError) as error:
        flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    assert error.value.code == "laptop_engine_source_mismatch"


def test_engine_verify_rejects_tampered_manifest_under_shared_lease(tmp_path):
    flow = prepared(tmp_path)
    preview = flow.engine_inspect("harbor", ERA)
    receipt = flow.engine_compile("harbor", ERA, preview["engine"]["source_digests"])
    path = tmp_path / receipt["engine"]["manifest_file"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(CanonError) as error:
        flow.engine_verify("harbor")
    assert error.value.code == "studio_engine_manifest_mismatch"
    assert not (tmp_path / "harbor.lock").exists()

def test_engine_preview_holds_lease_across_laptop_and_nine_plane_read(
        tmp_path, monkeypatch):
    flow = prepared(tmp_path)
    original = StudioEngineStore._inspect_snapshot
    attempted = []

    def guarded(self, fd, world_id, era):
        assert (tmp_path / "harbor.lock").exists()
        world = flow.worlds.read(world_id)
        changed = dict(world, prompt=world["prompt"] + " concurrent preview edit")
        with pytest.raises(CanonError) as error:
            flow.worlds.publish(changed, expected_digest=digest(world))
        attempted.append(error.value.code)
        return original(self, fd, world_id, era)

    monkeypatch.setattr(StudioEngineStore, "_inspect_snapshot", guarded)
    preview = flow.engine_inspect("harbor", ERA)
    assert preview["engine"]["source_digests"]["world"] == preview["laptop"]["source_digest"]
    assert attempted == ["lease_busy"]
    assert not (tmp_path / "harbor.lock").exists()


def test_engine_preview_never_publishes_or_approves_missing_planes(tmp_path):
    from skeleton.testing.test_jeeves_world_laptop_flow import ready
    flow, _, _, _ = ready(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(CanonError) as error:
        flow.engine_inspect("lighthouse", ERA)
    assert error.value.code == "not_found"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not (tmp_path / "lighthouse.lock").exists()
