"""Deterministic source-leased quest counterfactual regression fixtures."""
from __future__ import annotations
import copy
import json
import os
import stat

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_consequence_diff import (
    FILENAME, PROMPT, compile_quest_consequence_diff,
    propose_quest_consequence_diff, replay_quest_consequence_diff,
    compile_quest_consequence_handoff, render_quest_consequence_html,
    publish_quest_consequence_diff, restore_quest_consequence_diff,
)
from skeleton.ai.agents.jeeves.studio_quest_consequence_tool import (
    REQUEST_SCHEMA, execute_quest_consequence_tool, quest_consequence_tool_schema,
)


def source():
    return {
        "quest": {
            "project_id": "original", "release_certified": False,
            "stage_graph": [{
                "id": "gate", "prerequisites": [],
                "alternatives": ["mercy", "force"], "reward": "gate_open",
                "choice_effects": {
                    "mercy": ["choice:gate:mercy"],
                    "force": ["choice:gate:force"],
                },
            }],
        },
        "narrative": {
            "project_id": "original", "release_certified": False,
            "endings": [
                {"id": "peace", "requires": ["choice:gate:mercy"]},
                {"id": "war", "requires": ["choice:gate:force"]},
            ],
        },
    }


def leases(documents):
    return {
        "authorized": True,
        "expected_source_digest": compile_quest_program(documents).source_digest,
        "expected_initial_session_digest": start_quest(
            documents, authorized=True).digest,
    }


def fork():
    return {"baseline_actions": [["gate", "mercy"]],
            "candidate_actions": [["gate", "force"]]}


def test_deterministic_replay_and_ending_delta():
    docs = source()
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    assert report["ending_delta"]["lost"] == ["peace"]
    assert report["ending_delta"]["gained"] == ["war"]
    assert report["facts_delta"]["lost"] == ["choice:gate:mercy"]
    assert report["facts_delta"]["gained"] == ["choice:gate:force"]
    assert report["first_divergence_index"] == 0
    assert replay_quest_consequence_diff(docs, report, authorized=True) == report
    assert compile_quest_consequence_diff(docs, fork(), **leases(docs)) == report
    handoff = compile_quest_consequence_handoff(docs, report, authorized=True)
    assert handoff["consequence_receipt_digest"] == report["receipt_digest"]
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_prompt_requires_real_authored_fork():
    docs = source()
    assert propose_quest_consequence_diff(docs, PROMPT, **leases(docs))["authoring"] == fork()
    with pytest.raises(StudioQuestError):
        propose_quest_consequence_diff(docs, "invent an ending", **leases(docs))
    docs["quest"]["stage_graph"][0]["alternatives"] = ["mercy"]
    with pytest.raises(StudioQuestError):
        propose_quest_consequence_diff(docs, PROMPT, **leases(docs))


@pytest.mark.parametrize("authoring", [
    {}, {"baseline_actions": [], "candidate_actions": [], "extra": 1},
    {"baseline_actions": [], "candidate_actions": []},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["gate", "mercy"]]},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["gate", True]]},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["gate", "unknown"]]},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["missing", "force"]]},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["gate", "force", "x"]]},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": "gate"},
    {"baseline_actions": [["gate", "mercy"]], "candidate_actions": [["gate", "force"]]*65},
])
def test_invalid_authoring_fails_closed(authoring):
    docs = source()
    with pytest.raises(StudioQuestError):
        compile_quest_consequence_diff(docs, authoring, **leases(docs))


def test_leases_and_authority_fail_closed():
    docs = source()
    for key, value in [
        ("authorized", False),
        ("expected_source_digest", "0"*64),
        ("expected_initial_session_digest", "0"*64),
    ]:
        with pytest.raises((StudioQuestError, PermissionError)):
            compile_quest_consequence_diff(docs, fork(),
                                           **dict(leases(docs), **{key: value}))


