"""Selective original prose cherry-pick: CLI, typed Jeeves, replay and abuse."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, load_revision_bundle, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_author_cherry_pick import (
    CHERRY_PICK_SCHEMA, cherry_pick_canon_revision,
)
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import replay_walk
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    AUTHOR_CHERRY_PICK_REQUEST_SCHEMA, execute_author_cherry_pick_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
PREMISE = ["narrative", "premise"]
CAST = ["cast", "protagonist", "name"]


def edit(source, section, path, value):
    return preview_canon_revision(source, {
        "schema": REVISION_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(source, authorized=True)["source_digest"],
        "edits": [{"section": section, "path": path, "value": value}],
    }, authorized=True)


def branches():
    base = read_blueprint(PROJECT)
    donor, donor_html, donor_receipt = edit(
        base, "narrative", ["premise"], "The archive needs a public hearing.")
    target, target_html, target_receipt = edit(
        base, "cast", ["protagonist", "name"], "Miro Rook, archive keeper")
    return base, (donor, donor_html, donor_receipt), (target, target_html, target_receipt)


def test_cherry_pick_preserves_independent_target_and_compiles_playable(tmp_path):
    base, (donor, _, _), (target, _, _) = branches()
    original = deepcopy((base, donor, target))
    revised, html, receipt, impact = cherry_pick_canon_revision(
        base, donor, target, [PREMISE], authorized=True)
    assert (base, donor, target) == tuple(original)
    assert revised["narrative"]["premise"] == donor["narrative"]["premise"]
    assert revised["cast"]["protagonist"]["name"] == target["cast"]["protagonist"]["name"]
    assert receipt["cherry_pick_provenance"]["schema"] == CHERRY_PICK_SCHEMA
    assert receipt["cherry_pick_provenance"]["selected_count"] == 1
    assert receipt["base_source_digest"] == audit_canon_source(
        target, authorized=True)["source_digest"]
    assert receipt["release_certified"] is False
    assert impact["changed_path_count"] == 1
    assert impact["new_save_required"] is True
    assert b"Original interactive quest" in html
    assert replay_walk(revised, [], authorized=True).project_id == PROJECT
    directory = tmp_path / "cherry"
    write_revision_bundle(directory, revised, html, receipt)
    assert load_revision_bundle(directory, authorized=True, project_id=PROJECT)[0] == revised
    assert cherry_pick_canon_revision(base, donor, target, [PREMISE], authorized=True) == (
        revised, html, receipt, impact)


def test_cherry_pick_rejects_conflicts_and_noops():
    base = read_blueprint(PROJECT)
    donor, _, _ = edit(base, "narrative", ["premise"], "The archive must be audited.")
    conflict, _, _ = edit(base, "narrative", ["premise"], "The archive must be sealed.")
    with pytest.raises(StudioQuestError, match="conflict"):
        cherry_pick_canon_revision(base, donor, conflict, [PREMISE], authorized=True)
    with pytest.raises(StudioQuestError, match="no-op"):
        cherry_pick_canon_revision(base, donor, deepcopy(donor), [PREMISE], authorized=True)
    with pytest.raises(StudioQuestError, match="unchanged"):
        cherry_pick_canon_revision(base, donor, base, [CAST], authorized=True)


def test_cherry_pick_protected_fields_cross_project_and_bounds():
    base, (donor, _, _), (target, _, _) = branches()
    with pytest.raises(PermissionError):
        cherry_pick_canon_revision(base, donor, target, [PREMISE], authorized=False)
    forged = deepcopy(donor)
    forged["quest"]["stage_graph"][0]["reward"] = "unapproved_reward"
    with pytest.raises(StudioQuestError, match="protected"):
        cherry_pick_canon_revision(base, forged, target, [PREMISE], authorized=True)
    foreign = read_blueprint("studio_puzzle_expedition_copper_mesa")
    with pytest.raises(StudioQuestError, match="cross-project"):
        cherry_pick_canon_revision(base, foreign, target, [PREMISE], authorized=True)
    for paths in ([], [PREMISE] * 17, [PREMISE, PREMISE],
                  [["quest", "stage_graph", 0, "reward"]],
                  [["narrative", "premise", True]], [["narrative"]]):
        with pytest.raises(StudioQuestError):
            cherry_pick_canon_revision(base, donor, target, paths, authorized=True)


def test_cli_cherry_pick_verified_bundles_and_rejects_malformed_paths(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    base, (donor, donor_html, donor_receipt), (target, target_html, target_receipt) = branches()
    donor_dir, target_dir = tmp_path / "donor", tmp_path / "target"
    write_revision_bundle(donor_dir, donor, donor_html, donor_receipt)
    write_revision_bundle(target_dir, target, target_html, target_receipt)
    output = tmp_path / "result"
    assert main(["--project", PROJECT, "--cherry-pick-revision",
                 "--revision-compare-source", str(donor_dir),
                 "--revision-source", str(target_dir),
                 "--cherry-pick-paths", json.dumps([PREMISE]),
                 "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"]["cherry_pick_provenance"]["selected_count"] == 1
    assert load_revision_bundle(output, authorized=True, project_id=PROJECT)[0][
        "cast"]["protagonist"]["name"] == target["cast"]["protagonist"]["name"]
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--cherry-pick-revision",
              "--revision-compare-source", str(donor_dir),
              "--cherry-pick-paths", json.dumps([PREMISE, PREMISE]),
              "--output", str(tmp_path / "rejected")])
    assert not (tmp_path / "rejected").exists()


def test_jeeves_cherry_pick_typed_preview_rejects_untrusted_requests():
    base = read_blueprint(PROJECT)
    request = {
        "schema": AUTHOR_CHERRY_PICK_REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(base, authorized=True)["source_digest"],
        "donor_edits": [{"section": "narrative", "path": ["premise"],
                         "value": "The archive must be audited."}],
        "target_edits": [{"section": "cast", "path": ["protagonist", "name"],
                          "value": "Miro Rook, archive keeper"}],
        "selected_paths": [PREMISE],
    }
    with pytest.raises(PermissionError):
        execute_author_cherry_pick_tool(request, authorized=False)
    result = execute_author_cherry_pick_tool(request, authorized=True)
    assert result["detail"]["cherry_pick_provenance"]["selected_count"] == 1
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        execute_author_cherry_pick_tool({**request, "extra": True}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_author_cherry_pick_tool({**request, "expected_source_digest": "0" * 64},
                                        authorized=True)
    conflict = {**request, "target_edits": request["donor_edits"]}
    with pytest.raises(StudioQuestError):
        execute_author_cherry_pick_tool(conflict, authorized=True)

def test_cherry_pick_rejects_protected_target_mutation_and_receipt_tampering(tmp_path):
    base, (donor, _, _), (target, _, _) = branches()
    forged_target = deepcopy(target)
    forged_target["quest"]["stage_graph"][0]["reward"] = "unapproved_reward"
    with pytest.raises(StudioQuestError, match="protected"):
        cherry_pick_canon_revision(base, donor, forged_target, [PREMISE],
                                   authorized=True)
    revised, html, receipt, _ = cherry_pick_canon_revision(
        base, donor, target, [PREMISE], authorized=True)
    forged_receipt = deepcopy(receipt)
    forged_receipt["cherry_pick_provenance"]["selected_count"] = 2
    with pytest.raises(StudioQuestError, match="drift"):
        write_revision_bundle(tmp_path / "forged", revised, html, forged_receipt)
    assert not (tmp_path / "forged").exists()
