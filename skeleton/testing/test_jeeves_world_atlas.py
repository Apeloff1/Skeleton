"""Region atlas prompt-to-edit-to-review-to-compiled-playable regression contracts."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.atlas import (
    AtlasStore, atlas_report, propose_atlas, render_playable,
    review_atlas, validate_atlas,
)
from skeleton.jeeves.worlds.atlas_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def world():
    source = propose(
        world_id="voyage", premise="An original coastal rescue.",
        protagonist="Mira", region="Harbor", goal="Reach the beacon.",
    )
    return source


def crossing(source):
    atlas = propose_atlas(source, "A voyage between the harbor and beacon.")
    atlas["regions"] = [
        {"id": "beacon", "name": "Beacon", "description": "A safe original beacon."},
        {"id": "harbor", "name": "Harbor", "description": "A tidal harbor."},
    ]
    atlas["placements"] = [
        {"scene": "opening", "region": "harbor"},
        {"scene": "resolution", "region": "beacon"},
    ]
    atlas["passages"] = [{
        "id": "harbor_to_beacon", "choice": "pursue_goal",
        "from_region": "harbor", "to_region": "beacon",
        "description": "Follow the marked cliff road.",
    }]
    return atlas


def test_typed_prompt_and_reviewed_crossing():
    source = world()
    initial = propose_atlas(source, "Map the coast.")
    assert initial["approved"] is False
    assert atlas_report(initial, source)["passage_count"] == 0
    spec = crossing(source)
    assert validate_atlas(spec, source) == spec
    report = atlas_report(spec, source)
    assert report["ending_itineraries"]["resolution"] == [{
        "choice": "pursue_goal", "passage": "harbor_to_beacon",
        "from_region": "harbor", "to_region": "beacon",
    }]
    with pytest.raises(CanonError, match="atlas_review_required"):
        render_playable(spec, source)
    reviewed = review_atlas(spec, source, "Reviewed both region descriptions.")
    html = render_playable(reviewed, source).decode()
    assert "Content-Security-Policy" in html
    assert "Original region atlas" in html
    assert "Follow the marked cliff road." in html
    assert "Choices taken:" in html


@pytest.mark.parametrize("mutation,code", [
    (lambda a: a["passages"].clear(), "atlas_crossing_coverage_mismatch"),
    (lambda a: a["passages"].append(copy.deepcopy(a["passages"][0])), "atlas_duplicate_passage"),
    (lambda a: a["passages"][0].update(to_region="harbor"), "atlas_passage_placement_mismatch"),
    (lambda a: a["placements"].pop(), "atlas_incomplete_placements"),
    (lambda a: a["placements"][0].update(region="missing"), "atlas_unknown_region"),
    (lambda a: a["regions"].reverse(), "atlas_regions_not_sorted"),
    (lambda a: a.update(approved="yes"), "atlas_invalid_approval"),
])
def test_invalid_atlas_never_accepted(mutation, code):
    source = world()
    spec = crossing(source)
    mutation(spec)
    with pytest.raises(CanonError, match=code):
        validate_atlas(spec, source)


def test_stale_world_and_injection_fail_closed():
    source = world()
    spec = crossing(source)
    source["scenes"][0]["narrative"] = "Changed source."
    with pytest.raises(CanonError, match="atlas_source_lease_mismatch"):
        validate_atlas(spec, source)
    original = world()
    spec = crossing(original)
    spec["regions"][0]["name"] = "</script><img src=x onerror=alert(1)>"
    approved = review_atlas(spec, original, "Reviewed HTML escaping.")
    html = render_playable(approved, original).decode()
    assert "&lt;/script&gt;" in html
    assert "<img src=x" not in html


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_full_persist_edit_compile_verify_cli_and_jeeves(tmp_path, capsys):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    proposed = store.propose("voyage", "Map the coast.")
    initial = store.save(
        "voyage", proposed, expected_world_digest=digest(source), create=True,
    )
    assert initial == digest(proposed)
    spec = crossing(source)
    next_digest = store.save(
        "voyage", spec, expected_world_digest=digest(source),
        expected_atlas_digest=initial,
    )
    with pytest.raises(CanonError, match="atlas_stale_edit"):
        store.save(
            "voyage", proposed, expected_world_digest=digest(source),
            expected_atlas_digest=initial,
        )
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.atlas_preview", "world_id": "voyage", "args": {},
    })
    assert tool["persisted"] is False
    assert tool["result"]["report"]["passage_count"] == 1
    reviewed_digest = store.approve(
        "voyage", expected_atlas_digest=next_digest,
        review_note="Reviewed travel witness.",
    )
    assert run([
        "--store", str(tmp_path), "compile", "--world-id", "voyage",
        "--expected-atlas-digest", reviewed_digest,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"] == store.verify("voyage")
    assert "Original region atlas" in (
        tmp_path / "voyage.atlas.playable.html"
    ).read_text()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_tamper_stale_revision_and_lock_fail_closed(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    spec = review_atlas(crossing(source), source, "Reviewed source.")
    store.save("voyage", spec, expected_world_digest=digest(source), create=True)
    store.compile("voyage", expected_atlas_digest=digest(spec))
    html = tmp_path / "voyage.atlas.playable.html"
    html.write_text("tampered")
    with pytest.raises(CanonError, match="atlas_playable_mismatch"):
        store.verify("voyage")
    store.compile("voyage", expected_atlas_digest=digest(spec))
    (tmp_path / "voyage.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.verify("voyage")
    (tmp_path / "voyage.lock").unlink()
    source["scenes"][0]["narrative"] = "Revised coast."
    WorldStore(tmp_path).publish(source, expected_digest=digest(world()))
    with pytest.raises(CanonError, match="atlas_source_lease_mismatch"):
        store.verify("voyage")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlink_artifact_never_verified(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    spec = review_atlas(crossing(source), source, "Reviewed source.")
    store.save("voyage", spec, expected_world_digest=digest(source), create=True)
    store.compile("voyage", expected_atlas_digest=digest(spec))
    artifact = tmp_path / "voyage.atlas.playable.html"
    artifact.unlink()
    artifact.symlink_to(tmp_path / "voyage.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("voyage")

@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_approval_cannot_be_smuggled_through_save(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    spec = crossing(source)
    spec["approved"] = True
    spec["review_note"] = "Forged operator review."
    with pytest.raises(CanonError, match="atlas_approval_requires_review"):
        store.save("voyage", spec, expected_world_digest=digest(source), create=True)
    assert not (tmp_path / "voyage.atlas.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_jeeves_prompt_preview_is_read_only(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.atlas_propose_preview", "world_id": "voyage",
        "args": {"prompt": "Original cliff road and harbor."},
    })
    assert tool["persisted"] is False
    assert tool["review_required"] is True
    assert tool["result"]["approved"] is False
    assert tool["result"]["world_digest"] == digest(source)
    assert not (tmp_path / "voyage.atlas.json").exists()

@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_malformed_canonical_world_fails_as_typed_error(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    (tmp_path / "voyage.json").write_text("[]")
    with pytest.raises(CanonError, match="expected_object"):
        AtlasStore(tmp_path).propose("voyage", "Map the coast.")
