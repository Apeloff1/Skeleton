from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.automation.swarm.handoff import TaskEnvelope, TaskState
from skeleton.automation.swarm.multi_agent_orchestration import (
    ArbitrationCandidate,
    ArbitrationStatus,
    BoundedOrchestrationPolicy,
    ConflictDomain,
    ConflictDomainBusy,
    ConflictDomainRegistry,
    EvidenceArbitrator,
    EvidenceClaim,
    MultiAgentOrchestrationError,
    MultiAgentOrchestrator,
)


NOW = 1_800_000_000.0


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _envelope(
    task_id: str = "task-1",
    *,
    requester: str = "supervisor-1",
    assignee: str = "worker-1",
    payload: dict | None = None,
) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        capability="repo.write",
        input={"path": "a.py", "patch": "x"} if payload is None else payload,
        requester=requester,
        state=TaskState.WORKING,
        assignee=assignee,
        created_at=NOW - 10.0,
        updated_at=NOW - 5.0,
    )


def _claim(
    verifier: str,
    subject: str,
    *,
    verified: bool = True,
) -> EvidenceClaim:
    return EvidenceClaim(
        verifier_id=verifier,
        subject_digest=subject,
        evidence_refs=(f"evidence:{verifier}:{subject[:8]}",),
        verified=verified,
    )


def _candidate(
    candidate_id: str,
    label: str,
    *,
    verifiers: tuple[str, ...] = (),
    rejected_verifiers: tuple[str, ...] = (),
) -> ArbitrationCandidate:
    output = _digest(label)
    claims = tuple(
        _claim(verifier, output, verified=True)
        for verifier in verifiers
    ) + tuple(
        _claim(verifier, output, verified=False)
        for verifier in rejected_verifiers
    )
    return ArbitrationCandidate(
        candidate_id=candidate_id,
        output_digest=output,
        claims=claims,
    )


def _orchestrator(
    *,
    max_fanout: int = 4,
    max_domains: int = 2,
    max_candidates: int = 4,
    min_verifiers: int = 1,
) -> MultiAgentOrchestrator:
    policy = BoundedOrchestrationPolicy(
        max_fanout=max_fanout,
        max_conflict_domains_per_task=max_domains,
        max_arbitration_candidates=max_candidates,
        min_independent_verifiers=min_verifiers,
    )
    orchestrator = MultiAgentOrchestrator(policy=policy)
    orchestrator.conflicts.register(
        ConflictDomain(
            "repo:a.py",
            "repo:Apeloff1/Skeleton:path:a.py",
            "exclusive mutation ownership for a.py",
        )
    )
    orchestrator.conflicts.register(
        ConflictDomain(
            "repo:b.py",
            "repo:Apeloff1/Skeleton:path:b.py",
            "exclusive mutation ownership for b.py",
        )
    )
    return orchestrator


def test_conflict_domain_registration_is_idempotent_but_resource_unique() -> None:
    registry = ConflictDomainRegistry()
    domain = ConflictDomain("repo:a.py", "repo:path:a.py")

    assert registry.register(domain) == domain
    assert registry.register(domain) == domain

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="resource key is already owned",
    ):
        registry.register(
            ConflictDomain("other:a.py", "repo:path:a.py")
        )

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="already bound differently",
    ):
        registry.register(
            ConflictDomain(
                "repo:a.py",
                "repo:path:other.py",
            )
        )


def test_live_conflict_domain_allows_only_one_mutation_owner() -> None:
    registry = ConflictDomainRegistry()
    registry.register(ConflictDomain("repo:a.py", "repo:path:a.py"))

    first = registry.acquire(
        "repo:a.py",
        task_id="task-1",
        worker_id="worker-1",
        ttl_s=30.0,
        now=NOW,
    )

    replay = registry.acquire(
        "repo:a.py",
        task_id="task-1",
        worker_id="worker-1",
        ttl_s=30.0,
        now=NOW + 1.0,
    )
    assert replay == first

    with pytest.raises(ConflictDomainBusy):
        registry.acquire(
            "repo:a.py",
            task_id="task-2",
            worker_id="worker-2",
            ttl_s=30.0,
            now=NOW + 1.0,
        )


def test_reissued_domain_lease_fences_stale_worker_generation() -> None:
    registry = ConflictDomainRegistry()
    registry.register(ConflictDomain("repo:a.py", "repo:path:a.py"))

    first = registry.acquire(
        "repo:a.py",
        task_id="task-1",
        worker_id="worker-1",
        ttl_s=5.0,
        now=NOW,
    )
    second = registry.acquire(
        "repo:a.py",
        task_id="task-2",
        worker_id="worker-2",
        ttl_s=5.0,
        now=NOW + 6.0,
    )

    assert second.fence.generation == first.fence.generation + 1
    assert second.lease_id != first.lease_id

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="stale fencing token generation",
    ):
        registry.assert_fence(first, now=NOW + 6.5)

    assert registry.assert_fence(second, now=NOW + 6.5) == second


