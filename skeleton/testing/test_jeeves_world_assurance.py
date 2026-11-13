"""Integrated source-exact scenario/invariant/choice-impact handoff tests."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.assurance import AssuranceStore
from skeleton.jeeves.worlds.assurance_cli import run
from skeleton.jeeves.worlds.choice_impact import ChoiceImpactStore
from skeleton.jeeves.worlds.invariants import InvariantStore
from skeleton.jeeves.worlds.scenario import ScenarioStore
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def world():
    source = propose(
        world_id="assured", premise="An explorer enters a harbor.",
        protagonist="Ari", region="Harbor", goal="Save the lighthouse.",
    )
    source["choices"][0]["grants"] = ["rescued"]
    return source


def setup_upstream(root):
    source = world()
    WorldStore(root).publish(source, create=True)
    scenarios = ScenarioStore(str(root))
    cases = [{
        "id": "lighthouse_saved", "choices": ["pursue_goal"],
        "expect": {"scene": "resolution", "flags": ["rescued"], "ending": True},
    }]
    spec = scenarios.propose("assured", cases)
    first = scenarios.save("assured", spec, expected_world_digest=digest(source))
    approved = scenarios.approve(
        "assured", expected_suite_digest=first, review_note="Reviewed journey.",
    )
    scenarios.compile("assured", expected_suite_digest=approved)
    invariants = InvariantStore(str(root))
    rules = [{
        "id": "rescue_required", "kind": "require_all_at_scene",
        "scene": "resolution", "flags": ["rescued"],
    }]
    spec = invariants.propose("assured", rules)
    first = invariants.save("assured", spec, expected_world_digest=digest(source))
    approved = invariants.approve(
        "assured", expected_suite_digest=first, review_note="Reviewed invariant.",
    )
    invariants.compile("assured", expected_suite_digest=approved)
    ChoiceImpactStore(str(root)).compile(
        "assured", expected_world_digest=digest(source),
    )
    return source


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_full_integrated_playable_and_reverification(tmp_path, capsys):
    source = setup_upstream(tmp_path)
    store = AssuranceStore(str(tmp_path))
    preview = store.preview("assured")
    assert preview["ready_for_compile"]
    assert preview["missing_or_invalid"] == []
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.assurance_preview", "world_id": "assured", "args": {},
    })
    assert tool["persisted"] is False
    assert tool["result"]["ready_for_compile"]
    args = ["--store", str(tmp_path)]
    assert run(args + ["compile", "--world-id", "assured",
                       "--expected-world-digest", digest(source)]) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert store.verify("assured") == receipt
    handoff = json.loads((tmp_path / "assured.assurance.handoff.json").read_text())
    assert handoff["all_source_checks_verified"] is True
    assert set(handoff["assurance_dependencies"]) == {
        "scenario", "invariants", "choice_impact",
    }
    assert "Content-Security-Policy" in (
        tmp_path / "assured.assurance.playable.html"
    ).read_text()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_missing_dependency_never_passes(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AssuranceStore(str(tmp_path))
    preview = store.preview("assured")
    assert not preview["ready_for_compile"]
    assert "scenario_receipt_unverified" in preview["missing_or_invalid"]
    with pytest.raises(CanonError):
        store.compile("assured", expected_world_digest=digest(source))
    assert not (tmp_path / "assured.assurance.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_tampered_upstream_artifact_invalidates_integrated_receipt(tmp_path):
    source = setup_upstream(tmp_path)
    store = AssuranceStore(str(tmp_path))
    store.compile("assured", expected_world_digest=digest(source))
    (tmp_path / "assured.scenario.report.json").write_text("{}")
    with pytest.raises(CanonError, match="assurance_upstream_artifact_mismatch"):
        store.verify("assured")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_world_revision_fails_all_assurance_proofs(tmp_path):
    source = setup_upstream(tmp_path)
    store = AssuranceStore(str(tmp_path))
    store.compile("assured", expected_world_digest=digest(source))
    revised = copy.deepcopy(source)
    revised["scenes"][0]["narrative"] = "A changed harbor."
    WorldStore(tmp_path).publish(revised, expected_digest=digest(source))
    with pytest.raises(CanonError, match="assurance_stale_source"):
        store.compile("assured", expected_world_digest=digest(source))
    with pytest.raises(CanonError):
        store.verify("assured")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_integrated_artifact_symlink_and_lock_fail_closed(tmp_path):
    source = setup_upstream(tmp_path)
    store = AssuranceStore(str(tmp_path))
    (tmp_path / "assured.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.compile("assured", expected_world_digest=digest(source))
    (tmp_path / "assured.lock").unlink()
    store.compile("assured", expected_world_digest=digest(source))
    report = tmp_path / "assured.assurance.handoff.json"
    report.unlink()
    report.symlink_to(tmp_path / "assured.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("assured")
