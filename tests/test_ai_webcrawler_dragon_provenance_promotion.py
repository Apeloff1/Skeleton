"""Custody manifests are mandatory at the crawler -> knowledge promotion boundary."""
from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionPolicy
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance
from skeleton.ai.webcrawler.dragon_provenance_registry import (
    ProvenanceRegistry, SourceAttestation,
)
from skeleton.ai.webcrawler.dragon_provenance_assurance import AssurancePolicy
from skeleton.ai.webcrawler.dragon_provenance_promotion import (
    EmpiricalCitation, assess_custodied_promotion,
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
        empirical_citations=citations(items, sources), now=1000,
        attestation_registry=verified_registry(),
    )


def citations(items=None, sources=None):
    items = corpus() if items is None else items
    sources = manifest() if sources is None else sources
    return tuple(EmpiricalCitation(
        s.source_id, "v1", "buffered-jump", s.canonical_uri, s.content_digest,
        "study-" + s.source_id, s.canonical_uri + "/data", s.content_digest,
        "benchmark", "Run 100 recorded input sequences on the documented build.",
        "95 of 100 inputs produced a jump in the measured buffer window.", 100,
        "Applies only to the recorded build and input settings.",
        "Synthetic fixture; no external empirical claim is made.",
        "independent_lab", s.canonical_uri + "/methods",
        "reviewer", s.canonical_uri + "/review",
        tuple(sorted({r.evidence_locator for r in items if r.source_id == s.source_id})),
        900, 2000,
    ) for s in sources if any(r.source_id == s.source_id for r in items))


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


def verified_registry(*, same_owner=False):
    return ProvenanceRegistry((
        SourceAttestation(
            "one.example", "editorial-a", "distribution-a", "audit", "record-a",
        ),
        SourceAttestation(
            "two.example", "editorial-a" if same_owner else "editorial-b",
            "distribution-b", "audit", "record-b",
        ),
    ))


def test_promotion_rejects_shared_attested_owner():
    result = assess_custodied_promotion(
        "buffered-jump", corpus(), manifest(), (), (),
        authorized=True, policy=RELAXED,
        assurance_policy=AssurancePolicy(require_attestations=True),
        attestation_registry=verified_registry(same_owner=True),
    )
    assert not result.decision.eligible
    assert result.assurance.independent_groups == 1
    assert "Custody assurance: insufficient independent sources" in result.decision.reasons


def test_promotion_accepts_distinct_attested_owners_with_relaxed_other_gates():
    result = assess_custodied_promotion(
        "buffered-jump", corpus(), manifest(), (), (),
        authorized=True, policy=RELAXED,
        assurance_policy=AssurancePolicy(require_attestations=True),
        attestation_registry=verified_registry(),
        empirical_citations=citations(), now=1000,
    )
    assert result.assurance.candidate_for_review
    assert result.decision.eligible


def test_promotion_requires_verified_registry_when_attestations_mandatory():
    with pytest.raises(ValueError, match="registry required"):
        assess_custodied_promotion(
            "buffered-jump", corpus(), manifest(), (), (),
            authorized=True, policy=RELAXED,
            assurance_policy=AssurancePolicy(require_attestations=True),
        )


def empirical_review(records=None, **kwargs):
    return assess_custodied_promotion(
        "buffered-jump", corpus(), manifest(), (), (), authorized=True,
        policy=RELAXED, attestation_registry=verified_registry(),
        empirical_citations=citations() if records is None else records,
        now=kwargs.pop("now", 1000), **kwargs,
    )


def test_missing_empirical_citations_fail_closed_even_with_relaxed_policy():
    result = empirical_review(())
    assert not result.decision.eligible
    assert sum("Empirical citation review missing" in x for x in result.decision.reasons) == 2


@pytest.mark.parametrize("clock", [None, 899, 2000, 2500])
def test_empirical_review_requires_current_trusted_clock(clock):
    assert not empirical_review(now=clock).decision.eligible


@pytest.mark.parametrize("field,value", [
    ("study_id", "study-first"), ("artifact_digest", "a" * 64),
])
def test_shared_experiment_or_artifact_cannot_be_two_sources(field, value):
    records = citations()
    result = empirical_review((records[0], replace(records[1], **{field: value})))
    assert result.assurance.independent_groups == 1
    assert not result.decision.eligible


@pytest.mark.parametrize("field,value", [
    ("source_digest", "f" * 64), ("source_revision", "v2"),
    ("claim_id", "another-claim"), ("reviewed_locators", ("unrelated-section",)),
    ("source_url", "https://unrelated.example/page"),
])
def test_empirical_citation_cannot_be_rebound(field, value):
    records = citations()
    with pytest.raises(ValueError, match="bind exact"):
        empirical_review((replace(records[0], **{field: value}), records[1]))


@pytest.mark.parametrize("field,value", [
    ("methods", ""), ("measured_result", ""), ("limitations", ""),
    ("applicability", ""), ("sample_size", True), ("sample_size", 0),
    ("reputation_basis", "popular"), ("evidence_kind", "opinion"),
    ("artifact_digest", ""), ("reputation_reference", "http://127.0.0.1/"),
    ("expires_at", float("nan")),
])
def test_reputation_never_substitutes_for_empirical_review(field, value):
    records = citations()
    with pytest.raises(ValueError):
        empirical_review((replace(records[0], **{field: value}), records[1]))


def test_review_digest_binds_methods_clock_and_citations_order_independently():
    first = empirical_review()
    assert first.empirical_review_digest == empirical_review(tuple(reversed(citations()))).empirical_review_digest
    assert first.empirical_review_digest != empirical_review(now=1001).empirical_review_digest
    records = citations()
    changed = empirical_review((replace(records[0], methods="Different measured protocol"), records[1]))
    assert first.empirical_review_digest != changed.empirical_review_digest
    assert first.citations == tuple(sorted(citations(), key=lambda c: c.source_id))


def test_publisher_ownership_attestation_is_mandatory_for_empirical_gate():
    result = assess_custodied_promotion(
        "buffered-jump", corpus(), manifest(), (), (), authorized=True,
        policy=RELAXED, empirical_citations=citations(), now=1000,
    )
    assert not result.decision.eligible
    assert "Verified publisher ownership registry required" in result.decision.reasons


def test_duplicate_reviews_and_unbounded_inputs_fail_closed():
    from itertools import repeat
    with pytest.raises(ValueError, match="duplicate"):
        empirical_review((citations()[0], citations()[0]))
    with pytest.raises(ValueError, match="budget"):
        assess_custodied_promotion(
            "buffered-jump", repeat(corpus()[0]), manifest(), (), (),
            authorized=True, policy=RELAXED,
        )
    with pytest.raises(ValueError, match="budget"):
        empirical_review(repeat(citations()[0]))


def test_truthy_authorization_cannot_admit_empirical_reviews():
    with pytest.raises(PermissionError):
        assess_custodied_promotion(
            "buffered-jump", corpus(), manifest(), (), (),
            authorized="yes", policy=RELAXED,
        )
