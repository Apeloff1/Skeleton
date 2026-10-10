"""Provenance-bound source independence and adversarial holdout regressions."""
from dataclasses import replace
from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.webcrawler.dragon_knowledge_ledger import DragonKnowledgeLedger
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePass, EvidencePolicy, ProbabilisticKnowledgeDistiller,
)
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance
from skeleton.ai.webcrawler.dragon_provenance_registry import (
    ProvenanceRegistry, SourceAttestation,
)
from skeleton.ai.webcrawler.dragon_provenance_assurance import (
    AssurancePolicy, assure_crawler_evidence,
)


def source(sid, *, digest=None, uri=None, parents=(), tokens=()):
    return SourceProvenance(
        sid, digest or sha256(sid.encode("utf-8")).hexdigest(),
        uri or f"https://{sid}.example/research",
        tuple(parents), tuple(tokens),
    )


def read(sid, num=1, *, support=True, group=None, claim="claim-7",
         rev="v1", confidence=.9, reliability=.9):
    return EvidencePass(
        sid, rev, f"pass-{num}", claim, support, confidence, reliability,
        group or f"claimed-independent-{sid}", f"para:{num}",
        "Indexed original observation",
    )


def readings(sid, *, polarity=True, n=3, group=None):
    return tuple(read(sid, num, support=polarity, group=group)
                 for num in range(1, n + 1))


def evaluated(items=None, sources=None, **kwargs):
    if items is None:
        items = readings("alpha") + readings("beta")
    if sources is None:
        sources = (source("alpha"), source("beta"))
    return assure_crawler_evidence(
        "claim-7", items, sources, authorized=True, **kwargs,
    )


def test_two_independent_sources_with_full_coverage_are_review_candidates():
    report = evaluated()
    assert report.candidate_for_review
    assert report.needs_human_review
    assert not report.promotion_authorized
    assert report.belief.probability_semantics == "heuristic_logistic_score"
    assert report.independent_groups == 2
    assert report.provenance_relabels == 6
    assert report.minimum_heldout_probability >= .58
    assert all(h.remaining_groups == 1 for h in report.holdouts)
    assert not report.blockers
    assert not report.next_actions


def test_repeated_passes_never_create_independent_groups():
    manifest = (source("alpha"),)
    once = evaluated((read("alpha"),), manifest)
    repeated = evaluated(readings("alpha", n=10), manifest)
    assert once.independent_groups == repeated.independent_groups == 1
    assert once.belief.probability == repeated.belief.probability
    assert not repeated.candidate_for_review
    assert "insufficient_independent_sources" in repeated.blockers
    assert any(x.kind == "discover_independent_source"
               for x in repeated.next_actions)


def test_identical_content_overrides_forged_independence_labels():
    same = "d" * 64
    report = evaluated(sources=(
        source("alpha", digest=same),
        source("beta", digest=same),
    ))
    assert report.independent_groups == 1
    assert len(report.clusters) == 1
    assert "identical_content" in report.clusters[0].reasons
    assert "insufficient_independent_sources" in report.blockers
    assert not report.candidate_for_review


def test_explicit_derivation_and_transitive_lineage_conservatively_merge():
    items = readings("alpha") + readings("beta") + readings("gamma")
    report = evaluated(items, (
        source("alpha"),
        source("beta", parents=("alpha",)),
        source("gamma", tokens=("mirror",)),
        source("delta", tokens=("mirror",), parents=("beta",)),
    ))
    assert report.independent_groups == 1
    assert len(report.clusters[0].source_ids) == 4
    assert "declared_derivation" in report.clusters[0].reasons
    assert "shared_lineage" in report.clusters[0].reasons


def test_same_canonical_origin_merges_distinct_content_revisions():
    report = evaluated(sources=(
        source("alpha", uri="https://news.example/one?utm_term=x"),
        source("beta", uri="https://news.example/one?utm_term=y"),
    ))
    assert report.independent_groups == 1
    assert "canonical_origin" in report.clusters[0].reasons


