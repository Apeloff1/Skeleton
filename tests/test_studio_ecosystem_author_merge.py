"""Three-way original-world revision merge, replay, and adversarial bounds."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, load_revision_bundle, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_author_merge import merge_canon_revisions
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    AUTHOR_MERGE_REQUEST_SCHEMA, execute_author_merge_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def edit(source, section, path, value):
    request = {
        "schema": REVISION_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(source, authorized=True)["source_digest"],
        "edits": [{"section": section, "path": path, "value": value}],
    }
    return preview_canon_revision(source, request, authorized=True)


def test_independent_prose_revisions_merge_and_compile_playable(tmp_path):
    base = read_blueprint(PROJECT)
    original = deepcopy(base)
    left, left_html, left_receipt = edit(
        base, "narrative", ["premise"], "The glacial archive needs a public record.")
    right, right_html, right_receipt = edit(
        base, "cast", ["protagonist", "name"], "Miro Rook, custodian of the archive")
    merged, html, receipt, impact = merge_canon_revisions(
        base, left, right, authorized=True)
    assert base == original
    assert merged["narrative"]["premise"] == left["narrative"]["premise"]
    assert merged["cast"]["protagonist"]["name"] == right["cast"]["protagonist"]["name"]
    assert receipt["merge_provenance"]["conflict_count"] == 0
    assert receipt["merge_provenance"]["changed_field_count"] == 2
    assert impact["changed_path_count"] == 2
    assert impact["new_save_required"] is True
    assert b"Original interactive quest" in html
    assert replay_walk(merged, [], authorized=True).project_id == PROJECT
    destination = tmp_path / "merged"
    write_revision_bundle(destination, merged, html, receipt)
    assert load_revision_bundle(destination, authorized=True, project_id=PROJECT)[0] == merged
    assert json.loads((destination / "receipt.json").read_text()) == receipt
    assert left_html != html and right_html != html
    assert left_receipt["revised_source_digest"] != receipt["revised_source_digest"]
    assert right_receipt["revised_source_digest"] != receipt["revised_source_digest"]


def test_conflicting_edits_fail_before_any_export(tmp_path):
    base = read_blueprint(PROJECT)
    left, _, _ = edit(base, "narrative", ["premise"], "The archive must be audited.")
    right, _, _ = edit(base, "narrative", ["premise"], "The archive must be sealed.")
    with pytest.raises(StudioQuestError, match="conflict"):
        merge_canon_revisions(base, left, right, authorized=True)
    assert list(tmp_path.iterdir()) == []


def test_identical_overlapping_edits_are_idempotent():
    base = read_blueprint(PROJECT)
    left, _, _ = edit(base, "narrative", ["premise"], "The archive must be audited.")
    merged, _, receipt, _ = merge_canon_revisions(base, left, deepcopy(left), authorized=True)
    assert merged == left
    assert receipt["merge_provenance"]["changed_field_count"] == 1


def test_protected_fields_cross_project_and_authorization_fail_closed():
    base = read_blueprint(PROJECT)
    left, _, _ = edit(base, "narrative", ["premise"], "The archive must be audited.")
    with pytest.raises(PermissionError):
        merge_canon_revisions(base, left, left, authorized=False)
    forged = deepcopy(left)
    forged["quest"]["release_certified"] = True
    with pytest.raises(StudioQuestError):
        merge_canon_revisions(base, forged, left, authorized=True)
    foreign = read_blueprint("studio_puzzle_expedition_copper_mesa")
    with pytest.raises(StudioQuestError):
        merge_canon_revisions(base, left, foreign, authorized=True)


def test_jeeves_typed_merge_preview_and_conflict_rejection():
    base = read_blueprint(PROJECT)
    request = {
        "schema": AUTHOR_MERGE_REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(base, authorized=True)["source_digest"],
        "left_edits": [{"section": "narrative", "path": ["premise"],
                        "value": "The archive must be audited."}],
        "right_edits": [{"section": "cast", "path": ["protagonist", "name"],
                         "value": "Miro Rook, archive custodian"}],
    }
    with pytest.raises(PermissionError):
        execute_author_merge_tool(request, authorized=False)
    preview = execute_author_merge_tool(request, authorized=True)
    assert preview["file_write_performed"] is False
    assert preview["impact"]["changed_path_count"] == 2
    assert preview["release_certified"] is False
    with pytest.raises(StudioQuestError):
        execute_author_merge_tool({**request, "extra": True}, authorized=True)
    conflict = {**request, "right_edits": request["left_edits"][:-1] + [
        {**request["left_edits"][0], "value": "The archive must be sealed."}
    ]}
    with pytest.raises(StudioQuestError, match="conflict"):
        execute_author_merge_tool(conflict, authorized=True)


def test_cli_merges_verified_bundles_and_rejects_conflict(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    base = read_blueprint(PROJECT)
    left, left_html, left_receipt = edit(
        base, "narrative", ["premise"], "The archive must be audited.")
    right, right_html, right_receipt = edit(
        base, "cast", ["protagonist", "name"], "Miro Rook, archive custodian")
    left_dir, right_dir = tmp_path / "left", tmp_path / "right"
    write_revision_bundle(left_dir, left, left_html, left_receipt)
    write_revision_bundle(right_dir, right, right_html, right_receipt)
    destination = tmp_path / "merged"
    assert main(["--project", PROJECT, "--merge-revisions",
                 "--merge-left-source", str(left_dir),
                 "--merge-right-source", str(right_dir),
                 "--output", str(destination)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["impact"]["changed_path_count"] == 2
    assert (destination / "story.html").is_file()
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--merge-revisions",
              "--merge-left-source", str(left_dir),
              "--merge-right-source", str(left_dir),
              "--output", str(tmp_path / "missing")])
