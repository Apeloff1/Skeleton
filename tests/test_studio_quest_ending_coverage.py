"""Deterministic and adversarial canonical quest ending coverage fixtures."""
from __future__ import annotations
import copy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_ending_coverage import (
    FILENAME, PROMPT, compile_ending_coverage,
    compile_ending_coverage_handoff, propose_ending_coverage,
    publish_ending_coverage, render_ending_coverage_html,
    replay_ending_coverage, restore_ending_coverage,
)
from skeleton.ai.agents.jeeves import studio_quest_ending_coverage_tool as tool


def docs():
    return {
        "quest": {"project_id": "test-world", "release_certified": False,
                  "stage_graph": [{
                      "id": "gate", "prerequisites": [],
                      "alternatives": ["mercy", "force"],
                      "reward": "gate_open",
                      "choice_effects": {
                          "mercy": ["choice:gate:mercy"],
                          "force": ["choice:gate:force"],
                      },
                  }]},
        "narrative": {
            "project_id": "test-world", "release_certified": False,
            "endings": [
                {"id": "peace", "requires": ["choice:gate:mercy"]},
                {"id": "war", "requires": ["choice:gate:force"]},
            ],
        },
    }


def leases(source):
    return {"authorized": True,
            "expected_source_digest": compile_quest_program(source).source_digest,
            "expected_initial_session_digest":
                start_quest(source, authorized=True).digest}


def plan(**overrides):
    return {**{"initial_actions": [], "target_endings": ["peace", "war"],
               "max_states": 32, "max_depth": 1}, **overrides}


def test_two_mutually_exclusive_endings_have_independent_witnesses():
    source = docs()
    report = compile_ending_coverage(source, plan(), **leases(source))
    assert report["coverage_complete"] is True
    assert report["status"] == "all_targets_witnessed"
    assert {w["ending_id"] for w in report["witnesses"]} == {"peace", "war"}
    assert {tuple(w["actions"][0]) for w in report["witnesses"]} == {
        ("gate", "mercy"), ("gate", "force")}
    assert replay_ending_coverage(source, report, authorized=True) == report
    handoff = compile_ending_coverage_handoff(source, report, authorized=True)
    assert handoff["canonical_quest_replay_verified"] is True
    assert handoff["native_gameplay_verified"] is False
    assert b"script-src 'none'" in render_ending_coverage_html(
        source, report, authorized=True)


