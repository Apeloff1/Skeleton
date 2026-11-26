"""Original authored revision impact and conservative save replay fencing."""
from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision,
)
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_revision_impact import (
    compare_revision_sources,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"

def test_revision_impact_reports_precise_prose_and_requires_new_replay():
    docs = read_blueprint(PROJECT)
    req = {"schema": REVISION_SCHEMA, "project_id": PROJECT,
           "expected_source_digest": audit_canon_source(docs, authorized=True)["source_digest"],
           "edits": [{"section": "narrative", "path": ["premise"],
                      "value": "A new, independent audit of the ice-locked archive is required."}]}
    revised, _, _ = preview_canon_revision(docs, req, authorized=True)
    impact = compare_revision_sources(docs, revised, authorized=True)
    assert impact == compare_revision_sources(docs, revised, authorized=True)
    assert impact["changed_path_count"] == 1
    assert impact["changed_paths"][0]["path"] == ["narrative", "premise"]
    assert impact["authored_gameplay_contract_unchanged"] is True
    assert impact["rendered_playable_html_changed"] is True
    assert impact["existing_save_replay_lease_valid"] is False
    assert impact["new_save_required"] is True
    assert impact["release_certified"] is False

def test_revision_impact_same_source_and_rejects_unauthorized_or_cross_project():
    docs = read_blueprint(PROJECT)
    unchanged = compare_revision_sources(docs, deepcopy(docs), authorized=True)
    assert unchanged["changed_path_count"] == 0
    assert unchanged["existing_save_replay_lease_valid"] is True
    with pytest.raises(PermissionError):
        compare_revision_sources(docs, docs, authorized=False)
    other = read_blueprint("studio_puzzle_expedition_copper_mesa")
    with pytest.raises(StudioQuestError):
        compare_revision_sources(docs, other, authorized=True)
