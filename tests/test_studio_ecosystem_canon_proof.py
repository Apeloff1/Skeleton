"""Original source canon proof and contradiction detection."""
from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def test_canon_proof_is_deterministic_and_does_not_mint_ending_evidence():
    docs = read_blueprint(PROJECT)
    proof = audit_canon_source(docs, authorized=True)
    assert proof == audit_canon_source(docs, authorized=True)
    assert proof["checked_scene_count"] == 3
    assert proof["canon_consistent"] is True
    assert proof["all_endings_proven"] is False
    assert any(e["external_evidence_required"] for e in proof["ending_obligations"])
    assert proof["release_certified"] is False


def test_canon_proof_reports_contradictory_era_and_unbound_dialogue():
    docs = deepcopy(read_blueprint(PROJECT))
    docs["narrative"]["canon"]["era_order"].reverse()
    docs["scene"]["episode_plan"][0]["dialogue_hook"] = "unlisted_person"
    proof = audit_canon_source(docs, authorized=True)
    kinds = {issue["kind"] for issue in proof["issues"]}
    assert "era_order" in kinds
    assert "unbound_dialogue_hook" in kinds
    assert proof["canon_consistent"] is False


def test_canon_proof_rejects_unauthorized_and_missing_sections():
    docs = read_blueprint(PROJECT)
    with pytest.raises(PermissionError):
        audit_canon_source(docs, authorized=False)
    broken = deepcopy(docs)
    del broken["cast"]
    with pytest.raises(StudioQuestError):
        audit_canon_source(broken, authorized=True)
