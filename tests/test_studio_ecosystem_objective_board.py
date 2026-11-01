"""Canonical objective board, NPC scene joins, offline HTML and typed parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_objective_board import (
    OBJECTIVE_BOARD_SCHEMA, page_objectives, render_objective_board_html,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    OBJECTIVE_BOARD_REQUEST_SCHEMA, execute_objective_board_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    return docs, source, session


def test_objective_board_joins_real_quest_and_npc_scene_cues_without_mutation():
    docs, source, session = fixture()
    before = json.dumps(docs, sort_keys=True)
    board = page_objectives(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest, limit=4)
    assert board["schema"] == OBJECTIVE_BOARD_SCHEMA
    assert board["total_objectives"] >= 4
    assert len(board["objectives"]) == 4
    assert board["available_objective_ids"]
    assert board["objectives"][0]["status"] == "available"
    assert any(card["scene_links"] for card in board["objectives"])
    assert all(not card["npc_dialogue_spoken_verified"]
               for card in board["objectives"])
    assert board["release_certified"] is False
    assert board["file_write_performed"] is False
    assert board == page_objectives(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest, limit=4)
    assert json.dumps(docs, sort_keys=True) == before


def test_html_preview_is_script_free_source_bound_and_deterministic():
    docs, source, _ = fixture()
    board = page_objectives(
        docs, [], authorized=True, expected_source_digest=source,
        include_html=True, limit=4)
    assert "<main>" in board["html_preview"]
    assert "Content-Security-Policy" in board["html_preview"]
    assert "<script" not in board["html_preview"].lower()
    assert board["html_preview"] == render_objective_board_html(board)
    assert board == page_objectives(
        docs, [], authorized=True, expected_source_digest=source,
        include_html=True, limit=4)


def test_html_escapes_untrusted_original_authoring_text():
    board = {
        "schema": OBJECTIVE_BOARD_SCHEMA, "project_id": "<img src=x>",
        "objectives": [{
            "stage_id": "<script>alert(1)</script>", "status": "available",
            "reward": '"><iframe>', "scene_links": [{
                "scene_id": "<b>unsafe</b>", "site": '" onload="alert(1)',
                "npc_id": "<svg>",
            }],
        }],
    }
    html = render_objective_board_html(board)
    assert "<script" not in html.lower()
    assert "<iframe" not in html.lower()
    assert "<svg" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "&quot;" in html


@pytest.mark.parametrize("override", [
    {"expected_source_digest": "0" * 64},
    {"expected_session_digest": "0" * 64},
    {"expected_session_digest": True},
    {"offset": -1}, {"offset": True}, {"offset": 1},
    {"limit": 0}, {"limit": 17}, {"limit": True},
    {"include_html": "yes"}, {"actions": [["forged", "unknown"]]},
])
def test_invalid_options_leases_and_replay_fail_closed(override):
    docs, source, _ = fixture()
    kwargs = dict(authorized=True, expected_source_digest=source)
    actions = override.get("actions", [])
    kwargs.update({key: value for key, value in override.items() if key != "actions"})
    with pytest.raises(StudioQuestError):
        page_objectives(docs, actions, **kwargs)


def test_operator_authority_required():
    docs, source, _ = fixture()
    with pytest.raises(PermissionError):
        page_objectives(
            docs, [], authorized=False, expected_source_digest=source)


def test_typed_jeeves_cli_parity_and_mode_exclusion(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, source, _ = fixture()
    request = {
        "schema": OBJECTIVE_BOARD_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": source,
        "actions": [], "limit": 4, "include_html": True,
    }
    typed = execute_objective_board_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--objective-board",
        "--objective-board-expected-source", source,
        "--objective-board-limit", "4", "--objective-board-html",
        "--quest-actions", "[]",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_objective_board_tool({**request, "forged": 1}, authorized=True)
    with pytest.raises(PermissionError):
        execute_objective_board_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--objective-board"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--objective-board",
              "--objective-board-expected-source", source, "--ending-atlas"])
