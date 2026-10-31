"""Source-leased original authoring history, CLI and typed Jeeves parity."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision, write_revision_bundle,
)
from skeleton.ai.game_builder.studio_ecosystem_author_lineage import trace_canon_lineage
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    AUTHOR_LINEAGE_REQUEST_SCHEMA, execute_author_lineage_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def revision(source, section, path, value):
    return preview_canon_revision(source, {
        "schema": REVISION_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(source, authorized=True)["source_digest"],
        "edits": [{"section": section, "path": path, "value": value}],
    }, authorized=True)


def test_two_step_lineage_replays_original_source_and_rejects_reorder(tmp_path):
    base = read_blueprint(PROJECT)
    first, first_html, first_receipt = revision(
        base, "narrative", ["premise"], "The archive must be audited.")
    second, second_html, second_receipt = revision(
        first, "cast", ["protagonist", "name"], "Miro Rook, archive custodian")
    chain = [(first, first_receipt), (second, second_receipt)]
    proof = trace_canon_lineage(base, chain, authorized=True)
    assert proof == trace_canon_lineage(base, deepcopy(chain), authorized=True)
    assert proof["step_count"] == 2
    assert proof["steps"][1]["parent_source_digest"] == proof["steps"][0]["source_digest"]
    assert proof["head_source_digest"] == second_receipt["revised_source_digest"]
    assert proof["existing_root_save_lease_valid"] is False
    assert proof["release_certified"] is False
    with pytest.raises(StudioQuestError):
        trace_canon_lineage(base, chain[::-1], authorized=True)
    with pytest.raises(StudioQuestError):
        trace_canon_lineage(base, [chain[0], chain[0]], authorized=True)
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    write_revision_bundle(first_dir, first, first_html, first_receipt)
    write_revision_bundle(second_dir, second, second_html, second_receipt)
    from scripts.studio_ecosystem_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import load_revision_bundle
    assert main(["--project", PROJECT, "--revision-lineage",
                 "--revision-lineage-source", str(first_dir),
                 "--revision-lineage-source", str(second_dir)]) == 0
    assert load_revision_bundle(second_dir, authorized=True, project_id=PROJECT)[0] == second


def test_lineage_rejects_tampered_receipts_and_unauthorized():
    base = read_blueprint(PROJECT)
    first, _, receipt = revision(
        base, "narrative", ["premise"], "The archive must be audited.")
    with pytest.raises(PermissionError):
        trace_canon_lineage(base, [(first, receipt)], authorized=False)
    forged = {**receipt, "base_source_digest": "0" * 64}
    with pytest.raises(StudioQuestError):
        trace_canon_lineage(base, [(first, forged)], authorized=True)
    with pytest.raises(StudioQuestError):
        trace_canon_lineage(base, [], authorized=True)
    with pytest.raises(StudioQuestError):
        trace_canon_lineage(base, [(first, receipt)] * 9, authorized=True)


def test_jeeves_lineage_preview_is_typed_and_operator_gated():
    base = read_blueprint(PROJECT)
    req = {
        "schema": AUTHOR_LINEAGE_REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": audit_canon_source(base, authorized=True)["source_digest"],
        "edit_batches": [
            [{"section": "narrative", "path": ["premise"],
              "value": "The archive must be audited."}],
            [{"section": "cast", "path": ["protagonist", "name"],
              "value": "Miro Rook, archive custodian"}],
        ],
    }
    with pytest.raises(PermissionError):
        execute_author_lineage_tool(req, authorized=False)
    result = execute_author_lineage_tool(req, authorized=True)
    assert result["detail"]["step_count"] == 2
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        execute_author_lineage_tool({**req, "expected_source_digest": "0" * 64},
                                    authorized=True)
    with pytest.raises(StudioQuestError):
        execute_author_lineage_tool({**req, "edit_batches": [[]]}, authorized=True)


def test_lineage_rejects_protected_change_even_with_self_consistent_digest():
    from skeleton.ai.game_builder.studio_ecosystem_author_revision import _digest
    from skeleton.ai.game_builder.studio_ecosystem_story_html import render_story_html
    from hashlib import sha256
    base = read_blueprint(PROJECT)
    source, _, receipt = revision(
        base, "narrative", ["premise"], "The archive must be audited.")
    forged = deepcopy(source)
    forged["quest"]["stage_graph"][0]["reward"] = "unapproved_quest_reward"
    proof = audit_canon_source(forged, authorized=True)
    assert proof["canon_consistent"] is True
    forged_receipt = deepcopy(receipt)
    forged_receipt["revised_source_digest"] = proof["source_digest"]
    forged_receipt["revised_proof_digest"] = proof["proof_digest"]
    forged_receipt["playable_html_sha256"] = sha256(render_story_html(forged)).hexdigest()
    forged_receipt.pop("receipt_digest")
    forged_receipt["receipt_digest"] = _digest(forged_receipt)
    with pytest.raises(StudioQuestError, match="protected"):
        trace_canon_lineage(base, [(forged, forged_receipt)], authorized=True)
