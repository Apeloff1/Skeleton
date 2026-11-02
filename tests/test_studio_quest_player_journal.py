"""Quest player journal: canonical source, edited notes, private custody, UI and CLI."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest, step_quest,
)
from skeleton.ai.game_builder.studio_quest_player_journal import (
    SCHEMA, PLAN_SCHEMA, PROMPT, compile_quest_journal, suggest_quest_journal,
    replay_quest_journal, compile_journal_handoff, publish_quest_journal,
    restore_quest_journal, render_quest_journal_editor_html, FILENAME,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_player_journal_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    first = program.stages[0]
    advanced = step_quest(initial, docs, stage=first.key,
                          alternative=first.alternatives[0], authorized=True)
    plan = {"schema": PLAN_SCHEMA,
            "actions": [[first.key, first.alternatives[0]]],
            "entries": [{"stage_id": first.key, "note": "I remember this choice."}],
            "target_ending": program.endings[0][0]}
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    return docs, plan, leases, advanced


def test_source_replay_and_suggested_notes_are_not_external_evidence():
    docs, plan, leases, session = fixture()
    receipt = compile_quest_journal(docs, plan, **leases)
    assert receipt["schema"] == SCHEMA
    assert receipt["session_digest"] == session.digest
    assert receipt["entry_count"] == 1
    assert receipt["file_write_performed"] is False
    assert receipt["external_evidence_verified"] is False
    assert receipt["native_gameplay_verified"] is False
    assert receipt["release_certified"] is False
    assert replay_quest_journal(docs, receipt, authorized=True) == receipt
    suggested = suggest_quest_journal(
        docs, PROMPT, plan["actions"], target_ending=plan["target_ending"], **leases)
    assert suggested["authoring"]["entries"][0]["note"].startswith("Completed ")
    assert suggested["session_digest"] == receipt["session_digest"]
    if receipt["playable_handoff_allowed"]:
        handoff = compile_journal_handoff(docs, receipt, authorized=True)
        assert handoff["entries"] == plan["entries"]
        assert handoff["release_certified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_journal_handoff(docs, receipt, authorized=True)


@pytest.mark.parametrize("mutate", [
    lambda x: x["entries"].append({"stage_id": "never-earned", "note": "Forged"}),
    lambda x: x["entries"].append(copy.deepcopy(x["entries"][0])),
    lambda x: x["entries"][0].update({"note": "<script>\n<script>"}),
    lambda x: x["entries"][0].update({"note": "x" * 1025}),
    lambda x: x.update({"authorized": True}),
    lambda x: x.update({"schema": "forged"}),
])
def test_malformed_and_unearned_entries_fail_closed(mutate):
    docs, plan, leases, _ = fixture()
    bad = copy.deepcopy(plan)
    mutate(bad)
    if bad["entries"][0]["note"] == "<script>\n<script>":
        # HTML-shaped user prose is legal text; it is escaped in the editor.
        result = compile_quest_journal(docs, bad, **leases)
        html = render_quest_journal_editor_html(docs, result, authorized=True)
        assert b"&lt;script&gt;" in html
        assert b"<script>\n<script>" not in html
    else:
        with pytest.raises(StudioQuestError):
            compile_quest_journal(docs, bad, **leases)


def test_stale_source_forged_receipt_and_prompt_fail_closed():
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_journal(docs, plan, **leases)
    forged = copy.deepcopy(receipt)
    forged["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_journal(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_journal(docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        suggest_quest_journal(
            docs, "invent a fake victory", plan["actions"],
            target_ending=plan["target_ending"], **leases)
    changed = copy.deepcopy(docs)
    key = "stage_graph" if changed["quest"].get("stage_graph") else "stages"
    changed["quest"][key][0]["reward"] = "different"
    with pytest.raises(StudioQuestError):
        replay_quest_journal(changed, receipt, authorized=True)


def test_offline_editor_escapes_untrusted_prose_and_disables_network():
    docs, plan, leases, _ = fixture()
    plan["entries"][0]["note"] = "</textarea><img src=x onerror=alert(1)>"
    receipt = compile_quest_journal(docs, plan, **leases)
    html = render_quest_journal_editor_html(docs, receipt, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"&lt;/textarea&gt;" in html
    assert b"</textarea><img" not in html
    assert b"\\u003c" in html


def test_private_publication_restore_and_exclusive_link(tmp_path):
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_journal(docs, plan, **leases)
    published = publish_quest_journal(docs, receipt, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert restore_quest_journal(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_journal(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_journal(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_typed_jeeves_route_requires_authoring_opt_in(monkeypatch):
    docs, plan, leases, _ = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_player_journal_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_player_journal"
    entry = next(x for x in world_tool_catalog()["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "actions": plan["actions"], "target_ending": plan["target_ending"],
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"]}}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["detail"]["entry_count"] == 1
    assert routed["file_write_performed"] is False


def test_cli_edit_save_restore_and_handoff_hold(tmp_path, capsys):
    from scripts.studio_quest_player_journal_cli import main
    docs, plan, leases, _ = fixture()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["journal"]["entry_count"] == 1
    assert main(args + ["--editor-html"]) == 0
    assert "Quest player journal" in capsys.readouterr().out
    assert main(args + ["--publish", str(tmp_path)]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["journal"] == saved["journal"]
