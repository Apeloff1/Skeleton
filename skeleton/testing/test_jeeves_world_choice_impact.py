"""End-to-end terminal consequence proof, custody and CLI regressions."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.choice_impact import ChoiceImpactStore, analyze_choice_impact
from skeleton.jeeves.worlds.choice_impact_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def branching_world():
    world = propose(
        world_id="impact", premise="A courier finds two routes.",
        protagonist="Mira", region="Crossroads", goal="Reach home.",
    )
    world["scenes"] += [
        {"id": "safe", "title": "Safe road", "narrative": "Arrive safely."},
        {"id": "risky", "title": "Risky road", "narrative": "Arrive changed."},
    ]
    world["choices"] = [
        {"id": "safe_way", "from": "opening", "to": "safe",
         "label": "Take the safe road", "requires": [], "grants": []},
        {"id": "risky_way", "from": "opening", "to": "risky",
         "label": "Take the risky road", "requires": [], "grants": ["scar"]},
        {"id": "return_safe", "from": "safe", "to": "resolution",
         "label": "Return home", "requires": [], "grants": []},
        {"id": "return_risky", "from": "risky", "to": "resolution",
         "label": "Return home changed", "requires": [], "grants": []},
    ]
    prove(world)
    return world


def choice(report, name):
    return next(row for row in report["choices"] if row["choice_id"] == name)


def test_distinct_terminal_flags_and_shortest_canonical_witness():
    report = analyze_choice_impact(branching_world())
    assert report["states_explored"] == 5
    assert choice(report, "safe_way")["classification"] == "terminal_distinct"
    assert choice(report, "risky_way")["classification"] == "terminal_distinct"
    assert choice(report, "safe_way")["witness"] == ["safe_way"]
    assert choice(report, "return_safe")["classification"] == "no_peer_choice"
    assert choice(report, "return_risky")["terminal_outcomes"] == ["resolution:scar"]


def test_outcome_equivalence_not_misrepresented_as_narrative_equivalence():
    world = branching_world()
    world["choices"][1]["grants"] = []
    report = analyze_choice_impact(world)
    assert choice(report, "safe_way")["classification"] == "terminal_outcome_equivalent"
    assert choice(report, "risky_way")["classification"] == "terminal_outcome_equivalent"
    assert "does not imply identical narrative" in report["classification_note"]


def test_unreachable_requires_flag_is_not_a_valid_choice():
    world = branching_world()
    world["choices"].append({
        "id": "locked", "from": "opening", "to": "safe",
        "label": "Present a missing key", "requires": ["missing"], "grants": [],
    })
    report = analyze_choice_impact(world)
    assert choice(report, "locked")["classification"] == "unreachable"
    assert choice(report, "locked")["witness"] is None


def test_deterministic_under_choice_order_and_deepcopy():
    world = branching_world()
    baseline = analyze_choice_impact(world)
    other = copy.deepcopy(world)
    other["choices"].reverse()
    assert analyze_choice_impact(other) == baseline


def test_cycle_fixed_point_reaches_earned_flag_outcome():
    world = branching_world()
    world["choices"].append({
        "id": "loop", "from": "safe", "to": "opening",
        "label": "Reconsider", "requires": [], "grants": ["insight"],
    })
    report = analyze_choice_impact(world)
    assert report["states_explored"] > 5
    assert "resolution:insight" in choice(report, "safe_way")["terminal_outcomes"]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_cli_preview_compile_verify_and_typed_jeeves_tool(tmp_path, capsys):
    world = branching_world()
    WorldStore(tmp_path).publish(world, create=True)
    args = ["--store", str(tmp_path)]
    assert run(args + ["preview", "--world-id", "impact"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["world_digest"] == digest(world)
    request = {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.choice_impact_preview", "world_id": "impact", "args": {},
    }
    tool = invoke_world_tool(str(tmp_path), request)
    assert tool["persisted"] is False
    assert tool["result"]["world_digest"] == digest(world)
    assert run(args + ["compile", "--world-id", "impact",
                       "--expected-world-digest", digest(world)]) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert receipt["world_digest"] == digest(world)
    assert run(args + ["verify", "--world-id", "impact"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"] == receipt
    html = (tmp_path / "impact.choice-impact.playable.html").read_text()
    assert "Content-Security-Policy" in html


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_strict_distinct_policy_blocks_equivalent_without_receipt(tmp_path):
    world = branching_world()
    world["choices"][1]["grants"] = []
    WorldStore(tmp_path).publish(world, create=True)
    with pytest.raises(CanonError, match="choice_impact_equivalent_choices"):
        ChoiceImpactStore(str(tmp_path)).compile(
            "impact", expected_world_digest=digest(world), require_distinct=True,
        )
    assert not (tmp_path / "impact.choice-impact.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_source_and_tampered_artifacts_fail_closed(tmp_path):
    world = branching_world()
    worlds = WorldStore(tmp_path)
    worlds.publish(world, create=True)
    store = ChoiceImpactStore(str(tmp_path))
    with pytest.raises(CanonError, match="choice_impact_stale_source"):
        store.compile("impact", expected_world_digest="0" * 64)
    receipt = store.compile("impact", expected_world_digest=digest(world))
    assert store.verify("impact") == receipt
    (tmp_path / "impact.choice-impact.report.json").write_text("{}")
    with pytest.raises(CanonError, match="choice_impact_artifact_mismatch"):
        store.verify("impact")
    revised = copy.deepcopy(world)
    revised["scenes"][0]["narrative"] = "A different opening."
    worlds.publish(revised, expected_digest=digest(world))
    with pytest.raises(CanonError, match="choice_impact_receipt_mismatch"):
        store.verify("impact")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_lock_and_symlinked_artifact_rejected(tmp_path):
    world = branching_world()
    WorldStore(tmp_path).publish(world, create=True)
    store = ChoiceImpactStore(str(tmp_path))
    (tmp_path / "impact.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.compile("impact", expected_world_digest=digest(world))
    (tmp_path / "impact.lock").unlink()
    store.compile("impact", expected_world_digest=digest(world))
    report = tmp_path / "impact.choice-impact.report.json"
    report.unlink()
    report.symlink_to(tmp_path / "impact.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("impact")
