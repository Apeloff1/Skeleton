"""Deterministic causal witness proof, custody, and adversarial fixtures."""
from __future__ import annotations
import copy
import json
import os
import stat

import pytest

from tests.test_studio_quest_consequence_diff import source, leases, fork
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_consequence_diff import (
    compile_quest_consequence_diff,
)
from skeleton.ai.game_builder.studio_quest_causal_trace import (
    FILENAME, SCHEMA, compile_quest_causal_trace,
    replay_quest_causal_trace, compile_quest_causal_handoff,
    render_quest_causal_html, publish_quest_causal_trace,
    restore_quest_causal_trace,
)


def receipts(documents, authoring=None):
    diff = compile_quest_consequence_diff(
        documents, authoring or fork(), **leases(documents))
    return diff, compile_quest_causal_trace(documents, diff, authorized=True)


def test_witnesses_explain_real_authored_endings_and_divergence():
    docs = source()
    diff, trace = receipts(docs)
    assert trace["schema"] == SCHEMA
    assert trace["first_divergence_index"] == 0
    assert trace["baseline"]["steps"][0]["facts_added"] == [
        "choice:gate:mercy", "gate", "gate_open"]
    assert trace["candidate"]["steps"][0]["endings_unlocked"] == ["war"]
    rows = {row["ending_id"]: row for row in trace["ending_predicate_proofs"]}
    assert rows["peace"]["baseline_eligible"] is True
    assert rows["peace"]["candidate_missing"] == ["choice:gate:mercy"]
    assert rows["war"]["candidate_witnesses"]["choice:gate:force"] == [{
        "action_index": 0, "stage_id": "gate",
        "alternative": "force", "origin": "authored_choice_effect",
    }]
    assert replay_quest_causal_trace(docs, diff, trace, authorized=True) == trace
    assert receipts(docs)[1] == trace
    handoff = compile_quest_causal_handoff(
        docs, diff, trace, authorized=True)
    assert handoff["causal_trace_digest"] == trace["receipt_digest"]
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_shared_prefix_digest_and_append_only_history():
    docs = source()
    docs["quest"]["stage_graph"].append({
        "id": "bridge", "prerequisites": ["gate"],
        "alternatives": ["help"], "reward": "bridge_open",
    })
    plan = {
        "baseline_actions": [["gate", "mercy"], ["bridge", "help"]],
        "candidate_actions": [["gate", "mercy"]],
    }
    diff, trace = receipts(docs, plan)
    assert trace["first_divergence_index"] == 1
    assert (trace["shared_prefix_session_digest"]
            == trace["candidate"]["session_digest"])
    assert trace["baseline"]["steps"][1]["facts_added"] == [
        "bridge", "bridge_open"]
    assert replay_quest_causal_trace(docs, diff, trace, authorized=True) == trace


@pytest.mark.parametrize("key,value", [
    ("canonical_quest_replay_verified", 1),
    ("native_gameplay_verified", True),
    ("release_certified", True),
    ("first_divergence_index", False),
    ("receipt_digest", "0" * 64),
    ("shared_prefix_session_digest", "0" * 64),
])
def test_forged_receipt_fields_fail_closed(key, value):
    docs = source()
    diff, trace = receipts(docs)
    altered = copy.deepcopy(trace)
    altered[key] = value
    with pytest.raises(StudioQuestError):
        replay_quest_causal_trace(docs, diff, altered, authorized=True)


def test_forged_witness_and_source_drift_fail_closed():
    docs = source()
    diff, trace = receipts(docs)
    altered = copy.deepcopy(trace)
    altered["candidate"]["witnesses"]["choice:gate:force"][0]["origin"] = "external"
    with pytest.raises(StudioQuestError):
        replay_quest_causal_trace(docs, diff, altered, authorized=True)
    docs["quest"]["stage_graph"][0]["reward"] = "revised"
    with pytest.raises(StudioQuestError):
        replay_quest_causal_trace(docs, diff, trace, authorized=True)


