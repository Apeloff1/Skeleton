"""Source-bound authored scenario acceptance suite integration regressions."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.scenario import ScenarioStore, run_suite, validate_suite
from skeleton.jeeves.worlds.scenario_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def world():
    return propose(
        world_id="scenarios", premise="A pilot explores an ancient beacon.",
        protagonist="Sia", region="North coast", goal="Light the beacon.",
    )


def cases():
    return [
        {"id": "before_departure", "choices": [],
         "expect": {"scene": "opening", "flags": [], "ending": False}},
        {"id": "completed_journey", "choices": ["pursue_goal"],
         "expect": {"scene": "resolution", "flags": [], "ending": True}},
    ]


def test_proposal_requires_explicit_review_and_has_replayable_expectations(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = ScenarioStore(str(tmp_path))
    suite = store.propose("scenarios", cases())
    assert suite["approved"] is False
    report = run_suite(suite, source)
    assert report["total"] == 2 and report["passed"] == 2
    assert report["complete"] is True
    assert validate_suite(suite, source) == suite


def test_failed_assertions_are_reported_not_rewritten(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = ScenarioStore(str(tmp_path))
    incorrect = cases()
    incorrect[1]["expect"]["scene"] = "opening"
    incorrect[1]["expect"]["ending"] = False
    suite = store.propose("scenarios", incorrect)
    report = run_suite(suite, source)
    assert report["failed"] == 1
    assert report["cases"][1]["observed"]["scene"] == "resolution"
    assert report["cases"][1]["passed"] is False


def test_invalid_trace_is_reported_without_claiming_success(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    bad = cases()
    bad[1]["choices"] = ["pursue_goal", "pursue_goal"]
    suite = ScenarioStore(str(tmp_path)).propose("scenarios", bad)
    report = run_suite(suite, source)
    assert report["cases"][1]["error"] == "session_after_ending"
    assert report["complete"] is False


def test_duplicate_ids_noncanonical_flags_and_wrong_source_are_rejected(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    suite = ScenarioStore(str(tmp_path)).propose("scenarios", cases())
    dup = copy.deepcopy(suite)
    dup["cases"][1]["id"] = dup["cases"][0]["id"]
    with pytest.raises(CanonError, match="scenario_duplicate_case"):
        validate_suite(dup, source)
    stale = copy.deepcopy(suite)
    stale["world_digest"] = "0" * 64
    with pytest.raises(CanonError, match="scenario_source_lease_mismatch"):
        validate_suite(stale, source)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_save_approve_compile_verify_and_read_only_jeeves(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = ScenarioStore(str(tmp_path))
    suite = store.propose("scenarios", cases())
    suite_digest = store.save(
        "scenarios", suite, expected_world_digest=digest(source),
    )
    with pytest.raises(CanonError, match="scenario_review_required"):
        store.compile("scenarios", expected_suite_digest=suite_digest)
    tool = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.scenario_preview", "world_id": "scenarios", "args": {},
    })
    assert tool["persisted"] is False
    assert tool["result"]["complete"] is True
    approved_digest = store.approve(
        "scenarios", expected_suite_digest=suite_digest,
        review_note="Reviewed each player path against the authored ending.",
    )
    receipt = store.compile("scenarios", expected_suite_digest=approved_digest)
    assert store.verify("scenarios") == receipt
    html = (tmp_path / "scenarios.scenario.playable.html").read_text()
    assert "Content-Security-Policy" in html


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_lease_rejected_without_silent_overwrite(tmp_path):
    source = world()
    worlds = WorldStore(tmp_path)
    worlds.publish(source, create=True)
    store = ScenarioStore(str(tmp_path))
    suite = store.propose("scenarios", cases())
    with pytest.raises(CanonError, match="scenario_stale_source"):
        store.save("scenarios", suite, expected_world_digest="0" * 64)
    first = store.save("scenarios", suite, expected_world_digest=digest(source))
    with pytest.raises(CanonError, match="scenario_already_exists"):
        store.save("scenarios", suite, expected_world_digest=digest(source))
    with pytest.raises(CanonError, match="scenario_stale_suite"):
        store.approve("scenarios", expected_suite_digest="0" * 64, review_note="review")
    assert store.approve("scenarios", expected_suite_digest=first,
                         review_note="Accepted.") != first


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_tamper_stale_world_and_symlink_fail_closed(tmp_path):
    source = world()
    worlds = WorldStore(tmp_path)
    worlds.publish(source, create=True)
    store = ScenarioStore(str(tmp_path))
    suite = store.propose("scenarios", cases())
    first = store.save("scenarios", suite, expected_world_digest=digest(source))
    approved = store.approve("scenarios", expected_suite_digest=first,
                             review_note="Reviewed.")
    store.compile("scenarios", expected_suite_digest=approved)
    report = tmp_path / "scenarios.scenario.report.json"
    report.write_text("{}")
    with pytest.raises(CanonError, match="scenario_artifact_mismatch"):
        store.verify("scenarios")
    report.unlink()
    report.symlink_to(tmp_path / "scenarios.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("scenarios")
    report.unlink()
    revised = copy.deepcopy(source)
    revised["scenes"][0]["narrative"] = "New source."
    worlds.publish(revised, expected_digest=digest(source))
    with pytest.raises(CanonError, match="scenario_source_lease_mismatch"):
        store.verify("scenarios")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_cli_operator_flow(tmp_path, capsys):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases()))
    args = ["--store", str(tmp_path)]
    assert run(args + ["propose", "--world-id", "scenarios",
                       "--cases-file", str(path)]) == 0
    capsys.readouterr()
    assert run(args + ["save", "--world-id", "scenarios",
                       "--cases-file", str(path),
                       "--expected-world-digest", digest(source)]) == 0
    initial = json.loads(capsys.readouterr().out)["suite_digest"]
    assert run(args + ["approve", "--world-id", "scenarios",
                       "--expected-suite-digest", initial,
                       "--review-note", "Reviewed."]) == 0
    approved = json.loads(capsys.readouterr().out)["suite_digest"]
    assert run(args + ["compile", "--world-id", "scenarios",
                       "--expected-suite-digest", approved]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "scenarios"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["world_id"] == "scenarios"
