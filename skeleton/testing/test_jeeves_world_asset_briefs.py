"""Actual engine asset handoff and reviewed provenance custody."""
import copy
import os

import pytest

from skeleton.jeeves.worlds.asset_briefs import (
    ASSET_SCHEMA, AssetBriefStore, compile_assets, edit_briefs,
    propose_asset, validate_briefs,
)
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def setup():
    world = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                    protagonist="Sora", region="North Harbor",
                    goal="Restore the beacon.")
    item = propose_asset(world, asset_id="hero", scene="opening",
                         kind="sprite", description="Original sailor silhouette",
                         alt_text="A sailor in a blue coat")
    data = {"schema": ASSET_SCHEMA, "world_id": "harbor",
            "world_digest": prove(world).source_digest, "assets": [item]}
    return world, data


def reviewed(world, data):
    return edit_briefs(data, world, {"action": "review", "value": {
        "id": "hero", "originality_attested": True,
    }})


def test_typed_proposal_requires_explicit_review():
    world, data = setup()
    assert validate_briefs(data, world)["assets"][0]["reviewed"] is False
    with pytest.raises(CanonError, match="asset_review_required"):
        compile_assets(data, world, "eight_bit_tile_1983")


def test_reviewed_descriptor_compiles_to_real_engine_manifest():
    world, data = setup()
    output = compile_assets(reviewed(world, data), world, "eight_bit_tile_1983")
    assert output["engine_manifest"]["asset_count"] == 1
    assert output["engine_manifest"]["engine_era"] == "eight_bit_tile_1983"
    assert output["world_digest"] == digest(world)
    assert output["review_provenance"].startswith("operator_attestation")


def test_review_without_rights_attestation_still_held():
    world, data = setup()
    updated = edit_briefs(data, world, {"action": "review", "value": {
        "id": "hero", "originality_attested": False,
    }})
    with pytest.raises(CanonError, match="asset_review_required"):
        compile_assets(updated, world, "eight_bit_tile_1983")


def test_asset_bound_to_exact_world_revision():
    world, data = setup()
    altered = copy.deepcopy(world)
    altered["scenes"][0]["title"] = "Revised opening"
    with pytest.raises(CanonError, match="asset_source_lease_mismatch"):
        validate_briefs(data, altered)


def test_unknown_scene_rejected():
    world, data = setup()
    data["assets"][0]["scene"] = "missing"
    with pytest.raises(CanonError, match="unknown_asset_scene"):
        validate_briefs(data, world)


def test_duplicate_asset_rejected():
    world, data = setup()
    data["assets"].append(copy.deepcopy(data["assets"][0]))
    with pytest.raises(CanonError, match="duplicate_asset"):
        validate_briefs(data, world)


def test_bool_cannot_be_numeric_budget():
    world, data = setup()
    data["assets"][0]["width"] = True
    with pytest.raises(CanonError, match="invalid_numeric_budget"):
        validate_briefs(data, world)


def test_unreviewed_import_cannot_forge_approval():
    world, data = setup()
    forged = copy.deepcopy(data["assets"][0])
    forged["reviewed"] = True
    with pytest.raises(CanonError, match="review_cannot_be_imported"):
        edit_briefs(data, world, {"action": "add", "value": forged})


def test_edit_invalidates_prior_approval():
    world, data = setup()
    approved = reviewed(world, data)
    modified = copy.deepcopy(data["assets"][0])
    modified["description"] = "A new original description"
    edited = edit_briefs(approved, world, {"action": "replace", "value": modified})
    assert edited["assets"][0]["reviewed"] is False


def test_reject_era_incompatible_asset():
    world, data = setup()
    with pytest.raises(CanonError, match="engine_asset_compile_rejected"):
        compile_assets(reviewed(world, data), world, "pong_discrete_1972")


def test_compile_is_deterministic():
    world, data = setup()
    approved = reviewed(world, data)
    assert compile_assets(approved, world, "eight_bit_tile_1983") == (
        compile_assets(copy.deepcopy(approved), copy.deepcopy(world),
                       "eight_bit_tile_1983")
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_source_leased_persist_and_compile(tmp_path):
    worlds = WorldStore(tmp_path / "private")
    world, data = setup()
    worlds.publish(world, create=True)
    store = AssetBriefStore(tmp_path / "private")
    initial = store.publish("harbor", data, create=True)
    assert digest(store.read("harbor")) == initial
    approved = reviewed(world, data)
    final = store.publish("harbor", approved, expected_digest=initial)
    receipt = store.compile("harbor", final, "eight_bit_tile_1983")
    assert receipt["asset_briefs_digest"] == final
    with pytest.raises(CanonError, match="stale_asset_source"):
        store.compile("harbor", initial, "eight_bit_tile_1983")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_world_revision_invalidates_asset_publication(tmp_path):
    worlds = WorldStore(tmp_path / "private")
    world, data = setup()
    old = worlds.publish(world, create=True)
    store = AssetBriefStore(tmp_path / "private")
    store.publish("harbor", data, create=True)
    revised = copy.deepcopy(world)
    revised["scenes"][0]["title"] = "New harbor"
    worlds.publish(revised, expected_digest=old)
    with pytest.raises(CanonError, match="asset_source_lease_mismatch"):
        store.read("harbor")
