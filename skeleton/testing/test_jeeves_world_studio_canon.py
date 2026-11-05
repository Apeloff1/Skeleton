"""Cross-plane canon: an informed NPC cannot contradict their own testimony."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.jeeves.worlds.studio_canon import prove_studio_cross_canon
from skeleton.jeeves.worlds.studio_assembly import StudioAssemblyStore
from skeleton.jeeves.worlds.world_canon import CanonError, digest
from skeleton.testing.test_jeeves_world_studio_assembly import fixture


def test_matching_testimony_and_rumor_have_cross_plane_proof(tmp_path):
    store = fixture(tmp_path)
    fd = store.worlds._directory()
    try:
        world, cast, testimony, rumors, *_ = store._sources(fd, "harbor")
        proof = prove_studio_cross_canon(world, cast, testimony, rumors)
    finally:
        import os
        os.close(fd)
    assert proof["cross_plane_contradictions"] == 0
    assert proof["ending_witnesses"]["resolution"] == ["pursue_goal", "save_beacon"]
    assert "cross_plane" in store.inspect("harbor")["proof_digests"]


def test_approved_but_conflicting_npc_claim_fails_assembly(tmp_path):
    store = fixture(tmp_path)
    current = store.testimony.inspect("harbor")["testimony"]
    modified = deepcopy(current)
    modified["statements"][0]["stance"] = "denies"
    first = store.testimony.publish("harbor", modified, expected_digest=digest(current))
    store.testimony.approve("harbor", expected_digest=first, review_note="Reviewed")
    with pytest.raises(CanonError) as exc:
        store.inspect("harbor")
    assert exc.value.code == "studio_cross_plane_contradiction"


def test_cross_plane_proof_cannot_be_forged_with_stale_sources(tmp_path):
    store = fixture(tmp_path)
    fd = store.worlds._directory()
    try:
        world, cast, testimony, rumors, *_ = store._sources(fd, "harbor")
        modified = deepcopy(rumors)
        modified["world_digest"] = "0" * 64
        with pytest.raises(CanonError) as exc:
            prove_studio_cross_canon(world, cast, testimony, modified)
        assert exc.value.code == "rumors_source_lease_mismatch"
    finally:
        import os
        os.close(fd)
