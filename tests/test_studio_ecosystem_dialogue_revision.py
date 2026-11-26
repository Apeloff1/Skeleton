"""Persisted canon edits flow into source-bound NPC dialogue and Jeeves."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_STAGING_REQUEST_SCHEMA, execute_dialogue_staging_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
NEW_KNOWLEDGE = "Two conflicting archive witness records require public review."
EDIT = {"section": "cast", "path": ["support", 0, "knows"], "value": NEW_KNOWLEDGE}


def test_persisted_dialogue_revision_compiles_and_roundtrips(capsys, tmp_path):
    from scripts.studio_ecosystem_cli import main
    source = read_blueprint(PROJECT)
    digest = audit_canon_source(source, authorized=True)["source_digest"]
    revised, html, receipt = preview_canon_revision(source, {
        "schema": REVISION_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": digest, "edits": [EDIT],
    }, authorized=True)
    revision_dir = tmp_path / "revision"
    write_revision_bundle(revision_dir, revised, html, receipt)
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-revision-source", str(revision_dir),
                 "--dialogue-scene-id", "origin"]) == 0
    cards = json.loads(capsys.readouterr().out)
    assert cards["cards"][0]["authored_cues"][0]["text"] == NEW_KNOWLEDGE
    assert cards["source_digest"] == receipt["revised_source_digest"]
    output = tmp_path / "handoff"
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-revision-source", str(revision_dir),
                 "--dialogue-export", "--output", str(output)]) == 0
    capsys.readouterr()
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-revision-source", str(revision_dir),
                 "--dialogue-import", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["source_digest"] == receipt["revised_source_digest"]
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-import", str(output)])


def test_typed_jeeves_dialogue_edits_are_source_leased_and_read_only():
    source = read_blueprint(PROJECT)
    digest = audit_canon_source(source, authorized=True)["source_digest"]
    request = {
        "schema": DIALOGUE_STAGING_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": digest,
        "actions": [], "scene_id": "origin", "edits": [EDIT],
    }
    result = execute_dialogue_staging_tool(request, authorized=True)
    assert result["detail"]["cards"][0]["authored_cues"][0]["text"] == NEW_KNOWLEDGE
    assert result["author_receipt"]["revised_source_digest"] == result["detail"]["source_digest"]
    assert result["file_write_performed"] is False
    assert result == execute_dialogue_staging_tool(request, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_dialogue_staging_tool({**request, "expected_source_digest": "0" * 64},
                                      authorized=True)
    with pytest.raises(StudioQuestError):
        execute_dialogue_staging_tool({**request, "edits": [
            {"section": "cast", "path": ["support", 0, "id"], "value": "forged"}]},
            authorized=True)
