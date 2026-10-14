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


def _authority(method_id: str, evidence_digest: str):
    from skeleton.ai.game_builder.contracts import EvaluatorProvenance

    return EvaluatorProvenance(
        evaluator_id="independent-custody-operator",
        operation_id="legal-2026-10-14",
        execution_id="legal-exec-01",
        execution_identity_digest="1" * 64,
        finalization_intent_digest="2" * 64,
        authority_kind="deterministic_control",
        authority_identity_digest="3" * 64,
        method_id=method_id,
        source_revision="4" * 40,
        output_evidence_refs=(evidence_digest,),
    )


def _observation(source_digest: str, captured_at: int):
    return LegalSourceObservation(
        source_id="copyright-statute-01",
        url="https://lovdata.no/dokument/NL/lov/1961-05-12-2",
        jurisdiction="NO",
        areas=frozenset({"copyright"}),
        content_digest=source_digest,
        captured_at=captured_at,
        custody_evidence_digest="9" * 64,
        provenance=_authority("crawler-legal-custody", "9" * 64),
    )


def test_same_second_legal_change_invalidates_existing_clearance():
    from skeleton.ai.game_builder.dragon_porting import JurisdictionReview

    review = JurisdictionReview(
        artifact_digest=ARTIFACT,
        target_id="pc_windows",
        jurisdiction="NO",
        area="copyright",
        disposition="cleared",
        checked_at=2_000,
        expires_at=3_000,
        evidence_digest="8" * 64,
        authority=_authority("human-legal-review", "8" * 64),
    )
    impact = legal_update_impact(
        (_observation("a" * 64, 1_000),),
        (_observation("b" * 64, 2_000),),
        (review,),
        now=2_000,
    )
    assert impact["requires_human_review"] is True
    assert impact["release_authority"] is False
    assert impact["invalidated_reviews"] == [[ARTIFACT, "pc_windows", "NO", "copyright"]]
    assert impact["events"][0]["reason"] == "primary_source_body_changed"


def test_unchanged_primary_source_never_infers_a_legal_change():
    original = _observation("a" * 64, 1000)
    refresh = _observation("a" * 64, 2000)
    report = legal_update_impact((original,), (refresh,), (), now=2000)
    assert report["events"] == []
    assert report["affected_cells"] == []
    assert report["release_authority"] is False


@pytest.mark.parametrize("url", (
    "\nhttps://lovdata.no/dokument/NL/lov/1961-05-12-2",
    "https://lovdata.no/path\r\n",
    "https://lovdata.no:invalid/dokument/",
    "https://lovdata.no",
    "https://lovdata.no/dokument/#fragment",
    "https://lovdata.no.evil.example/dokument/",
))
def test_primary_source_url_cannot_hide_whitespace_or_ambiguous_authority(url):
    with pytest.raises(ValueError):
        LegalSourceObservation(
            source_id="legal-source",
            url=url,
            jurisdiction="NO",
            areas=frozenset({"copyright"}),
            content_digest=ARTIFACT,
            captured_at=1_000,
            custody_evidence_digest=MECHANIC,
            provenance=_authority("crawler-legal-custody", MECHANIC),
        )
