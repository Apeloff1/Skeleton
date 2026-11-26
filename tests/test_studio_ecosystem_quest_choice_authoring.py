"""Canonical original quest-choice prose editing, persistence and replay."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, load_revision_bundle, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_author_merge import merge_canon_revisions
from skeleton.ai.game_builder.studio_ecosystem_author_cherry_pick import (
    cherry_pick_canon_revision,
)
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    AUTHOR_REVISION_REQUEST_SCHEMA, execute_author_revision_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
NEW_CHOICE = "Record the glacial fractures in a publicly auditable survey"


def revise(source, stage, choice, value):
    return preview_canon_revision(source, {
        "schema": REVISION_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(
            source, authorized=True)["source_digest"],
        "edits": [{"section": "quest",
                   "path": ["stage_graph", stage, "alternatives", choice],
                   "value": value}],
    }, authorized=True)


def test_quest_alternative_authoring_compiles_replayable_source_and_bundle(tmp_path):
    base = read_blueprint(PROJECT)
    original = deepcopy(base)
    program = compile_quest_program(base)
    first = program.stages[0]
    revised, html, receipt = revise(base, 0, 0, NEW_CHOICE)
    assert base == original
    assert revised["quest"]["stage_graph"][0]["alternatives"][0] == NEW_CHOICE
    assert receipt["canon_consistent"] is True
    assert receipt["release_certified"] is False
    assert receipt["base_source_digest"] != receipt["revised_source_digest"]
    assert b"Original interactive quest" in html
    assert replay_quest(revised, [[first.key, NEW_CHOICE]],
                        authorized=True).completed == (first.key,)
    with pytest.raises(StudioQuestError, match="not an authored alternative"):
        replay_quest(base, [[first.key, NEW_CHOICE]], authorized=True)
    output = tmp_path / "authored"
    write_revision_bundle(output, revised, html, receipt)
    loaded, loaded_receipt = load_revision_bundle(
        output, authorized=True, project_id=PROJECT)
    assert loaded == revised
    assert loaded_receipt == receipt


def test_quest_alternative_rejects_structural_edits_and_duplicate_choices():
    base = read_blueprint(PROJECT)
    original = base["quest"]["stage_graph"][0]["alternatives"]
    with pytest.raises(StudioQuestError):
        revise(base, 0, 0, original[1])
    with pytest.raises(StudioQuestError):
        revise(base, 0, 0, "x" * 513)
    for path in (["stage_graph", 0, "reward"],
                 ["stage_graph", 0, "prerequisites"],
                 ["stage_graph", 0, "id"],
                 ["stage_graph", 0, "alternatives", True],
                 ["stage_graph", 64, "alternatives", 0]):
        request = {
            "schema": REVISION_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": audit_canon_source(
                base, authorized=True)["source_digest"],
            "edits": [{"section": "quest", "path": path, "value": NEW_CHOICE}],
        }
        with pytest.raises(StudioQuestError):
            preview_canon_revision(base, request, authorized=True)
    with pytest.raises(PermissionError):
        preview_canon_revision(base, {
            "schema": REVISION_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": audit_canon_source(
                base, authorized=True)["source_digest"],
            "edits": [{"section": "quest",
                       "path": ["stage_graph", 0, "alternatives", 0],
                       "value": NEW_CHOICE}],
        }, authorized=False)


def test_quest_choice_merge_and_cherry_pick_keep_other_story_edits():
    base = read_blueprint(PROJECT)
    left, _, _ = revise(base, 0, 0, NEW_CHOICE)
    right, _, _ = revise(
        base, 1, 0, "Publish thermal vent safety findings before the bout")
    merged, html, receipt, impact = merge_canon_revisions(
        base, left, right, authorized=True)
    assert receipt["merge_provenance"]["changed_field_count"] == 2
    assert impact["changed_path_count"] == 2
    assert b"Original interactive quest" in html
    assert compile_quest_program(merged).stages[1].alternatives[0] == (
        "Publish thermal vent safety findings before the bout")
    picked, _, cherry_receipt, _ = cherry_pick_canon_revision(
        base, left, right,
        [["quest", "stage_graph", 0, "alternatives", 0]], authorized=True)
    assert picked == merged
    assert cherry_receipt["cherry_pick_provenance"]["selected_count"] == 1
    with pytest.raises(StudioQuestError, match="conflict"):
        conflict, _, _ = revise(base, 0, 0, "Erase the archive survey without consent")
        cherry_pick_canon_revision(
            base, left, conflict,
            [["quest", "stage_graph", 0, "alternatives", 0]], authorized=True)


def test_quest_choice_cli_and_jeeves_share_canonical_editor(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    base = read_blueprint(PROJECT)
    source_digest = audit_canon_source(base, authorized=True)["source_digest"]
    edits = [{"section": "quest",
              "path": ["stage_graph", 0, "alternatives", 0],
              "value": NEW_CHOICE}]
    request = {"schema": REVISION_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source_digest, "edits": edits}
    output = tmp_path / "edited"
    assert main(["--project", PROJECT, "--author-revision",
                 "--revision-request", json.dumps(request),
                 "--output", str(output)]) == 0
    cli = json.loads(capsys.readouterr().out)
    typed = execute_author_revision_tool({
        **request, "schema": AUTHOR_REVISION_REQUEST_SCHEMA,
    }, authorized=True)
    assert cli["receipt"] == typed["detail"]
    assert typed["impact"]["new_save_required"] is True
    assert typed["file_write_performed"] is False
    assert load_revision_bundle(output, authorized=True,
                                project_id=PROJECT)[0]["quest"][
                                    "stage_graph"][0]["alternatives"][0] == NEW_CHOICE
