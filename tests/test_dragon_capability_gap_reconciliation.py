"""Fail-closed and evidence-bound Dragon capability review reconciliation."""
from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.dragon_capability_gap_matrix import CapabilityGap, prioritize_gaps
from skeleton.ai.game_builder.dragon_industry_domains import INDUSTRY_DOMAINS, ALMANAC_SECTIONS


def gap(value="original-grid", *, checked=2, total=10, importance=1.0, expires=2000.0):
    return CapabilityGap("mechanic", value, total, checked, importance, "human-review-001", expires)


def test_ranks_measured_unmet_checks_without_claiming_a_model_score():
    priorities = prioritize_gaps((gap("medium", checked=5, importance=0.5), gap()), now=1000.0)
    assert [item.value for item in priorities] == ["original-grid", "medium"]
    assert priorities[0].score == 0.8
    assert priorities[0].missing_checks == 8
    assert priorities[0].review_ref == "human-review-001"


def test_expired_reviews_and_fully_covered_capabilities_are_excluded():
    assert prioritize_gaps((gap(expires=1000.0), gap("complete", checked=10)), now=1000.0) == ()


def test_duplicate_gap_and_excess_matrix_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        prioritize_gaps((gap(), gap()), now=1000.0)
    with pytest.raises(ValueError, match="budget"):
        prioritize_gaps((gap(),), now=1000.0, max_results=0)
    with pytest.raises(ValueError, match="budget"):
        prioritize_gaps(tuple(gap(str(i)) for i in range(129)), now=1000.0)


@pytest.mark.parametrize("values", [
    {"expected_checks": 0},
    {"passed_checks": 11},
    {"importance": float("nan")},
    {"expires_at": float("inf")},
    {"factor": "unknown"},
    {"review_ref": ""},
])
def test_noncredible_gap_evidence_cannot_enter_prioritization(values):
    with pytest.raises(ValueError):
        replace(gap(), **values)


def test_industry_taxonomy_is_structured_not_a_knowledge_claim():
    names = [name for name, sections in INDUSTRY_DOMAINS]
    assert len(names) == len(set(names))
    assert "research_integrity" in names
    assert "accessibility" in names
    assert all(name and sections and all(section.strip() for section in sections)
               for name, sections in INDUSTRY_DOMAINS)
    assert "Rights" in ALMANAC_SECTIONS
