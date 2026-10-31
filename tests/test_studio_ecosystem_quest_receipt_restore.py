"""Restore canonical quest receipts to source-verified NPC editor state."""
import io
import json
import sys

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_choice_preview import (
    preview_dialogue_choices,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_quest_receipt_restore import (
    MAX_QUEST_RECEIPT_BYTES, restore_quest_receipt,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_RESTORE_REQUEST_SCHEMA, execute_dialogue_restore_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def _source_and_receipt():
    docs = read_blueprint(PROJECT)
    source_digest = audit_canon_source(docs, authorized=True)["source_digest"]
    choice = preview_dialogue_choices(docs, [], authorized=True)["previews"][0]
    actions = [[choice["quest_stage"], choice["alternative"]]]
    return docs, source_digest, replay_quest(docs, actions, authorized=True).receipt()


def test_restore_replays_and_verifies_every_save_field():
    docs, digest, receipt = _source_and_receipt()
    session = restore_quest_receipt(
        docs, json.dumps(receipt), authorized=True, expected_source_digest=digest)
    assert session.receipt() == receipt
    assert restore_quest_receipt(
        docs, json.dumps(receipt).encode(), authorized=True).receipt() == receipt


def test_forged_replay_and_source_drift_fail_closed():
    docs, digest, receipt = _source_and_receipt()
    with pytest.raises(PermissionError):
        restore_quest_receipt(docs, json.dumps(receipt), authorized=False)
    for mutation in (
        {"session_digest": "0" * 64},
        {"completed": []},
        {"release_certified": True},
        {"external_evidence_verified": True},
        {"source_digest": "0" * 64},
        {"choices": [["nonexistent", "win"]]},
        {"unknown": "field"},
    ):
        with pytest.raises(StudioQuestError):
            restore_quest_receipt(docs, json.dumps({**receipt, **mutation}),
                                  authorized=True)
    with pytest.raises(StudioQuestError):
        restore_quest_receipt(docs, json.dumps(receipt), authorized=True,
                              expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        restore_quest_receipt(docs, b'{"schema":"a","schema":"b"}', authorized=True)
    with pytest.raises(StudioQuestError):
        restore_quest_receipt(docs, b"{" + b"x" * MAX_QUEST_RECEIPT_BYTES + b"}",
                              authorized=True)
    assert digest == audit_canon_source(docs, authorized=True)["source_digest"]


def test_cli_and_typed_jeeves_restore_are_identical(monkeypatch, capsys):
    from scripts.studio_ecosystem_cli import main
    _, digest, receipt = _source_and_receipt()
    request = {
        "schema": DIALOGUE_RESTORE_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "receipt": receipt,
    }
    typed = execute_dialogue_restore_tool(request, authorized=True)
    stream = io.TextIOWrapper(io.BytesIO(json.dumps(receipt).encode("utf-8")))
    monkeypatch.setattr(sys, "stdin", stream)
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-restore-stdin",
                 "--dialogue-expected-digest", digest]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_restore_tool({**request, "unexpected": True},
                                      authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-restore-stdin"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-restore-stdin", "--dialogue-actions", "[]"])
