"""Canonical NPC encounter codex: replayed cues, pagination and typed parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_npc_codex import (
    NPC_CODEX_SCHEMA, page_npc_encounters,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    NPC_CODEX_REQUEST_SCHEMA, execute_npc_codex_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, source


def test_source_bound_codex_pages_and_replays_deterministically():
    docs, source = fixture()
    before = json.dumps(docs, sort_keys=True)
    first = page_npc_encounters(
        docs, [], authorized=True, expected_source_digest=source, limit=2)
    assert first["schema"] == NPC_CODEX_SCHEMA
    assert first["total"] >= 2 and len(first["entries"]) == 2
    assert first["next_offset"] == 2
    assert all(not entry["dialogue_spoken_verified"] for entry in first["entries"])
    second = page_npc_encounters(
        docs, [], authorized=True, expected_source_digest=source,
        offset=first["next_offset"], limit=2,
        expected_session_digest=first["session_digest"])
    assert first["entries"][0]["scene_id"] != second["entries"][0]["scene_id"]
    assert json.dumps(docs, sort_keys=True) == before
    assert first == page_npc_encounters(
        docs, [], authorized=True, expected_source_digest=source, limit=2)


def test_npc_filter_preserves_source_order_and_unknown_fails_closed():
    docs, source = fixture()
    all_cards = page_npc_encounters(
        docs, [], authorized=True, expected_source_digest=source, limit=16)
    npc = all_cards["entries"][0]["npc_id"]
    subset = page_npc_encounters(
        docs, [], authorized=True, expected_source_digest=source, npc_id=npc)
    assert subset["entries"] and all(e["npc_id"] == npc for e in subset["entries"])
    with pytest.raises(StudioQuestError):
        page_npc_encounters(
            docs, [], authorized=True, expected_source_digest=source,
            npc_id="../forged")


@pytest.mark.parametrize("override", [
    {"offset": -1}, {"offset": True}, {"limit": 0}, {"limit": 17},
    {"offset": 1}, {"expected_session_digest": "0" * 64},
    {"expected_source_digest": "0" * 64}, {"npc_id": True},
])
def test_invalid_pagination_and_leases_fail_closed(override):
    docs, source = fixture()
    kwargs = dict(authorized=True, expected_source_digest=source)
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        page_npc_encounters(docs, [], **kwargs)


def test_codex_requires_operator_authority():
    docs, source = fixture()
    with pytest.raises(PermissionError):
        page_npc_encounters(docs, [], authorized=False, expected_source_digest=source)


def test_typed_jeeves_cli_parity_and_exclusive_modes(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, source = fixture()
    request = {"schema": NPC_CODEX_REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source, "actions": [], "limit": 2}
    typed = execute_npc_codex_tool(request, authorized=True)
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-actions", "[]", "--dialogue-expected-digest", source,
                 "--dialogue-npc-codex", "--dialogue-npc-limit", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_npc_codex_tool({**request, "unknown": True}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-npc-codex"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-npc-codex", "--dialogue-preview"])