def test_unknown_budget_is_not_a_playable_proof():
    source = docs()
    report = compile_ending_coverage(source, plan(max_states=1), **leases(source))
    assert report["status"] == "inconclusive_budget_exhausted"
    assert report["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_ending_coverage_handoff(source, report, authorized=True)


def test_exhaustive_negative_coverage():
    source = docs()
    source["narrative"]["endings"].append(
        {"id": "impossible", "requires": ["external_evidence"]})
    report = compile_ending_coverage(
        source, plan(target_endings=["impossible"]), **leases(source))
    assert report["status"] == "unreachable_in_exhaustive_search"
    assert report["search_exhaustive"] is True
    assert report["uncovered_endings"] == ["impossible"]


def test_forgery_drift_and_missing_authority_rejected():
    source = docs()
    report = compile_ending_coverage(source, plan(), **leases(source))
    forged = copy.deepcopy(report)
    forged["witnesses"][0]["actions"] = [["gate", "force"]]
    with pytest.raises(StudioQuestError):
        replay_ending_coverage(source, forged, authorized=True)
    drift = copy.deepcopy(source)
    drift["quest"]["stage_graph"][0]["reward"] = "different"
    with pytest.raises(StudioQuestError):
        replay_ending_coverage(drift, report, authorized=True)
    with pytest.raises(PermissionError):
        compile_ending_coverage(
            source, plan(), **{**leases(source), "authorized": False})


def test_private_persistence_restore_and_symlink_guard(tmp_path):
    source = docs()
    report = compile_ending_coverage(source, plan(), **leases(source))
    published = publish_ending_coverage(source, report, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert (tmp_path / FILENAME).stat().st_mode & 0o077 == 0
    restored = restore_ending_coverage(
        source, tmp_path, authorized=True,
        expected_source_digest=report["source_digest"])
    assert restored == report
    with pytest.raises(FileExistsError):
        publish_ending_coverage(source, report, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_ending_coverage(
            source, tmp_path, authorized=True,
            expected_source_digest=report["source_digest"])


def test_typed_prompt_and_jeeves_router_adapter(monkeypatch):
    source = docs()
    assert propose_ending_coverage(source, PROMPT, **leases(source))[
        "coverage_complete"] is True
    monkeypatch.setattr(tool, "read_blueprint", lambda _: source)
    request = {"schema": tool.REQUEST_SCHEMA, "project_id": "test-world",
               "authoring": plan(),
               "expected_source_digest": leases(source)["expected_source_digest"],
               "expected_initial_session_digest":
                   leases(source)["expected_initial_session_digest"]}
    with pytest.raises(PermissionError):
        tool.execute_quest_ending_coverage_tool(request, authorized=False)
    result = tool.execute_quest_ending_coverage_tool(request, authorized=True)
    assert result["detail"]["coverage_complete"] is True
    assert result["file_write_performed"] is False
    with pytest.raises(StudioQuestError):
        tool.execute_quest_ending_coverage_tool(
            {**request, "allow_authoring": True}, authorized=True)


def test_duplicate_json_evidence_fails_closed(tmp_path):
    source = docs()
    (tmp_path / FILENAME).write_text('{"schema":"one","schema":"two"}')
    with pytest.raises(StudioQuestError):
        restore_ending_coverage(
            source, tmp_path, authorized=True,
            expected_source_digest=leases(source)["expected_source_digest"])


def test_router_exposes_read_only_ending_coverage(monkeypatch):
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    source = docs()
    monkeypatch.setattr(tool, "read_blueprint", lambda _: source)
    lease = leases(source)
    request = {
        "tool": "studio_original_quest_ending_coverage",
        "arguments": {
            "schema": tool.REQUEST_SCHEMA, "project_id": "test-world",
            "authoring": plan(),
            "expected_source_digest": lease["expected_source_digest"],
            "expected_initial_session_digest":
                lease["expected_initial_session_digest"],
        },
    }
    catalog = world_tool_catalog()
    descriptor = next(
        item for item in catalog["tools"]
        if item["name"] == request["tool"])
    assert descriptor["explicit_authoring_permission_required"] is False
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=False)
    result = route_world_tool(request, authorized=True)
    assert result["file_write_performed"] is False
    assert result["result"]["detail"]["coverage_complete"] is True
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        route_world_tool({
            **request, "arguments": {
                **request["arguments"], "allow_authoring": True,
            },
        }, authorized=True)


def test_operator_cli_source_lease_and_handoff(monkeypatch, tmp_path, capsys):
    from scripts import studio_quest_ending_coverage_cli as cli
    source = docs()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source)
    lease = leases(source)
    args = [
        "--project", "test-world",
        "--expected-source", lease["expected_source_digest"],
        "--expected-session", lease["expected_initial_session_digest"],
        "--prompt", "--playable", "--publish", str(tmp_path),
    ]
    assert cli.main(args) == 0
    response = __import__("json").loads(capsys.readouterr().out)
    assert response["coverage"]["coverage_complete"] is True
    assert response["playable_handoff"]["canonical_quest_replay_verified"] is True
    assert response["file_write_performed"] is True
    assert (tmp_path / FILENAME).is_file()
    restored_args = [
        "--project", "test-world",
        "--expected-source", lease["expected_source_digest"],
        "--expected-session", lease["expected_initial_session_digest"],
        "--restore", str(tmp_path),
    ]
    assert cli.main(restored_args) == 0
    restored = __import__("json").loads(capsys.readouterr().out)
    assert restored["coverage"] == response["coverage"]
    assert restored["file_write_performed"] is False