def test_tamper_and_type_substitution_are_rejected():
    docs = source()
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    for key, value in [
        ("ending_delta", {"lost": [], "gained": ["war"], "retained": []}),
        ("release_certified", True),
        ("canonical_quest_replay_verified", 1),
        ("first_divergence_index", True),
        ("receipt_digest", "0"*64),
    ]:
        changed = copy.deepcopy(report)
        changed[key] = value
        with pytest.raises(StudioQuestError):
            replay_quest_consequence_diff(docs, changed, authorized=True)
    docs["narrative"]["endings"][0]["id"] = "altered"
    with pytest.raises(StudioQuestError):
        replay_quest_consequence_diff(docs, report, authorized=True)


def test_unfinished_branch_never_handoffs():
    docs = source()
    report = compile_quest_consequence_diff(
        docs, {"baseline_actions": [], "candidate_actions": [["gate", "force"]]},
        **leases(docs))
    assert report["both_branches_have_authored_ending"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_consequence_handoff(docs, report, authorized=True)


def test_html_escapes_untrusted_authored_ending():
    docs = source()
    docs["narrative"]["endings"][0]["id"] = "<script>alert(1)</script>"
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    html = render_quest_consequence_html(docs, report, authorized=True)
    assert b"script-src 'none'" in html
    assert b"&lt;script&gt;" in html
    assert b"<script>alert(1)</script>" not in html


def test_private_publish_restore_and_symlink_rejection(tmp_path):
    docs = source()
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    assert publish_quest_consequence_diff(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    assert stat.S_IMODE((tmp_path / FILENAME).stat().st_mode) == 0o600
    assert restore_quest_consequence_diff(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases(docs)["expected_source_digest"]) == report
    with pytest.raises(FileExistsError):
        publish_quest_consequence_diff(docs, report, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_quest_consequence_diff(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])


def test_duplicate_json_and_world_readable_restore_rejected(tmp_path):
    docs = source()
    (tmp_path / FILENAME).write_text('{"schema":"a","schema":"b"}')
    os.chmod(tmp_path / FILENAME, 0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_consequence_diff(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    (tmp_path / FILENAME).write_text(json.dumps(report))
    os.chmod(tmp_path / FILENAME, 0o644)
    with pytest.raises(StudioQuestError):
        restore_quest_consequence_diff(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases(docs)["expected_source_digest"])


def test_directory_fsync_failure_rolls_back_publication(tmp_path, monkeypatch):
    from skeleton.ai.game_builder import studio_quest_consequence_diff as owner
    docs = source()
    report = compile_quest_consequence_diff(docs, fork(), **leases(docs))
    original = owner.os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(owner.os.fstat(fd).st_mode):
            raise OSError("simulated durability failure")
        return original(fd)
    monkeypatch.setattr(owner.os, "fsync", fail_directory)
    with pytest.raises(OSError, match="durability failure"):
        publish_quest_consequence_diff(docs, report, tmp_path, authorized=True)
    assert not list(tmp_path.iterdir())


def test_jeeves_adapter_exact_fields_and_authority(monkeypatch):
    docs = source()
    from skeleton.ai.agents.jeeves import studio_quest_consequence_tool as tool
    monkeypatch.setattr(tool, "read_blueprint", lambda project: docs)
    request = {
        "schema": REQUEST_SCHEMA, "project_id": "original",
        "authoring": fork(),
        "expected_source_digest": leases(docs)["expected_source_digest"],
        "expected_initial_session_digest":
            leases(docs)["expected_initial_session_digest"],
    }
    assert quest_consequence_tool_schema()["name"] == "studio_original_quest_consequences"
    result = execute_quest_consequence_tool(request, authorized=True)
    assert result["detail"]["ending_delta"]["gained"] == ["war"]
    with pytest.raises(PermissionError):
        execute_quest_consequence_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_quest_consequence_tool(dict(request, unexpected=1), authorized=True)