def test_asserted_dependence_can_only_merge_never_split():
    report = evaluated(
        readings("alpha", group="shared")
        + readings("beta", group="shared"),
    )
    assert report.independent_groups == 1
    assert "asserted_shared_group" in report.clusters[0].reasons


def test_holdouts_expose_dominating_corroborator():
    evidence = readings("alpha") + readings("beta", polarity=False)
    report = evaluated(evidence)
    assert report.belief.conflicting
    assert report.minimum_heldout_probability < .5
    assert any(x.flips_majority for x in report.holdouts)
    assert "cross_source_contradiction" in report.blockers
    assert "fragile_to_source_removal" in report.blockers
    assert any(a.kind == "falsify_opposition" for a in report.next_actions)


def test_within_source_contradictions_are_not_suppressed():
    evidence = (read("alpha", 1, support=True),
                read("alpha", 2, support=False),
                read("alpha", 3, support=True))
    report = evaluated(evidence, (source("alpha"),))
    assert "cross_source_contradiction" in report.blockers
    assert any(a.kind == "resolve_internal_contradiction"
               for a in report.next_actions)


def test_reread_coverage_is_measured_per_revision():
    items = readings("alpha") + (read("alpha", rev="v2"),)
    report = evaluated(items, (source("alpha"),))
    assert not report.source_coverage_complete
    assert "incomplete_reread_coverage" in report.blockers
    assert any(a.kind == "reread_with_lens" and "@v2" in a.target
               for a in report.next_actions)


def test_empty_evidence_cannot_be_promoted_or_count_ghosts():
    report = evaluated((), (source("alpha"),))
    assert report.independent_groups == 0
    assert "no_evidence" in report.blockers
    assert not report.candidate_for_review
    assert not report.promotion_authorized
    assert not report.holdouts


def test_permutation_invariance_of_repeated_observations_and_manifest():
    items = readings("alpha") + readings("beta") + readings("gamma")
    sources = (source("alpha"), source("beta"), source("gamma"))
    first = evaluated(items, sources)
    shuffled = evaluated(tuple(reversed(items)), tuple(reversed(sources)))
    assert first.fingerprint == shuffled.fingerprint
    assert first.belief == shuffled.belief
    assert first.holdouts == shuffled.holdouts
    assert first.blockers == shuffled.blockers


def test_changed_custody_or_polarity_changes_assurance_fingerprint():
    items = readings("alpha") + readings("beta")
    before = evaluated(items)
    changed_evidence = evaluated(
        items[:-1] + (replace(items[-1], supports=False),),
    )
    changed_origin = evaluated(items, (
        source("alpha"),
        source("beta", uri="https://beta.example/altered"),
    ))
    assert before.fingerprint != changed_evidence.fingerprint
    assert before.fingerprint != changed_origin.fingerprint


def test_owner_ledger_readings_can_be_analyzed_without_mutation():
    ledger = DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    for item in readings("alpha") + readings("beta"):
        ledger.add("alice", item, authorized=True)
        ledger.add("bob", item, authorized=True)
    report = evaluated(
        ledger.readings("alice", "claim-7", authorized=True),
    )
    assert report.candidate_for_review
    assert len(ledger.readings("bob", "claim-7", authorized=True)) == 6


def test_action_budget_and_priority_are_deterministic():
    items = readings("alpha", n=1) + readings("beta", n=1, polarity=False)
    report = evaluated(
        items,
        assurance_policy=AssurancePolicy(maximum_actions=2),
    )
    assert len(report.next_actions) == 2
    assert list(report.next_actions) == sorted(
        report.next_actions,
        key=lambda a: (-a.priority, a.kind, a.target),
    )


@pytest.mark.parametrize("missing", [
    (), (source("other"),),
])
def test_all_observed_sources_require_manifest_custody(missing):
    with pytest.raises(ValueError, match="missing provenance"):
        evaluated((read("alpha"),), missing)


