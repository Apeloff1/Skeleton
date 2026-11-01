"""Quest alternative authoring: source lease, playable compile and replay parity."""
from hashlib import sha256
import json

import pytest

from skeleton.ai.agents.jeeves.studio_walk_tool import (
    CHOICE_AUTHOR_REQUEST_SCHEMA, execute_choice_author_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    load_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_quest_choice_author import (
    CHOICE_AUTHOR_SCHEMA, preview_quest_choice_revision,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
NEW_CHOICE = "Survey the glacial shore with an original tide ledger."


def fixture():
    docs = read_blueprint(PROJECT)
    stage = compile_quest_program(docs).stages[0]
    old = stage.alternatives[0]
    old_digest = sha256(json.dumps(
        old, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "ascii")).hexdigest()
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, stage.key, old_digest, source


def test_quest_choice_revision_compiles_and_replays_new_authored_branch():
    docs, stage, old_digest, source = fixture()
    before = json.dumps(docs, sort_keys=True)
    revised, html, receipt, detail = preview_quest_choice_revision(
        docs, stage_id=stage, alternative_index=0,
        replacement=NEW_CHOICE, expected_source_digest=source,
        expected_alternative_digest=old_digest, authorized=True)
    assert detail["schema"] == CHOICE_AUTHOR_SCHEMA
    assert detail["original_sample"]["actions"][-1][0] == stage
    assert detail["revised_sample"]["actions"][-1] == [stage, NEW_CHOICE]
    assert detail["revised_sample"]["session_digest"] == replay_quest(
        revised, detail["revised_sample"]["actions"], authorized=True).digest
    assert detail["original_sample"]["session_digest"] != detail[
        "revised_sample"]["session_digest"]
    assert receipt["revised_source_digest"] != source
    assert b"<html" in html.lower()
    assert json.dumps(docs, sort_keys=True) == before
    assert (revised, html, receipt, detail) == preview_quest_choice_revision(
        docs, stage_id=stage, alternative_index=0,
        replacement=NEW_CHOICE, expected_source_digest=source,
        expected_alternative_digest=old_digest, authorized=True)


@pytest.mark.parametrize("override", [
    {"stage_id": "missing"}, {"stage_id": "../escape"},
    {"stage_id": True}, {"alternative_index": True},
    {"alternative_index": -1}, {"alternative_index": 8},
    {"replacement": ""}, {"replacement": "x" * 513},
    {"expected_source_digest": "0" * 64},
    {"expected_alternative_digest": "0" * 64},
])
def test_invalid_choice_authoring_fails_closed(override):
    docs, stage, old_digest, source = fixture()
    kwargs = dict(stage_id=stage, alternative_index=0, replacement=NEW_CHOICE,
                  expected_source_digest=source,
                  expected_alternative_digest=old_digest, authorized=True)
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        preview_quest_choice_revision(docs, **kwargs)


def test_operator_authority_required():
    docs, stage, old_digest, source = fixture()
    with pytest.raises(PermissionError):
        preview_quest_choice_revision(
            docs, stage_id=stage, alternative_index=0,
            replacement=NEW_CHOICE, expected_source_digest=source,
            expected_alternative_digest=old_digest, authorized=False)


def test_typed_jeeves_cli_private_bundle_and_exclusivity(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    docs, stage, old_digest, source = fixture()
    req = {"schema": CHOICE_AUTHOR_REQUEST_SCHEMA, "project_id": PROJECT,
           "stage_id": stage, "alternative_index": 0,
           "replacement": NEW_CHOICE, "expected_source_digest": source,
           "expected_alternative_digest": old_digest}
    typed = execute_choice_author_tool(req, authorized=True)
    output = tmp_path / "authored-quest-choice"
    args = ["--project", PROJECT, "--author-choice",
            "--choice-author-stage", stage, "--choice-author-index", "0",
            "--choice-author-replacement", NEW_CHOICE,
            "--choice-author-expected-source", source,
            "--choice-author-expected-alternative", old_digest,
            "--output", str(output)]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["author"] == typed["detail"]
    restored, receipt = load_revision_bundle(
        output, authorized=True, project_id=PROJECT)
    assert receipt == result["receipt"]
    assert replay_quest(
        restored, typed["detail"]["revised_sample"]["actions"],
        authorized=True).digest == typed["detail"]["revised_sample"]["session_digest"]
    with pytest.raises(SystemExit):
        main(args)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--author-choice"])
    with pytest.raises(StudioQuestError):
        execute_choice_author_tool({**req, "forged": True}, authorized=True)
    with pytest.raises(PermissionError):
        execute_choice_author_tool(req, authorized=False)
