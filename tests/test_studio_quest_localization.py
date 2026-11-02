"""Source-grounded quest localization, reviewed handoff, CLI and adversarial input."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest, step_quest,
)
from skeleton.ai.game_builder.studio_quest_localization import (
    PLAN_SCHEMA, PROMPT, FILENAME, propose_quest_localization,
    compile_quest_localization, replay_quest_localization,
    compile_localized_handoff, publish_quest_localization,
    restore_quest_localization, render_localization_editor_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_localization_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    stage = program.stages[0]
    advanced = step_quest(initial, docs, stage=stage.key,
                          alternative=stage.alternatives[0], authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_quest_localization(
        docs, PROMPT, "nb-NO", [[stage.key, stage.alternatives[0]]],
        program.endings[0][0], **leases)
    return docs, plan, leases, advanced


def test_proposal_is_source_only_and_requires_explicit_review():
    docs, plan, leases, advanced = fixture()
    assert plan["schema"] == PLAN_SCHEMA
    assert plan["rows"] and all(not x["reviewed"] for x in plan["rows"])
    assert all(x["translation"] == x["source"] for x in plan["rows"])
    receipt = compile_quest_localization(docs, plan, **leases)
    assert receipt["session_digest"] == advanced.digest
    assert receipt["reviewed_count"] == 0
    assert receipt["playable_handoff_allowed"] is False
    assert receipt["translation_provenance_verified"] is False
    assert receipt["native_gameplay_verified"] is False
    assert replay_quest_localization(docs, receipt, authorized=True) == receipt
    with pytest.raises(StudioQuestError):
        compile_localized_handoff(docs, receipt, authorized=True)


def test_reviewed_translation_preserves_canonical_choice_and_ending():
    docs, plan, leases, advanced = fixture()
    for row in plan["rows"]:
        row["reviewed"] = True
    receipt = compile_quest_localization(docs, plan, **leases)
    assert receipt["reviewed_count"] == receipt["row_count"]
    assert receipt["session_digest"] == advanced.digest
    if receipt["target_ending_eligible"]:
        handoff = compile_localized_handoff(docs, receipt, authorized=True)
        assert handoff["canonical_choices"] == plan["actions"]
        assert handoff["source_digest"] == leases["expected_source_digest"]
        assert handoff["native_gameplay_verified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_localized_handoff(docs, receipt, authorized=True)


@pytest.mark.parametrize("mutation", [
    lambda p: p["rows"].pop(),
    lambda p: p["rows"].reverse(),
    lambda p: p["rows"][0].update({"source": "forged"}),
    lambda p: p["rows"][0].update({"stage_id": "forged"}),
    lambda p: p["rows"][0].update({"reviewed": 1}),
    lambda p: p["rows"][0].update({"translation": "\u202eunsafe"}),
    lambda p: p["rows"][0].update({"translation": "x" * 513}),
    lambda p: p.update({"authorized": True}),
    lambda p: p.update({"locale": "xx/../../"}),
])
def test_malformed_or_forged_translation_fails_closed(mutation):
    docs, plan, leases, _ = fixture()
    bad = copy.deepcopy(plan)
    mutation(bad)
    with pytest.raises(StudioQuestError):
        compile_quest_localization(docs, bad, **leases)


def test_stale_source_and_receipt_tamper_fail_closed():
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_localization(docs, plan, **leases)
    forged = copy.deepcopy(receipt)
    forged["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_localization(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_localization(docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        propose_quest_localization(
            docs, "translate by guessing", "nb-NO", plan["actions"],
            plan["target_ending"], **leases)
    with pytest.raises(StudioQuestError):
        compile_quest_localization(
            docs, plan, **{**leases, "expected_source_digest": "0" * 64})


def test_html_escapes_translation_and_disables_network():
    docs, plan, leases, _ = fixture()
    plan["rows"][0]["translation"] = '</script><img src=x onerror=alert(1)>'
    receipt = compile_quest_localization(docs, plan, **leases)
    html = render_localization_editor_html(docs, receipt, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"&lt;/script&gt;" in html
    assert b"\\u003c" in html
    assert b"</script><img" not in html


def test_private_publication_restore_and_exclusive_link(tmp_path):
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_localization(docs, plan, **leases)
    result = publish_quest_localization(docs, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_localization(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_localization(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_localization(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_jeeves_router_requires_out_of_band_authoring(monkeypatch):
    docs, plan, leases, _ = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_localization_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_localization"
    entry = next(row for row in world_tool_catalog()["tools"] if row["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "locale": "nb-NO", "actions": plan["actions"],
        "target_ending": plan["target_ending"],
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"]}}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["detail"] == plan
    assert routed["file_write_performed"] is False


def test_cli_plan_preview_publish_restore(tmp_path, capsys):
    from scripts.studio_quest_localization_cli import main
    docs, plan, leases, _ = fixture()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["localization"]["row_count"] > 0
    assert main(args + ["--editor-html"]) == 0
    assert "Original quest localization editor" in capsys.readouterr().out
    assert main(args + ["--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["localization"]["row_count"] > 0