def test_released_domain_reissue_also_invalidates_old_fence() -> None:
    registry = ConflictDomainRegistry()
    registry.register(ConflictDomain("repo:a.py", "repo:path:a.py"))

    first = registry.acquire(
        "repo:a.py",
        task_id="task-1",
        worker_id="worker-1",
        ttl_s=30.0,
        now=NOW,
    )
    registry.release(first, now=NOW + 1.0)

    second = registry.acquire(
        "repo:a.py",
        task_id="task-2",
        worker_id="worker-2",
        ttl_s=30.0,
        now=NOW + 2.0,
    )

    assert second.fence.generation == 2
    with pytest.raises(
        MultiAgentOrchestrationError,
        match="stale fencing token generation",
    ):
        registry.assert_fence(first, now=NOW + 3.0)


def test_handoff_binding_is_canonical_and_domain_bounded() -> None:
    orchestrator = _orchestrator()

    left = orchestrator.bind_handoffs(
        [_envelope(payload={"path": "a.py", "patch": "x"})],
        conflict_domains_by_task={"task-1": ("repo:a.py",)},
    )[0]
    right = orchestrator.bind_handoffs(
        [_envelope(payload={"patch": "x", "path": "a.py"})],
        conflict_domains_by_task={"task-1": ("repo:a.py",)},
    )[0]

    assert left.payload_digest == right.payload_digest
    assert left.digest == right.digest

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="bounded maximum",
    ):
        orchestrator.bind_handoffs(
            [_envelope()],
            conflict_domains_by_task={
                "task-1": ("repo:a.py", "repo:b.py", "repo:c.py")
            },
        )


def test_handoff_fanout_is_bounded_before_any_lease_is_created() -> None:
    orchestrator = _orchestrator(max_fanout=2)
    envelopes = [
        _envelope("task-1", assignee="worker-1"),
        _envelope("task-2", assignee="worker-2"),
        _envelope("task-3", assignee="worker-3"),
    ]

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="fanout exceeds",
    ):
        orchestrator.bind_handoffs(
            envelopes,
            conflict_domains_by_task={
                "task-1": ("repo:a.py",),
                "task-2": ("repo:a.py",),
                "task-3": ("repo:a.py",),
            },
        )

    assert orchestrator.conflicts.snapshot(now=NOW) == ()


def test_handoff_must_reference_registered_conflict_domain() -> None:
    orchestrator = _orchestrator()

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="unknown conflict domain",
    ):
        orchestrator.bind_handoffs(
            [_envelope()],
            conflict_domains_by_task={"task-1": ("repo:missing.py",)},
        )


def test_mutation_lease_is_bound_to_handoff_assignee_and_domain() -> None:
    orchestrator = _orchestrator()
    handoff = orchestrator.bind_handoffs(
        [_envelope()],
        conflict_domains_by_task={"task-1": ("repo:a.py",)},
    )[0]

    lease = orchestrator.acquire_mutation(
        handoff,
        "repo:a.py",
        ttl_s=30.0,
        now=NOW,
    )

    assert lease.task_id == handoff.task_id
    assert lease.worker_id == handoff.assignee_id
    assert orchestrator.require_mutation_authority(
        lease,
        now=NOW + 1.0,
    ) == lease

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="does not authorize",
    ):
        orchestrator.acquire_mutation(
            handoff,
            "repo:b.py",
            ttl_s=30.0,
            now=NOW,
        )


def test_unverified_agent_volume_cannot_outvote_one_verified_candidate() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=4,
        min_independent_verifiers=1,
    )
    verified = _candidate(
        "candidate-a",
        "safe-output",
        verifiers=("verifier:policy",),
    )
    noisy = _candidate(
        "candidate-b",
        "popular-output",
        rejected_verifiers=(
            "agent:1",
            "agent:2",
            "agent:3",
            "agent:4",
            "agent:5",
        ),
    )

    decision = arbitrator.resolve([noisy, verified])

    assert decision.status is ArbitrationStatus.RESOLVED
    assert decision.selected_candidate_id == "candidate-a"
    assert decision.reason == "independent-verifier-evidence-dominates"


def test_independent_verifier_strength_must_be_strictly_greater() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=4,
        min_independent_verifiers=1,
    )
    stronger = _candidate(
        "candidate-a",
        "output-a",
        verifiers=("verifier:policy", "verifier:test"),
    )
    weaker = _candidate(
        "candidate-b",
        "output-b",
        verifiers=("verifier:policy-b",),
    )

    decision = arbitrator.resolve([weaker, stronger])

    assert decision.status is ArbitrationStatus.RESOLVED
    assert decision.selected_candidate_id == "candidate-a"
    assert dict(decision.verified_counts) == {
        "candidate-a": 2,
        "candidate-b": 1,
    }


