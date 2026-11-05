"""Complete world→assets→timeline→playable engine bundle acceptance."""
import json
import os

import pytest

from skeleton.jeeves.worlds.asset_briefs import (
    ASSET_SCHEMA, AssetBriefStore, edit_briefs, propose_asset,
)
from skeleton.jeeves.worlds.bundle import PlayableBundleStore
from skeleton.jeeves.worlds.timeline import TimelineStore, propose_timeline
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


@pytest.fixture
def published(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    world = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                    protagonist="Sora", region="North Harbor",
                    goal="Restore the beacon.")
    wd = worlds.publish(world, create=True)
    asset = propose_asset(world, asset_id="hero", scene="opening",
                          kind="sprite", description="Original sailor silhouette",
                          alt_text="A sailor in a blue coat")
    data = {"schema": ASSET_SCHEMA, "world_id": "harbor",
            "world_digest": prove(world).source_digest, "assets": [asset]}
    approved = edit_briefs(data, world, {"action": "review", "value": {
        "id": "hero", "originality_attested": True,
    }})
    ad = AssetBriefStore(root).publish("harbor", approved, create=True)
    timeline = propose_timeline(world, actor="sora",
                                opening_note="The beacon goes dark.",
                                resolution_note="The light returns.")
    td = TimelineStore(root).publish("harbor", timeline, create=True)
    return root, world, wd, ad, td


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_full_verified_playable_bundle(published):
    root, world, wd, ad, td = published
    store = PlayableBundleStore(root)
    receipt = store.compile("harbor", world_digest=wd, asset_digest=ad,
                            timeline_digest=td, era="eight_bit_tile_1983")
    assert store.verify("harbor") == receipt
    html = (root / receipt["html_file"]).read_text()
    assert "addEventListener" in html
    assert "default-src 'none'" in html
    manifest = json.loads((root / receipt["manifest_file"]).read_text())
    assert manifest["engine_assets"]["engine_manifest"]["asset_count"] == 1
    assert manifest["temporal_events"]["events"][0]["kind"] == "setup"
    assert manifest["world_digest"] == digest(world)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_tampered_html_fails_closed(published):
    root, _, wd, ad, td = published
    store = PlayableBundleStore(root)
    receipt = store.compile("harbor", world_digest=wd, asset_digest=ad,
                            timeline_digest=td, era="eight_bit_tile_1983")
    (root / receipt["html_file"]).write_text("<html>tampered</html>")
    with pytest.raises(CanonError, match="bundle_artifact_tampered"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_missing_manifest_fails_closed(published):
    root, _, wd, ad, td = published
    store = PlayableBundleStore(root)
    receipt = store.compile("harbor", world_digest=wd, asset_digest=ad,
                            timeline_digest=td, era="eight_bit_tile_1983")
    (root / receipt["manifest_file"]).unlink()
    with pytest.raises(CanonError, match="artifact_missing"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_stale_world_cannot_republish(published):
    root, world, wd, ad, td = published
    changed = dict(world)
    changed["scenes"] = [dict(x) for x in world["scenes"]]
    changed["scenes"][0]["title"] = "Revised"
    WorldStore(root).publish(changed, expected_digest=wd)
    with pytest.raises(CanonError, match="asset_source_lease_mismatch"):
        PlayableBundleStore(root).compile(
            "harbor", world_digest=wd, asset_digest=ad,
            timeline_digest=td, era="eight_bit_tile_1983")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_incompatible_era_fails_without_receipt(published):
    root, _, wd, ad, td = published
    with pytest.raises(CanonError, match="engine_asset_compile_rejected"):
        PlayableBundleStore(root).compile(
            "harbor", world_digest=wd, asset_digest=ad,
            timeline_digest=td, era="pong_discrete_1972")
    assert not (root / "harbor.bundle.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_replay_produces_identical_receipt(published):
    root, _, wd, ad, td = published
    store = PlayableBundleStore(root)
    first = store.compile("harbor", world_digest=wd, asset_digest=ad,
                          timeline_digest=td, era="eight_bit_tile_1983")
    second = store.compile("harbor", world_digest=wd, asset_digest=ad,
                           timeline_digest=td, era="eight_bit_tile_1983")
    assert first == second
    assert store.verify("harbor") == first


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_artifact_symlink_rejected(published):
    root, _, wd, ad, td = published
    store = PlayableBundleStore(root)
    receipt = store.compile("harbor", world_digest=wd, asset_digest=ad,
                            timeline_digest=td, era="eight_bit_tile_1983")
    target = root / "target"
    target.write_text("outside")
    (root / receipt["html_file"]).unlink()
    (root / receipt["html_file"]).symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
