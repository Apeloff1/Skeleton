from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.contradiction_resolution import (
    ContradictionEvidence,
    resolve_contradictions,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_refresh import (
    EvidenceRefreshCandidate,
    plan_evidence_refresh,
)
from skeleton.ai.research.model_internals.reverse_engineering.experiment_replay import (
    ReplayExpectation,
    ReplayObservation,
    verify_experiment_replay,
)
from skeleton.ai.research.model_internals.reverse_engineering.power_audit import (
    PowerRequirement,
    audit_experiment_power,
)
from skeleton.ai.research.model_internals.reverse_engineering.reproducibility import (
    ReproductionRun,
    analyze_reproducibility,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_contradiction_resolution_requires_cross_domain_margin():
    report = resolve_contradictions(
        (
            ContradictionEvidence("a", "c", "attention", d("a"), True, 0.95),
            ContradictionEvidence("b", "c", "cache", d("b"), True, 0.9),
            ContradictionEvidence("c", "c", "artifact", d("c"), False, 0.1),
        )
    )[0]
    assert report.status == "supported"
    assert report.supporting_domain_count == 2
    assert report.margin > 0.5


def test_reproducibility_scores_identical_outputs_high():
    protocol = d("protocol")
    runs = (
        ReproductionRun("a", protocol, d("env1"), d("out"), 1.0),
        ReproductionRun("b", protocol, d("env2"), d("out"), 1.02),
        ReproductionRun("c", protocol, d("env3"), d("out"), 0.98),
    )
    report = analyze_reproducibility(runs)
    assert report.dominant_output_ratio == 1.0
    assert report.environment_count == 3
    assert report.reproducibility_score > 0.98


def test_evidence_refresh_prioritizes_stale_and_drifting_items():
    plan = plan_evidence_refresh(
        (
            EvidenceRefreshCandidate("fresh", d("f"), 1, 10, 0.2, 0.1),
            EvidenceRefreshCandidate("stale", d("s"), 20, 10, 0.4, 0.2),
            EvidenceRefreshCandidate("drift", d("d"), 2, 10, 0.5, 0.9),
        )
    )
    assert set(plan.must_refresh_ids) == {"stale", "drift"}
    assert plan.ordered_refresh_ids[0] == "stale"


def test_experiment_replay_requires_exact_step_outputs():
    expectations = (
        ReplayExpectation("a", d("ia"), d("oa")),
        ReplayExpectation("b", d("ib"), d("ob")),
    )
    exact = verify_experiment_replay(
        expectations,
        (
            ReplayObservation("a", d("oa")),
            ReplayObservation("b", d("ob")),
        ),
    )
    assert exact.exact_replay is True

    mismatch = verify_experiment_replay(
        expectations,
        (
            ReplayObservation("a", d("oa")),
            ReplayObservation("b", d("other")),
        ),
    )
    assert mismatch.exact_replay is False
    assert mismatch.mismatched_step_count == 1


def test_power_audit_flags_underpowered_experiment():
    report = audit_experiment_power(
        (
            PowerRequirement("a", 10, (("control", 10), ("treatment", 11))),
            PowerRequirement("b", 20, (("control", 18), ("treatment", 22))),
        )
    )
    assert report.powered_count == 1
    assert report.underpowered_count == 1
    assert report.all_powered is False
    underpowered = next(item for item in report.items if item.experiment_id == "b")
    assert underpowered.deficit == 2