def test_equal_verified_evidence_fails_closed_instead_of_tie_breaking_text() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=4,
        min_independent_verifiers=1,
    )
    left = _candidate(
        "candidate-a",
        "output-a",
        verifiers=("verifier:left",),
    )
    right = _candidate(
        "candidate-b",
        "output-b",
        verifiers=("verifier:right",),
    )

    decision = arbitrator.resolve([left, right])

    assert decision.status is ArbitrationStatus.UNRESOLVED
    assert decision.selected_candidate_id is None
    assert decision.reason == "verified-evidence-tie"


def test_one_verifier_cannot_validate_competing_outputs_in_same_arbitration() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=4,
        min_independent_verifiers=1,
    )
    left = _candidate(
        "candidate-a",
        "output-a",
        verifiers=("verifier:shared",),
    )
    right = _candidate(
        "candidate-b",
        "output-b",
        verifiers=("verifier:shared",),
    )

    decision = arbitrator.resolve([left, right])

    assert decision.status is ArbitrationStatus.UNRESOLVED
    assert decision.selected_candidate_id is None
    assert decision.reason == "verifier-bound-conflicting-outputs"


def test_minimum_independent_verifier_policy_fails_closed() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=4,
        min_independent_verifiers=2,
    )
    left = _candidate(
        "candidate-a",
        "output-a",
        verifiers=("verifier:left",),
    )
    right = _candidate(
        "candidate-b",
        "output-b",
        rejected_verifiers=("verifier:right",),
    )

    decision = arbitrator.resolve([left, right])

    assert decision.status is ArbitrationStatus.UNRESOLVED
    assert decision.reason == "insufficient-independent-verification"


def test_claim_must_bind_exact_candidate_output_digest() -> None:
    output = _digest("output-a")
    claim = _claim("verifier:1", _digest("other-output"))

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="claim subject does not match",
    ):
        ArbitrationCandidate(
            candidate_id="candidate-a",
            output_digest=output,
            claims=(claim,),
        )


def test_duplicate_verifier_claims_on_one_candidate_are_rejected() -> None:
    output = _digest("output-a")
    claim = _claim("verifier:1", output)

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="duplicate verifier",
    ):
        ArbitrationCandidate(
            candidate_id="candidate-a",
            output_digest=output,
            claims=(claim, claim),
        )


def test_arbitration_is_order_deterministic_and_conflict_record_is_bound() -> None:
    orchestrator = _orchestrator()
    left = _candidate(
        "candidate-a",
        "output-a",
        verifiers=("verifier:policy", "verifier:test"),
    )
    right = _candidate(
        "candidate-b",
        "output-b",
        verifiers=("verifier:other",),
    )

    first = orchestrator.arbitrator.resolve([left, right])
    second = orchestrator.arbitrator.resolve([right, left])

    assert first.decision_digest == second.decision_digest
    assert first.selected_candidate_id == "candidate-a"

    record = orchestrator.record_conflict(
        domain_id="repo:a.py",
        task_id="task-1",
        candidates=[right, left],
    )
    assert record.selected_candidate_id == "candidate-a"
    assert record.arbitration_digest == first.decision_digest
    assert len(record.digest) == 64


def test_candidate_fanout_limit_is_enforced() -> None:
    arbitrator = EvidenceArbitrator(
        max_candidates=2,
        min_independent_verifiers=1,
    )
    candidates = [
        _candidate(
            f"candidate-{index}",
            f"output-{index}",
            verifiers=(f"verifier:{index}",),
        )
        for index in range(3)
    ]

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="candidate fanout exceeds",
    ):
        arbitrator.resolve(candidates)


def test_source_and_ai_mirror_remain_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/automation/swarm/multi_agent_orchestration.py"
    mirror = root / "skeleton/ai/agents/swarm/multi_agent_orchestration.py"

    assert source.read_bytes() == mirror.read_bytes()


def test_expired_work_lease_cannot_authorize_mutation() -> None:
    orchestrator = _orchestrator()
    handoff = orchestrator.bind_handoffs(
        [_envelope()],
        conflict_domains_by_task={"task-1": ("repo:a.py",)},
    )[0]
    lease = orchestrator.acquire_mutation(
        handoff,
        "repo:a.py",
        ttl_s=5.0,
        now=NOW,
    )

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="absent or expired",
    ):
        orchestrator.require_mutation_authority(
            lease,
            now=NOW + 5.0,
        )


def test_non_working_handoff_fails_before_domain_authority() -> None:
    orchestrator = _orchestrator()
    envelope = replace(_envelope(), state=TaskState.SUBMITTED)

    with pytest.raises(
        MultiAgentOrchestrationError,
        match="working state",
    ):
        orchestrator.bind_handoffs(
            [envelope],
            conflict_domains_by_task={"task-1": ("repo:a.py",)},
        )

    assert orchestrator.conflicts.snapshot(now=NOW) == ()