def test_unfinished_branch_blocks_handoff():
    docs = source()
    diff, trace = receipts(docs, {
        "baseline_actions": [], "candidate_actions": [["gate", "force"]],
    })
    assert trace["baseline"]["endings"] == []
    with pytest.raises(StudioQuestError):
        compile_quest_causal_handoff(docs, diff, trace, authorized=True)


def test_authority_and_wrong_receipt_type_rejected():
    docs = source()
    diff, trace = receipts(docs)
    with pytest.raises(PermissionError):
        compile_quest_causal_trace(docs, diff, authorized=False)
    with pytest.raises(PermissionError):
        replay_quest_causal_trace(docs, diff, trace, authorized=False)
    with pytest.raises(StudioQuestError):
        replay_quest_causal_trace(docs, diff, [], authorized=True)


def test_html_escapes_authored_ending_and_blocks_scripts():
    docs = source()
    docs["narrative"]["endings"][0]["id"] = "<script>alert(1)</script>"
    diff, trace = receipts(docs)
    html = render_quest_causal_html(docs, diff, trace, authorized=True)
    assert b"script-src 'none'" in html
    assert b"&lt;script&gt;" in html
    assert b"<script>alert(1)</script>" not in html


def test_private_publication_restore_and_no_clobber(tmp_path):
    docs = source()
    diff, trace = receipts(docs)
    published = publish_quest_causal_trace(
        docs, diff, trace, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert stat.S_IMODE((tmp_path / FILENAME).stat().st_mode) == 0o600
    assert restore_quest_causal_trace(
        docs, diff, tmp_path, authorized=True) == trace
    with pytest.raises(FileExistsError):
        publish_quest_causal_trace(docs, diff, trace, tmp_path, authorized=True)


def test_symlink_public_permissions_and_duplicate_keys_rejected(tmp_path):
    docs = source()
    diff, trace = receipts(docs)
    path = tmp_path / FILENAME
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(OSError):
        restore_quest_causal_trace(docs, diff, tmp_path, authorized=True)
    path.unlink()
    path.write_text(json.dumps(trace))
    os.chmod(path, 0o644)
    with pytest.raises(StudioQuestError):
        restore_quest_causal_trace(docs, diff, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_causal_trace(docs, diff, tmp_path, authorized=True)


def test_directory_fsync_failure_rolls_back(tmp_path, monkeypatch):
    from skeleton.ai.game_builder import studio_quest_causal_trace as owner
    docs = source()
    diff, trace = receipts(docs)
    original = owner.os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(owner.os.fstat(fd).st_mode):
            raise OSError("simulated durability failure")
        return original(fd)
    monkeypatch.setattr(owner.os, "fsync", fail_directory)
    with pytest.raises(OSError, match="durability failure"):
        publish_quest_causal_trace(
            docs, diff, trace, tmp_path, authorized=True)
    assert not list(tmp_path.iterdir())


def test_jeeves_adapter_and_router_registration(monkeypatch):
    docs = source()
    from skeleton.ai.agents.jeeves import studio_quest_causal_trace_tool as tool
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    monkeypatch.setattr(tool, "read_blueprint", lambda project: docs)
    request = {
        "schema": tool.REQUEST_SCHEMA, "project_id": "original",
        "authoring": fork(),
        "expected_source_digest": leases(docs)["expected_source_digest"],
        "expected_initial_session_digest":
            leases(docs)["expected_initial_session_digest"],
    }
    name = tool.quest_causal_trace_tool_schema()["name"]
    assert name in {x["name"] for x in world_tool_catalog()["tools"]}
    routed = route_world_tool(
        {"tool": name, "arguments": request}, authorized=True)
    assert routed["result"]["detail"]["ending_delta"]["gained"] == ["war"]
    with pytest.raises(PermissionError):
        tool.execute_quest_causal_trace_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        tool.execute_quest_causal_trace_tool(
            dict(request, unexpected=True), authorized=True)
