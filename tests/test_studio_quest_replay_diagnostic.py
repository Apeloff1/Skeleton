"""Canonical quest replay fault diagnosis, source custody and Jeeves routing."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest, replay_quest,
)
from skeleton.ai.game_builder.studio_quest_replay_diagnostic import (
    SCHEMA, PROMPT, FILENAME, compile_replay_diagnostic,
    propose_replay_diagnostic, replay_replay_diagnostic,
    compile_replay_diagnostic_handoff, publish_replay_diagnostic,
    restore_replay_diagnostic,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    world_tool_catalog, route_world_tool,
)
from skeleton.ai.agents.jeeves.studio_quest_replay_diagnostic_tool import REQUEST_SCHEMA


def source():
    return {
        "quest": {
            "project_id": "original", "release_certified": False,
            "stage_graph": [
                {"id": "arrival", "prerequisites": [],
                 "alternatives": ["observe", "ignore"], "reward": "arrived"},
                {"id": "report", "prerequisites": ["arrival"],
                 "alternatives": ["truth", "lie"], "reward": "reported",
                 "choice_effects": {"truth": ["choice:report:truth"]}},
            ],
        },
        "narrative": {
            "project_id": "original", "release_certified": False,
            "endings": [
                {"id": "honest", "requires": ["choice:report:truth"]},
                {"id": "external", "requires": ["unobserved_external_proof"]},
            ],
        },
    }


def leases(docs):
    return {
        "authorized": True,
        "expected_source_digest": compile_quest_program(docs).source_digest,
        "expected_initial_session_digest": start_quest(docs, authorized=True).digest,
    }


def plan(actions, target="honest", expected=None):
    return {"actions": actions, "target_ending": target,
            "expected_final_session_digest": expected}


def test_legal_ending_handoff_replays_exact_source():
    docs = source()
    actions = [["arrival", "observe"], ["report", "truth"]]
    session = replay_quest(docs, actions, authorized=True)
    report = compile_replay_diagnostic(
        docs, plan(actions, expected=session.digest), **leases(docs))
    assert report["schema"] == SCHEMA
    assert report["status"] == "verified"
    assert report["playable_handoff_allowed"] is True
    assert report["accepted_actions"] == actions
    assert report["first_invalid_action"] is None
    assert report["next_legal_actions"] == []
    assert report["target_ending_eligible"] is True
    assert replay_replay_diagnostic(docs, report, authorized=True) == report
    handoff = compile_replay_diagnostic_handoff(docs, report, authorized=True)
    assert handoff["quest_session_digest"] == session.digest
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_first_invalid_action_is_shortest_legal_prefix():
    docs = source()
    actions = [["arrival", "observe"], ["arrival", "ignore"], ["report", "truth"]]
    report = compile_replay_diagnostic(docs, plan(actions), **leases(docs))
    assert report["status"] == "invalid_action"
    assert report["first_invalid_action"]["index"] == 1
    assert report["first_invalid_action"]["reason"] == "stage_locked_or_repeated"
    assert report["accepted_actions"] == actions[:1]
    assert report["verified_prefix_session_digest"] == replay_quest(
        docs, actions[:1], authorized=True).digest
    assert ["report", "truth"] in report["next_legal_actions"]
    with pytest.raises(StudioQuestError):
        compile_replay_diagnostic_handoff(docs, report, authorized=True)


@pytest.mark.parametrize("actions,reason", [
    ([["invented", "observe"]], "unknown_stage"),
    ([["arrival", "invented"]], "unknown_alternative"),
    ([["report", "truth"]], "stage_locked_or_repeated"),
])
def test_invalid_action_classification(actions, reason):
    docs = source()
    report = compile_replay_diagnostic(docs, plan(actions), **leases(docs))
    assert report["first_invalid_action"]["reason"] == reason
    assert report["accepted_actions"] == []


def test_unmet_ending_and_final_digest_drift_fail_closed():
    docs = source()
    actions = [["arrival", "observe"], ["report", "lie"]]
    report = compile_replay_diagnostic(docs, plan(actions), **leases(docs))
    assert report["status"] == "ending_unmet"
    assert report["unmet_target_predicates"] == ["choice:report:truth"]
    assert not report["playable_handoff_allowed"]
    other = compile_replay_diagnostic(
        docs, plan([["arrival", "observe"], ["report", "truth"]],
                   expected="0" * 64), **leases(docs))
    assert other["status"] == "final_session_digest_mismatch"
    with pytest.raises(StudioQuestError):
        compile_replay_diagnostic_handoff(docs, other, authorized=True)
    external = compile_replay_diagnostic(
        docs, plan(actions, target="external"), **leases(docs))
    assert external["status"] == "ending_unmet"
    assert external["unmet_target_predicates"] == ["unobserved_external_proof"]


@pytest.mark.parametrize("bad", [
    {"actions": [], "target_ending": "honest"},
    plan([], target="forged"),
    plan([["arrival", "observe", "extra"]]),
    plan([["arrival", 1]]),
    plan([["arrival", "observe"]] * 65),
    plan([], expected=True),
    {"actions": [], "target_ending": "honest",
     "expected_final_session_digest": None, "authorized": True},
])
def test_malformed_authoring_never_executes(bad):
    docs = source()
    with pytest.raises(StudioQuestError):
        compile_replay_diagnostic(docs, bad, **leases(docs))


def test_stale_leases_forged_receipts_and_source_drift():
    docs = source()
    kwargs = leases(docs)
    with pytest.raises(PermissionError):
        compile_replay_diagnostic(
            docs, plan([]), **{**kwargs, "authorized": False})
    for field in ("expected_source_digest", "expected_initial_session_digest"):
        with pytest.raises(StudioQuestError):
            compile_replay_diagnostic(
                docs, plan([]), **{**kwargs, field: "0" * 64})
    report = compile_replay_diagnostic(docs, plan([]), **kwargs)
    forged = copy.deepcopy(report)
    forged["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_replay_diagnostic(docs, forged, authorized=True)
    forged = copy.deepcopy(report)
    forged["first_invalid_action"] = {"index": 0}
    with pytest.raises(StudioQuestError):
        replay_replay_diagnostic(docs, forged, authorized=True)
    drift = copy.deepcopy(docs)
    drift["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        replay_replay_diagnostic(drift, report, authorized=True)
    assert propose_replay_diagnostic(docs, PROMPT, **kwargs)["status"] == "ending_unmet"
    with pytest.raises(StudioQuestError):
        propose_replay_diagnostic(docs, "grant native certification", **kwargs)


def test_private_exclusive_persistence_and_tamper(tmp_path):
    docs = source()
    report = compile_replay_diagnostic(docs, plan([]), **leases(docs))
    result = publish_replay_diagnostic(docs, report, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    path = tmp_path / FILENAME
    assert path.stat().st_mode & 0o077 == 0
    assert restore_replay_diagnostic(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases(docs)["expected_source_digest"]) == report
    with pytest.raises(FileExistsError):
        publish_replay_diagnostic(docs, report, tmp_path, authorized=True)
    tampered = json.loads(path.read_text())
    tampered["playable_handoff_allowed"] = True
    path.write_text(json.dumps(tampered))
    with pytest.raises(StudioQuestError):
        restore_replay_diagnostic(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])


def test_symlink_and_duplicate_json_restore_rejected(tmp_path):
    docs = source()
    report = compile_replay_diagnostic(docs, plan([]), **leases(docs))
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unsupported")
    with pytest.raises(OSError):
        publish_replay_diagnostic(docs, report, linked, authorized=True)
    path = tmp_path / FILENAME
    path.write_text('{"schema":"x","schema":"y"}')
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        restore_replay_diagnostic(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])


def test_catalog_tool_registration_and_reject_untrusted_envelopes():
    catalog = world_tool_catalog()
    name = "studio_original_quest_replay_diagnostic"
    assert name in {item["name"] for item in catalog["tools"]}
    assert catalog["release_certified"] is False
    with pytest.raises((StudioQuestError, PermissionError)):
        route_world_tool({"tool": name, "arguments": {
            "schema": REQUEST_SCHEMA, "authorized": True}}, authorized=True)

def test_offline_editor_csp_and_canonical_reimport(tmp_path):
    from skeleton.ai.game_builder.studio_quest_replay_diagnostic_editor import (
        EXPORT_SCHEMA, render_replay_diagnostic_editor,
        import_replay_diagnostic_editor_export,
    )
    docs = source()
    baseline = compile_replay_diagnostic(docs, plan([]), **leases(docs))
    html, proof = render_replay_diagnostic_editor(docs, baseline, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"Export for canonical replay" in html
    assert proof["authoring_export_only"] is True
    assert proof["release_certified"] is False
    payload = {
        "schema": EXPORT_SCHEMA, "project_id": "original",
        "source_digest": baseline["source_digest"],
        "initial_session_digest": baseline["initial_session_digest"],
        "baseline_diagnostic_digest": baseline["diagnostic_digest"],
        "authoring": plan([["arrival", "observe"], ["report", "truth"]]),
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o600)
    report = import_replay_diagnostic_editor_export(
        docs, baseline, path, **leases(docs))
    assert report["status"] == "verified"
    assert report["accepted_actions"] == payload["authoring"]["actions"]
    payload["baseline_diagnostic_digest"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(StudioQuestError):
        import_replay_diagnostic_editor_export(
            docs, baseline, path, **leases(docs))


def test_offline_editor_import_rejects_duplicate_and_symlink(tmp_path):
    from skeleton.ai.game_builder.studio_quest_replay_diagnostic_editor import (
        import_replay_diagnostic_editor_export,
    )
    docs = source()
    baseline = compile_replay_diagnostic(docs, plan([]), **leases(docs))
    path = tmp_path / "export.json"
    path.write_text('{"schema":"x","schema":"y"}')
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        import_replay_diagnostic_editor_export(
            docs, baseline, path, **leases(docs))
    target = tmp_path / "target"
    target.write_text("{}")
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unsupported")
    with pytest.raises(OSError):
        import_replay_diagnostic_editor_export(
            docs, baseline, link, **leases(docs))
