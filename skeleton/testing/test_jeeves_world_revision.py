"""Revision impact classification, reviewed custody and tamper fixtures."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.revision import RevisionStore, analyze_revision
from skeleton.jeeves.worlds.revision_cli import run
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose, prove


def world():
    return propose(world_id="isles", premise="A cartographer crosses the isles.",
                   protagonist="Ari", region="Isles", goal="Chart a safe passage.")


def changed(source, causal=False):
    target = copy.deepcopy(source)
    target["scenes"][0]["narrative"] = "A new coastline emerges."
    if causal:
        target["choices"][0]["grants"] = ["map"]
    prove(target)
    return target


def test_presentation_only_revision_has_no_causal_claim():
    old = world()
    report = analyze_revision(old, changed(old))
    assert report["review_class"] == "presentation_review"
    assert report["causal_change"] is False
    assert report["scenes"]["modified"][0]["fields"] == ["narrative"]
    assert report["new_world_digest"] == digest(changed(old))


def test_causal_choice_change_is_explicit():
    old = world()
    report = analyze_revision(old, changed(old, causal=True))
    assert report["causal_change"]
    assert report["review_class"] == "causal_review_required"
    assert report["choices"]["modified"][0]["fields"] == ["grants"]
    assert report["choices"]["modified"][0]["causal"] is True


def test_addition_removal_and_ending_changes_reported():
    old = world()
    new = copy.deepcopy(old)
    new["scenes"].append({"id": "detour", "title": "Detour",
                          "narrative": "A hidden crossing."})
    new["choices"].append({"id": "sidepath", "from": "opening",
                           "to": "detour", "label": "Detour",
                           "requires": [], "grants": []})
    new["choices"].append({"id": "rejoin", "from": "detour",
                           "to": "resolution", "label": "Rejoin",
                           "requires": [], "grants": []})
    prove(new)
    report = analyze_revision(old, new)
    assert report["scenes"]["added"] == ["detour"]
    assert report["choices"]["added"] == ["rejoin", "sidepath"]
    assert report["causal_change"]


def test_source_identity_and_same_digest_fail_closed():
    old = world()
    with pytest.raises(CanonError, match="revision_unchanged"):
        analyze_revision(old, old)
    new = changed(old)
    new["id"] = "another"
    with pytest.raises(CanonError, match="revision_identity_mismatch"):
        analyze_revision(old, new)


def test_deterministic_reordering_and_no_private_prose_in_report():
    old = world()
    new = changed(old)
    result = analyze_revision(old, new)
    assert result == analyze_revision(copy.deepcopy(old), copy.deepcopy(new))
    encoded = json.dumps(result)
    assert "A new coastline emerges." not in encoded
    assert "A cartographer crosses the isles." not in encoded
    assert len(result["playable_sha256"]) == 64


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_operator_review_and_verified_playable(tmp_path):
    old = world()
    new = changed(old)
    WorldStore(tmp_path).publish(new, create=True)
    store = RevisionStore(str(tmp_path))
    impact = store.preview("isles", old)
    with pytest.raises(CanonError, match="revision_stale_preview"):
        store.review("isles", old, expected_impact_digest="0" * 64,
                     note="Reviewed.")
    receipt = store.review("isles", old, expected_impact_digest=digest(impact),
                           note="Reviewed original world.")
    assert receipt["impact_digest"] == digest(impact)
    assert store.verify("isles", old) == receipt
    page = (tmp_path / "isles.revision.playable.html").read_text()
    assert "Content-Security-Policy" in page


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_changed_source_invalidates_receipt(tmp_path):
    old = world()
    new = changed(old)
    worlds = WorldStore(tmp_path)
    worlds.publish(new, create=True)
    store = RevisionStore(str(tmp_path))
    store.review("isles", old, expected_impact_digest=digest(store.preview("isles", old)),
                 note="Reviewed.")
    newer = copy.deepcopy(new)
    newer["scenes"][0]["title"] = "New title"
    worlds.publish(newer, expected_digest=digest(new))
    with pytest.raises(CanonError, match="revision_receipt_mismatch"):
        store.verify("isles", old)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_artifact_tamper_and_symlink_fail_closed(tmp_path):
    old = world()
    new = changed(old)
    WorldStore(tmp_path).publish(new, create=True)
    store = RevisionStore(str(tmp_path))
    store.review("isles", old, expected_impact_digest=digest(store.preview("isles", old)),
                 note="Reviewed.")
    path = tmp_path / "isles.revision.impact.json"
    path.write_text("{}")
    with pytest.raises(CanonError, match="revision_artifact_mismatch"):
        store.verify("isles", old)
    path.unlink()
    path.symlink_to(tmp_path / "isles.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("isles", old)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_lock_conflict(tmp_path):
    old = world()
    WorldStore(tmp_path).publish(changed(old), create=True)
    (tmp_path / "isles.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        RevisionStore(str(tmp_path)).review(
            "isles", old, expected_impact_digest="0" * 64, note="Reviewed.")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_preview_review_verify(tmp_path, capsys):
    old = world()
    WorldStore(tmp_path).publish(changed(old), create=True)
    old_file = tmp_path / "old-world.json"
    old_file.write_text(json.dumps(old))
    base = ["--store", str(tmp_path)]
    opts = ["--world-id", "isles", "--old-world-file", str(old_file)]
    assert run(base + ["preview"] + opts) == 0
    impact = json.loads(capsys.readouterr().out)
    assert impact["impact"]["review_class"] == "presentation_review"
    assert run(base + ["review"] + opts + [
        "--expected-impact-digest", impact["impact_digest"],
        "--review-note", "Reviewed."]) == 0
    capsys.readouterr()
    assert run(base + ["verify"] + opts) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "isles"