def test_unobserved_parent_may_exist_but_must_be_declared():
    manifest = (
        source("alpha", parents=("unobserved",)),
        source("unobserved"),
    )
    assert evaluated(readings("alpha"), manifest).independent_groups == 1
    with pytest.raises(ValueError, match="unknown provenance parent"):
        evaluated(readings("alpha"), manifest[:1])


def test_duplicate_provenance_identity_fails_closed():
    with pytest.raises(ValueError, match="duplicate provenance"):
        evaluated((read("alpha"),), (source("alpha"), source("alpha")))


@pytest.mark.parametrize("bad_uri", [
    "file:///etc/passwd",
    "http://127.0.0.1/admin",
    "http://localhost/private",
    "https://[::1]/secret",
    "not-an-absolute-url",
])
def test_malformed_or_private_provenance_origins_rejected(bad_uri):
    with pytest.raises(ValueError, match="untrusted provenance"):
        evaluated((read("alpha"),), (source("alpha", uri=bad_uri),))


def test_digest_and_lineage_token_validation():
    with pytest.raises(ValueError, match="digest"):
        evaluated((read("alpha"),), (source("alpha", digest="A" * 64),))
    with pytest.raises(ValueError, match="lineage"):
        evaluated((read("alpha"),), (source("alpha", tokens=("",)),))


def test_cross_claim_or_duplicate_pass_rejected():
    with pytest.raises(ValueError, match="cross-claim"):
        evaluated((read("alpha", claim="different"),), (source("alpha"),))
    with pytest.raises(ValueError, match="duplicate"):
        evaluated((read("alpha"), read("alpha")), (source("alpha"),))


def test_nonfinite_observation_fails_closed():
    with pytest.raises(ValueError, match="confidence"):
        evaluated(
            (read("alpha", confidence=float("nan")),),
            (source("alpha"),),
        )


def test_evidence_and_manifest_budgets_fail_closed():
    with pytest.raises(ValueError, match="evidence budget"):
        evaluated(
            readings("alpha"),
            (source("alpha"),),
            evidence_policy=EvidencePolicy(max_evidence=2),
        )
    with pytest.raises(ValueError, match="provenance source budget"):
        evaluated(
            (read("alpha"),),
            (source("alpha"), source("beta")),
            assurance_policy=AssurancePolicy(maximum_sources=1),
        )


@pytest.mark.parametrize("kwargs", [
    {"min_independent_groups": 1},
    {"maximum_sources": 0},
    {"maximum_actions": 0},
    {"min_heldout_probability": float("nan")},
    {"min_supporting_probability": 1.5},
])
def test_invalid_assurance_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        evaluated(assurance_policy=AssurancePolicy(**kwargs))


def test_authorization_is_mandatory_even_with_no_evidence():
    with pytest.raises(PermissionError):
        assure_crawler_evidence(
            "claim-7", (), (), authorized=False,
        )


def test_probability_is_not_presented_as_empirically_calibrated():
    result = evaluated()
    raw = ProbabilisticKnowledgeDistiller().distill(
        "claim-7", readings("alpha") + readings("beta"),
    )
    assert result.probability_semantics == "heuristic_logistic_score"
    assert raw.probability_semantics == result.probability_semantics
    assert result.needs_human_review
    assert not result.promotion_authorized


def test_credentialed_provenance_url_rejected():
    with pytest.raises(ValueError, match="untrusted provenance"):
        evaluated(
            (read("alpha"),),
            (source("alpha", uri="https://user:secret@alpha.example/data"),),
        )


def test_holdout_group_budget_fails_closed_before_quadratic_explosion():
    with pytest.raises(ValueError, match="holdout group budget"):
        evaluated(
            readings("alpha") + readings("beta") + readings("gamma"),
            (source("alpha"), source("beta"), source("gamma")),
            assurance_policy=AssurancePolicy(maximum_holdout_groups=2),
        )


