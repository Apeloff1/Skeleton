"""Exhaustive state invariant proof, reviewed persistence and CLI regression."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.invariants import InvariantStore, prove_invariants
from skeleton.jeeves.worlds.invariants_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose, prove


def world():
    data = propose(
        world_id="guarded", premise="A traveler chooses a route.",
        protagonist="Lena", region="Border", goal="Reach the lighthouse.",
    )
    data["scenes"].insert(1, {
        "id": "crossing", "title": "Crossing", "narrative": "Cross the border.",
    })
    data["choices"] = [
        {"id": "earn_pass", "from": "opening", "to": "crossing",
         "label": "Earn the pass", "requires": [], "grants": ["pass"]},
        {"id": "finish", "from": "crossing", "to": "resolution",
         "label": "Complete the journey", "requires": ["pass"], "grants": []},
    ]
    prove(data)
    return data


def rules():
    return [
        {"id": "ending_has_pass", "kind": "require_any_at_ending",
         "scene": "resolution", "flags": ["pass"]},
        {"id": "crossing_requires_pass", "kind": "require_all_at_scene",
         "scene": "crossing", "flags": ["pass"]},
        {"id": "opening_no_pass", "kind": "forbid_any_at_scene",
         "scene": "opening", "flags": ["pass"]},
    ]


def test_exhaustive_proof_replay_and_determinism(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = InvariantStore(str(tmp_path))
    spec = store.propose("guarded", rules())
    report = prove_invariants(spec, source)
    assert report["complete"]
    assert report["states_explored"] == 3
    assert all(row["status"] == "passed" for row in report["rules"])
    other = copy.deepcopy(source)
    other["choices"].reverse()
    assert prove_invariants(spec, other) == report


def test_violation_witness_replays_actual_flag_state(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    bad = rules()
    bad[0]["flags"] = ["pass"]
    bad[0]["kind"] = "forbid_any_at_scene"
    spec = InvariantStore(str(tmp_path)).propose("guarded", bad)
    report = prove_invariants(spec, source)
    assert not report["complete"]
    violation = next(r for r in report["rules"] if r["id"] == "ending_has_pass")
    assert violation["status"] == "violation"
    assert violation["violation_witness"] == ["earn_pass", "finish"]
    assert violation["violation_state"]["flags"] == ["pass"]


def test_unexercised_rule_never_silently_passes(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    # All scenes in a valid world are reachable, but a rule targeting a
    # nonexistent scene is rejected rather than passing vacuously.
    bad = rules()
    bad[0]["scene"] = "missing"
    with pytest.raises(CanonError, match="invariant_unknown_scene"):
        InvariantStore(str(tmp_path)).propose("guarded", bad)


def test_global_invariant_detects_jointly_earned_flags(tmp_path):
    source = world()
    source["choices"][0]["grants"] = ["key", "pass"]
    WorldStore(tmp_path).publish(source, create=True)
    spec = InvariantStore(str(tmp_path)).propose("guarded", [
        {"id": "never_both", "kind": "forbid_all_flags",
         "scene": None, "flags": ["key", "pass"]},
    ])
    report = prove_invariants(spec, source)
    assert report["rules"][0]["status"] == "violation"
    assert report["rules"][0]["violation_witness"] == ["earn_pass"]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_operator_approval_compilation_verification_and_jeeves(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = InvariantStore(str(tmp_path))
    spec = store.propose("guarded", rules())
    first = store.save("guarded", spec, expected_world_digest=digest(source))
    with pytest.raises(CanonError, match="invariant_review_required"):
        store.compile("guarded", expected_suite_digest=first)
    preview = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.invariants_preview", "world_id": "guarded", "args": {},
    })
    assert preview["persisted"] is False
    assert preview["result"]["complete"]
    approved = store.approve(
        "guarded", expected_suite_digest=first, review_note="Continuity verified.",
    )
    receipt = store.compile("guarded", expected_suite_digest=approved)
    assert store.verify("guarded") == receipt
    assert "Content-Security-Policy" in (
        tmp_path / "guarded.invariants.playable.html"
    ).read_text()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_fail_closed_bad_proof_and_stale_lease(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = InvariantStore(str(tmp_path))
    bad = rules()
    bad[0]["kind"] = "forbid_any_at_scene"
    spec = store.propose("guarded", bad)
    with pytest.raises(CanonError, match="invariant_stale_source"):
        store.save("guarded", spec, expected_world_digest="0" * 64)
    first = store.save("guarded", spec, expected_world_digest=digest(source))
    with pytest.raises(CanonError, match="invariant_proof_failed"):
        store.approve("guarded", expected_suite_digest=first, review_note="review")
    assert not (tmp_path / "guarded.invariants.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_receipt_tamper_symlink_and_revision_rejected(tmp_path):
    source = world()
    worlds = WorldStore(tmp_path)
    worlds.publish(source, create=True)
    store = InvariantStore(str(tmp_path))
    spec = store.propose("guarded", rules())
    first = store.save("guarded", spec, expected_world_digest=digest(source))
    approved = store.approve("guarded", expected_suite_digest=first,
                             review_note="Approved.")
    store.compile("guarded", expected_suite_digest=approved)
    report = tmp_path / "guarded.invariants.report.json"
    report.write_text("{}")
    with pytest.raises(CanonError, match="invariant_artifact_mismatch"):
        store.verify("guarded")
    report.unlink()
    report.symlink_to(tmp_path / "guarded.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("guarded")
    report.unlink()
    revised = copy.deepcopy(source)
    revised["scenes"][0]["narrative"] = "New source."
    worlds.publish(revised, expected_digest=digest(source))
    with pytest.raises(CanonError, match="invariant_world_lease_mismatch"):
        store.verify("guarded")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_cli_review_flow(tmp_path, capsys):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    file = tmp_path / "rules.json"
    file.write_text(json.dumps(rules()))
    args = ["--store", str(tmp_path)]
    assert run(args + ["propose", "--world-id", "guarded",
                       "--rules-file", str(file)]) == 0
    capsys.readouterr()
    assert run(args + ["save", "--world-id", "guarded",
                       "--rules-file", str(file),
                       "--expected-world-digest", digest(source)]) == 0
    first = json.loads(capsys.readouterr().out)["suite_digest"]
    assert run(args + ["approve", "--world-id", "guarded",
                       "--expected-suite-digest", first,
                       "--review-note", "Reviewed."]) == 0
    approved = json.loads(capsys.readouterr().out)["suite_digest"]
    assert run(args + ["compile", "--world-id", "guarded",
                       "--expected-suite-digest", approved]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "guarded"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "guarded"
