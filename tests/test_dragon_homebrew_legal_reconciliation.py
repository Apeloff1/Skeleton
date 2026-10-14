"""Fail-closed homebrew and legal-change regression for Dragon reconciliation.

These tests do not grant release authority, run a crawler or access an SDK.
"""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.dragon_porting import (
    MechanicInfusion, REVIEW_AREAS, legal_release_blockers, plan_homebrew_port,
)
from skeleton.ai.game_builder.dragon_legal_updates import (
    LegalSourceObservation, legal_update_impact, legal_recrawl_plan,
)

ARTIFACT = "a" * 64
MECHANIC = "b" * 64


def test_missing_human_reviews_block_every_jurisdiction_area():
    blockers = legal_release_blockers(
        artifact_digest=ARTIFACT, target_id="pc_windows",
        jurisdictions=("NO", "US"), reviews=(), now=1_000,
    )
    assert len(blockers) == 2 * len(REVIEW_AREAS)
    assert all("missing review" in reason for reason in blockers)


def test_plan_is_design_only_and_never_proclaims_release():
    mechanic = MechanicInfusion(
        mechanic_id="jump-arc", abstract_rule="original arc trajectory",
        source_reference_id="abstract-platformer", independent_design_digest=MECHANIC,
        historical_cost_bytes=512, desktop_enhancement="interpolation",
    )
    report = plan_homebrew_port(
        source_target="pc_windows", destination_target="pc_windows",
        style="2d", mechanics=(mechanic,), preserve=("pixel proportions",),
        memory_budget_bytes=4096, artifact_digest=ARTIFACT,
        jurisdictions=("NO",), reviews=(), now=1_000,
    )
    assert report["build_state"] == "not_built"
    assert report["gameplay_state"] == "not_verified"
    assert report["release_authority"] is False
    assert report["release_blockers"]
    assert report["mechanics"][0]["implementation_state"] == "design_only"


def test_primary_source_identity_and_custody_are_required():
    with pytest.raises(ValueError):
        LegalSourceObservation(
            source_id="law", url="http://localhost/policy",
            jurisdiction="NO", areas=frozenset({"copyright"}),
            content_digest=ARTIFACT, captured_at=1_000,
            custody_evidence_digest=MECHANIC, provenance=None,
        )


def test_empty_legal_baseline_cannot_claim_no_change():
    with pytest.raises(ValueError, match="baseline"):
        legal_update_impact((), (), (), now=1_000)
    with pytest.raises(ValueError, match="source"):
        legal_recrawl_plan((), now=1_000)