def test_extended_reread_policy_emits_explicit_planning_gap():
    items = tuple(read("alpha", i) for i in range(1, 14))
    result = evaluated(
        items,
        (source("alpha"),),
        evidence_policy=EvidencePolicy(
            min_passes_per_source=13, max_passes_per_source=13,
        ),
    )
    assert result.source_coverage_complete
    assert any(x.kind == "extend_lens_schedule" for x in result.next_actions)


def test_reading_over_budget_is_rejected_before_manifests_are_clustered():
    with pytest.raises(ValueError, match="source reread budget"):
        evaluated(
            readings("alpha", n=13),
            (source("alpha"),),
        )


def attested(*, same_owner=False, same_syndication=False, omit_beta=False):
    entries = [
        SourceAttestation(
            "alpha.example", "publisher-a", "feed-1",
            "auditor", "signed-custody:alpha",
        ),
    ]
    if not omit_beta:
        entries.append(SourceAttestation(
            "beta.example", "publisher-a" if same_owner else "publisher-b",
            "feed-1" if same_syndication else "feed-2",
            "auditor", "signed-custody:beta",
        ))
    return ProvenanceRegistry(tuple(entries))


def test_attested_same_owner_merges_even_with_different_feeds():
    result = assure_crawler_evidence(
        "claim-7", readings("alpha") + readings("beta"),
        (source("alpha"), source("beta")),
        authorized=True, attestation_registry=attested(same_owner=True),
        assurance_policy=AssurancePolicy(require_attestations=True),
    )
    assert result.independent_groups == 1
    assert "attested_common_control" in result.clusters[0].reasons
    assert not result.candidate_for_review
    assert result.attestation_fingerprint


def test_shared_syndication_merges_separate_owners():
    report = assure_crawler_evidence(
        "claim-7", readings("alpha") + readings("beta"),
        (source("alpha"), source("beta")), authorized=True,
        attestation_registry=attested(same_syndication=True),
    )
    assert report.independent_groups == 1


def test_distinct_attested_ownership_and_feeds_stay_separate():
    report = assure_crawler_evidence(
        "claim-7", readings("alpha") + readings("beta"),
        (source("alpha"), source("beta")), authorized=True,
        attestation_registry=attested(),
        assurance_policy=AssurancePolicy(require_attestations=True),
    )
    assert report.candidate_for_review
    assert report.independent_groups == 2
    assert report.attestation_fingerprint


def test_missing_required_attestation_registry_fails_closed():
    with pytest.raises(ValueError, match="registry required"):
        evaluated(assurance_policy=AssurancePolicy(require_attestations=True))


def test_unattested_source_fails_closed_with_registry():
    with pytest.raises(ValueError, match="unattested source"):
        assure_crawler_evidence(
            "claim-7", readings("alpha") + readings("beta"),
            (source("alpha"), source("beta")), authorized=True,
            attestation_registry=attested(omit_beta=True),
        )


def test_registry_revision_changes_canonical_fingerprint():
    base = evaluated()
    with_registry = assure_crawler_evidence(
        "claim-7", readings("alpha") + readings("beta"),
        (source("alpha"), source("beta")), authorized=True,
        attestation_registry=attested(),
    )
    assert base.fingerprint != with_registry.fingerprint
    assert with_registry.attestation_fingerprint is not None


def test_relation_fanout_budget_rejects_pathological_manifests():
    manifest = (
        source("alpha", tokens=("first", "second", "third")),
    )
    with pytest.raises(ValueError, match="relationship budget"):
        evaluated(
            readings("alpha"), manifest,
            assurance_policy=AssurancePolicy(max_relationships_per_source=2),
        )


def test_duplicate_relationship_identity_rejected():
    with pytest.raises(ValueError, match="duplicate provenance relationship"):
        evaluated(
            readings("alpha"),
            (source("alpha", tokens=("copied", "copied")),),
        )


def test_untrusted_registry_implementation_rejected():
    with pytest.raises(TypeError, match="verified provenance registry"):
        assure_crawler_evidence(
            "claim-7", readings("alpha"), (source("alpha"),),
            authorized=True, attestation_registry=object(),
        )
