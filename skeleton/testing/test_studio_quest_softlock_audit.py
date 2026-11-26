"""Deterministic, adversarial regression tests for quest softlock auditing."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_quest_softlock_audit import (
    PROMPT, compile_quest_softlock_audit, propose_quest_softlock_audit,
    replay_quest_softlock_audit, compile_quest_softlock_handoff,
    publish_quest_softlock_audit, restore_quest_softlock_audit,
    render_quest_softlock_html,
)


def docs():
    return {
        "quest": {"project_id": "demo", "release_certified": False,
                  "stage_graph": [{
                      "id": "opening", "prerequisites": [],
                      "alternatives": ["rescue", "abandon"],
                      "reward": "opening_complete",
                      "choice_effects": {"rescue": ["choice:opening:rescue"],
                                         "abandon": ["choice:opening:abandon"]},
                  }]},
        "narrative": {"project_id": "demo", "release_certified": False,
                      "endings": [{"id": "saved", "requires": ["choice:opening:rescue"]}]},
    }


def kwargs(source=None, actions=None):
    d = docs() if source is None else source
    a = [] if actions is None else actions
    return {"authorized": True,
            "expected_source_digest": compile_quest_program(d).source_digest,
            "expected_initial_session_digest":
                replay_quest(d, a, authorized=True).digest}


def plan(actions=None, states=64, depth=4):
    return {"initial_actions": [] if actions is None else actions,
            "target_endings": ["saved"], "max_states": states, "max_depth": depth}


def test_proven_softlock_has_replayable_terminal_witness():
    d = docs()
    result = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    assert result["status"] == "softlock_proven"
    assert result["terminal_softlock_witness"]["actions"] == [["opening", "abandon"]]
    assert result["safe_ending_witness"]["actions"] == [["opening", "rescue"]]
    assert result["playable_handoff_allowed"] is False
    assert replay_quest_softlock_audit(d, result, authorized=True) == result
    assert b"softlock_proven" in render_quest_softlock_html(d, result, authorized=True)
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_handoff(d, result, authorized=True)


def test_safe_prefix_is_exhaustive_and_handoff_is_source_bound():
    d = docs()
    actions = [["opening", "rescue"]]
    result = compile_quest_softlock_audit(d, plan(actions), **kwargs(d, actions))
    assert result["status"] == "no_softlock_in_exhaustive_search"
    assert result["search_exhaustive"] is True
    assert result["playable_handoff_allowed"] is True
    handoff = compile_quest_softlock_handoff(d, result, authorized=True)
    assert handoff["canonical_quest_replay_verified"] is True
    assert handoff["native_gameplay_verified"] is False


def test_budget_exhaustion_is_not_a_safety_proof():
    d = docs()
    result = compile_quest_softlock_audit(d, plan(states=1), **kwargs(d))
    assert result["status"] == "inconclusive"
    assert result["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_handoff(d, result, authorized=True)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"audit_digest": "0" * 64}),
    lambda x: x.update({"status": "no_softlock_in_exhaustive_search"}),
    lambda x: x.update({"playable_handoff_allowed": True}),
    lambda x: x["terminal_softlock_witness"]["actions"].append(["opening", "rescue"]),
])
def test_forged_receipt_rejected(mutate):
    d = docs()
    result = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    forged = copy.deepcopy(result)
    mutate(forged)
    with pytest.raises(StudioQuestError):
        replay_quest_softlock_audit(d, forged, authorized=True)


@pytest.mark.parametrize("invalid", [
    {"initial_actions": [], "target_endings": ["saved"], "max_states": True, "max_depth": 4},
    {"initial_actions": [], "target_endings": ["saved", "saved"], "max_states": 8, "max_depth": 4},
    {"initial_actions": [], "target_endings": ["unknown"], "max_states": 8, "max_depth": 4},
    {"initial_actions": [], "target_endings": ["saved"], "max_states": 8, "max_depth": False},
    {"initial_actions": [["opening", "rescue"]], "target_endings": ["saved"], "max_states": 8, "max_depth": 0},
])
def test_malformed_authoring_rejected(invalid):
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_audit(docs(), invalid, **kwargs())


def test_prompt_and_stale_source_session_rejected():
    d = docs()
    result = propose_quest_softlock_audit(d, PROMPT, **kwargs(d))
    assert result["status"] == "softlock_proven"
    with pytest.raises(StudioQuestError):
        propose_quest_softlock_audit(d, "make up an ending", **kwargs(d))
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_audit(
            d, plan(), authorized=True,
            expected_source_digest="0" * 64,
            expected_initial_session_digest=kwargs(d)["expected_initial_session_digest"])
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_audit(
            d, plan(), authorized=True,
            expected_source_digest=kwargs(d)["expected_source_digest"],
            expected_initial_session_digest="0" * 64)
    with pytest.raises(PermissionError):
        compile_quest_softlock_audit(
            d, plan(), authorized=False,
            expected_source_digest=kwargs(d)["expected_source_digest"],
            expected_initial_session_digest=kwargs(d)["expected_initial_session_digest"])


def test_private_publication_and_restore(tmp_path: Path):
    d = docs()
    result = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    publication = publish_quest_softlock_audit(d, result, tmp_path, authorized=True)
    assert publication["file_write_performed"] is True
    assert restore_quest_softlock_audit(
        d, tmp_path, authorized=True,
        expected_source_digest=kwargs(d)["expected_source_digest"]) == result
    with pytest.raises((FileExistsError, StudioQuestError)):
        publish_quest_softlock_audit(d, result, tmp_path, authorized=True)
    file = tmp_path / "studio_quest_softlock_audit.json"
    file.unlink()
    file.write_text(json.dumps({**result, "status": "forged"}))
    file.chmod(0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_softlock_audit(
            d, tmp_path, authorized=True,
            expected_source_digest=kwargs(d)["expected_source_digest"])


def test_editor_roundtrip_and_tamper_rejection(tmp_path: Path):
    from skeleton.ai.game_builder.studio_quest_softlock_editor import (
        EXPORT_SCHEMA, render_quest_softlock_editor,
        publish_quest_softlock_editor, load_quest_softlock_editor_export,
    )
    d = docs()
    baseline = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    html = render_quest_softlock_editor(d, baseline, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"sha256-" in html
    assert b"unsafe-inline" not in html
    assert b"Export typed plan" in html
    publication = publish_quest_softlock_editor(
        d, baseline, tmp_path, authorized=True)
    assert publication["file_write_performed"] is True
    export = tmp_path / "export.json"
    envelope = {
        "schema": EXPORT_SCHEMA, "baseline_digest": baseline["audit_digest"],
        "source_digest": baseline["source_digest"],
        "initial_session_digest": baseline["initial_session_digest"],
        "authoring": plan([["opening", "rescue"]]),
    }
    export.write_text(json.dumps(envelope))
    export.chmod(0o600)
    edited = load_quest_softlock_editor_export(
        d, baseline, export, **kwargs(d))
    result = compile_quest_softlock_audit(
        d, edited, **kwargs(d, [["opening", "rescue"]]))
    assert result["status"] == "no_softlock_in_exhaustive_search"
    envelope["baseline_digest"] = "0" * 64
    export.write_text(json.dumps(envelope))
    with pytest.raises(StudioQuestError):
        load_quest_softlock_editor_export(d, baseline, export, **kwargs(d))
    envelope["baseline_digest"] = baseline["audit_digest"]
    export.write_text('{"schema":"x","schema":"y"}')
    with pytest.raises(StudioQuestError):
        load_quest_softlock_editor_export(d, baseline, export, **kwargs(d))


def test_editor_symlink_export_rejected(tmp_path: Path):
    from skeleton.ai.game_builder.studio_quest_softlock_editor import (
        load_quest_softlock_editor_export,
    )
    d = docs()
    baseline = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    target = tmp_path / "real.json"
    target.write_text("{}")
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises((OSError, StudioQuestError)):
        load_quest_softlock_editor_export(
            d, baseline, link, **kwargs(d))


def test_exhaustive_safety_when_every_authored_choice_awards_same_stage_reward():
    d = docs()
    d["narrative"]["endings"][0]["requires"] = ["opening_complete"]
    result = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    assert result["status"] == "no_softlock_in_exhaustive_search"
    assert result["expanded_states"] == 3
    assert result["search_exhaustive"] is True
    assert result["terminal_softlock_witness"] is None
    assert compile_quest_softlock_handoff(
        d, result, authorized=True)["canonical_quest_replay_verified"] is True


def test_depth_truncation_cannot_be_reported_safe():
    d = docs()
    result = compile_quest_softlock_audit(
        d, plan(depth=1), **kwargs(d))
    assert result["status"] == "softlock_proven"
    d["quest"]["stage_graph"].append({
        "id": "second", "prerequisites": ["opening"],
        "alternatives": ["wait"], "reward": "second_complete",
    })
    result = compile_quest_softlock_audit(
        d, plan(depth=1), **kwargs(d))
    # The good choice is a verified eligible ending; the bad choice has
    # unresolved authored successors at the depth fence, not a proved lock.
    assert result["status"] == "inconclusive"
    assert result["playable_handoff_allowed"] is False


def test_edited_prefix_rejected_if_quest_action_is_illegal():
    d = docs()
    bad = plan([["missing_stage", "rescue"]])
    with pytest.raises(StudioQuestError):
        compile_quest_softlock_audit(d, bad, **kwargs(d))


def test_private_restore_rejects_symlink_and_world_writable_file(tmp_path: Path):
    d = docs()
    result = compile_quest_softlock_audit(d, plan(), **kwargs(d))
    other = tmp_path / "other"
    other.mkdir()
    publish_quest_softlock_audit(d, result, other, authorized=True)
    link = tmp_path / "studio_quest_softlock_audit.json"
    link.symlink_to(other / "studio_quest_softlock_audit.json")
    with pytest.raises((OSError, StudioQuestError)):
        restore_quest_softlock_audit(
            d, tmp_path, authorized=True,
            expected_source_digest=kwargs(d)["expected_source_digest"])
    link.unlink()
    published = other / "studio_quest_softlock_audit.json"
    published.chmod(0o666)
    with pytest.raises(StudioQuestError):
        restore_quest_softlock_audit(
            d, other, authorized=True,
            expected_source_digest=kwargs(d)["expected_source_digest"])


def test_jeeves_tool_descriptor_and_authorization_contract(monkeypatch):
    from skeleton.ai.agents.jeeves import studio_quest_softlock_audit_tool as adapter
    d = docs()
    monkeypatch.setattr(adapter, "read_blueprint", lambda project_id: d)
    descriptor = adapter.quest_softlock_audit_tool_schema()
    assert descriptor["name"] == "studio_original_quest_softlock_audit"
    request = {
        "schema": adapter.REQUEST_SCHEMA,
        "project_id": "demo",
        "authoring": plan(),
        "expected_source_digest": kwargs(d)["expected_source_digest"],
        "expected_initial_session_digest": kwargs(d)["expected_initial_session_digest"],
    }
    with pytest.raises(PermissionError):
        adapter.execute_quest_softlock_audit_tool(request, authorized=False)
    result = adapter.execute_quest_softlock_audit_tool(request, authorized=True)
    assert result["detail"]["status"] == "softlock_proven"
    assert result["file_write_performed"] is False
    with pytest.raises(StudioQuestError):
        adapter.execute_quest_softlock_audit_tool(
            {**request, "authorized": True}, authorized=True)
