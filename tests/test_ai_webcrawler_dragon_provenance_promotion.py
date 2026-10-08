"""Custody manifests are mandatory at the crawler -> knowledge promotion boundary."""
from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionPolicy
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance
from skeleton.ai.webcrawler.dragon_provenance_promotion import (
    assess_custodied_promotion,
)


def reading(sid, index, *, supports=True, group=None):
    return EvidencePass(
        sid, "v1", f"pass-{index}", "buffered-jump", supports, 0.95, 0.95,
        group or f"fake-independent-{sid}", f"frame:{index}",
        "Observed game input and jump outcome",
    )


def corpus():
    return tuple(
        reading(sid, i)
        for sid in ("first", "second")
        for i in (1, 2, 3)
    )


def manifest(*, duplicate=False):
    return (
        SourceProvenance("first", "a" * 64, "https://one.example/game"),
        SourceProvenance("second", ("a" if duplicate else "b") * 64,
                         "https://two.example/game"),
    )


# Tests intentionally relax *other* promotion gates to isolate custody
# verification. Production defaults continue to require calibration and
# a full human-reviewed analysis chain.
RELAXED = PromotionPolicy(
    require_full_analysis=False,
    require_empirical_calibration=False,
)


def analyze(items=None, sources=None, policy=RELAXED):
    return assess_custodied_promotion(
        "buffered-jump",
        items if items is not None else corpus(),
        sources if sources is not None else manifest(),
        (), (), authorized=True, policy=policy,
    )


def test_complete_distinct_custody_reaches_decision_boundary():
    result = analyze()
    assert result.assurance.candidate_for_review
    assert result.decision.eligible
    assert result.normalized_evidence_digest == result.decision.evidence_digest
    assert result.manifest_fingerprint == result.assurance.fingerprint
    assert result.decision.probability_semantics == "heuristic_logistic_score"


def test_false_independence_from_duplicate_content_blocks_promotion():
    result = analyze(sources=manifest(duplicate=True))
    assert not result.assurance.candidate_for_review
    assert not result.decision.eligible
    assert any("independent" in reason.lower()
               for reason in result.decision.reasons)
    assert result.assurance.independent_groups == 1


def test_incomplete_rereads_block_even_when_source_groups_are_distinct():
    result = analyze(items=(reading("first", 1), reading("second", 1)))
    assert "incomplete_reread_coverage" in result.assurance.blockers
    assert not result.decision.eligible


def test_contradictions_are_exposed_in_both_promotion_and_custody_verdicts():
    items = corpus()
    items = items[:-1] + (replace(items[-1], supports=False),)
    result = analyze(items=items)
    assert result.assurance.belief.conflicting
    assert not result.decision.eligible
    assert any("contradict" in reason.lower()
               for reason in result.decision.reasons)


def test_default_full_analysis_and_calibration_remain_required():
    result = analyze(policy=PromotionPolicy())
    assert not result.decision.eligible
    assert "Eligible empirical calibration artifact required" in result.decision.reasons
    assert "Analysis chain is incomplete" in result.decision.reasons


def test_unknown_source_is_rejected_not_silently_excluded():
    with pytest.raises(ValueError, match="missing provenance"):
        analyze(sources=(manifest()[0],))


def test_cross_claim_injection_is_rejected_before_promotion():
    items = corpus()
    with pytest.raises(ValueError, match="cross-claim"):
        analyze(items=items[:-1] + (replace(items[-1], claim_id="other"),))


def test_custodied_promotion_requires_authorization():
    with pytest.raises(PermissionError):
        assess_custodied_promotion(
            "buffered-jump", corpus(), manifest(), (), (),
            authorized=False, policy=RELAXED,
        )


def test_source_manifest_order_does_not_change_decision():
    before = analyze()
    after = analyze(items=tuple(reversed(corpus())),
                    sources=tuple(reversed(manifest())))
    assert before.manifest_fingerprint == after.manifest_fingerprint
    assert before.decision == after.decision
