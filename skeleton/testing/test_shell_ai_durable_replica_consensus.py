"""Cross-replica durable evidence consensus and certificate tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.durable_replica_consensus import (
    REPLICA_CONSENSUS_ARTIFACT_TYPE,
    DurableReplicaConsensusAuthority,
    DurableReplicaConsensusCandidate,
    DurableReplicaConsensusCertificate,
    DurableReplicaConsensusError,
    DurableReplicaConsensusEvaluator,
    DurableReplicaConsensusFinding,
    DurableReplicaConsensusHead,
    DurableReplicaConsensusPolicy,
    DurableReplicaConsensusReport,
    DurableReplicaConsensusVote,
    DurableReplicaConsensusVoteState,
    SignedDurableReplicaConsensusCertificate,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleetMemberReport,
    DurableReplicaFleetReport,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicationReport,
    DurableEvidenceReplicationReport,
    DurableReplicaState,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)


def fp(char: str) -> str:
    return char * 64


def chain(
    chain_id: str,
    *,
    source_sequence: int = 5,
    source_root: str = fp("a"),
    target_sequence: int | None = None,
    target_root: str | None = None,
    source_valid: bool = True,
    target_valid: bool = True,
    state: DurableReplicaState | None = None,
) -> DurableChainReplicationReport:
    if target_sequence is None:
        target_sequence = source_sequence
    if target_root is None:
        target_root = source_root
    if state is None:
        state = (
            DurableReplicaState.IN_SYNC
            if (
                target_sequence == source_sequence
                and target_root == source_root
            )
            else DurableReplicaState.DIVERGED
        )
    return DurableChainReplicationReport(
        chain_id,
        state,
        source_sequence,
        source_root,
        target_sequence,
        target_root,
        abs(source_sequence - target_sequence),
        source_valid,
        target_valid,
        None,
        "",
        "",
        fp("p"),
    )


def replication(
    *,
    journal_sequence: int = 5,
    journal_root: str = fp("a"),
    receipt_sequence: int = 7,
    receipt_root: str = fp("b"),
    target_journal_sequence: int | None = None,
    target_journal_root: str | None = None,
    target_receipt_sequence: int | None = None,
    target_receipt_root: str | None = None,
    source_valid: bool = True,
    target_valid: bool = True,
) -> DurableEvidenceReplicationReport:
    return DurableEvidenceReplicationReport(
        chain(
            "journal",
            source_sequence=journal_sequence,
            source_root=journal_root,
            target_sequence=target_journal_sequence,
            target_root=target_journal_root,
            source_valid=source_valid,
            target_valid=target_valid,
        ),
        chain(
            "receipts",
            source_sequence=receipt_sequence,
            source_root=receipt_root,
            target_sequence=target_receipt_sequence,
            target_root=target_receipt_root,
            source_valid=source_valid,
            target_valid=target_valid,
        ),
        fp("p"),
    )


def member(
    target_id: str,
    domain: str,
    *,
    required: bool = False,
    ready: bool = True,
    report: DurableEvidenceReplicationReport | None = None,
) -> DurableReplicaFleetMemberReport:
    report = report or replication()
    return DurableReplicaFleetMemberReport(
        target_id,
        domain,
        required,
        report,
        ready,
        "" if ready else "not ready",
    )


def fleet(
    *members: DurableReplicaFleetMemberReport,
    quorum_ready: bool = True,
) -> DurableReplicaFleetReport:
    findings = (
        ()
        if quorum_ready
        else ()
    )
    # Fleet report derives quorum_ready from counts/required readiness rather
    # than accepting it as a direct field. Choose thresholds accordingly.
    return DurableReplicaFleetReport(
        "primary",
        100.0,
        tuple(
            sorted(
                members,
                key=lambda item: item.target_id,
            )
        ),
        findings,
        fp("f"),
        1 if quorum_ready else len(members) + 1,
        1,
    )


def consensus_policy(**changes):
    values = dict(
        min_agreeing_replicas=2,
        min_agreeing_failure_domains=2,
        min_agreement_fraction=2.0 / 3.0,
        require_fleet_quorum=True,
        require_all_required_members=True,
        require_target_caught_up=True,
        require_member_source_integrity=True,
        require_member_target_integrity=True,
    )
    values.update(changes)
    return DurableReplicaConsensusPolicy(**values)


def evaluator(**policy_changes):
    return DurableReplicaConsensusEvaluator(
        consensus_policy(**policy_changes)
    )


def canonical_fleet():
    return fleet(
        member("replica-a", "zone-a"),
        member("replica-b", "zone-b"),
        member("replica-c", "zone-c"),
    )


def signer(
    *,
    key=b"k" * 32,
    now=100.0,
):
    return ArtifactSigner(
        "consensus-key",
        key,
        clock=lambda: now,
    )


def authority(
    *,
    now=None,
    policy=None,
    nonce="nonce",
):
    clock_value = [100.0] if now is None else now
    return DurableReplicaConsensusAuthority(
        signer(
            now=clock_value[0],
        ),
        policy or evaluator(),
        max_ttl_seconds=300.0,
        max_clock_skew_seconds=5.0,
        clock=lambda: clock_value[0],
        nonce_factory=lambda: nonce,
    )


def test_three_matching_replicas_form_consensus():
    report = evaluator().evaluate(
        canonical_fleet()
    )
    assert report.certifiable
    assert not report.split_brain
    assert report.selected is not None
    assert report.selected.ready_voters == 3
    assert report.selected.agreement_fraction == 1.0
    assert report.agreeing_targets == (
        "replica-a",
        "replica-b",
        "replica-c",
    )
    assert report.agreeing_failure_domains == (
        "zone-a",
        "zone-b",
        "zone-c",
    )
    assert report.dissenting_targets == ()
    assert report.findings == ()


def test_consensus_head_binds_both_chains():
    report = evaluator().require_consensus(
        canonical_fleet()
    )
    head = report.selected.head
    assert head.journal_sequence == 5
    assert head.journal_root == fp("a")
    assert head.receipt_sequence == 7
    assert head.receipt_root == fp("b")
    assert len(head.digest) == 64


def test_consensus_requires_independent_failure_domains():
    same_domain = fleet(
        member("replica-a", "zone-a"),
        member("replica-b", "zone-a"),
        member("replica-c", "zone-a"),
    )
    report = evaluator().evaluate(
        same_domain
    )
    assert not report.certifiable
    assert any(
        item.code == "consensus.no_unique_quorum"
        for item in report.findings
    )


def test_consensus_requires_minimum_replica_count():
    report = evaluator().evaluate(
        fleet(
            member("replica-a", "zone-a"),
        )
    )
    assert not report.certifiable
    assert any(
        item.code
        == "consensus.ready_voters_insufficient"
        for item in report.findings
    )


def test_two_of_three_same_head_with_one_dissent_is_detected_as_split_brain():
    report = evaluator().evaluate(
        fleet(
            member("replica-a", "zone-a"),
            member("replica-b", "zone-b"),
            member(
                "replica-c",
                "zone-c",
                report=replication(
                    journal_root=fp("c"),
                    receipt_root=fp("d"),
                ),
            ),
        )
    )
    assert report.split_brain
    assert not report.certifiable
    assert any(
        item.code
        == "consensus.split_brain_detected"
        for item in report.findings
    )


def test_split_brain_candidates_are_separate():
    report = evaluator().evaluate(
        fleet(
            member("replica-a", "zone-a"),
            member("replica-b", "zone-b"),
            member(
                "replica-c",
                "zone-c",
                report=replication(
                    journal_root=fp("c"),
                    receipt_root=fp("d"),
                ),
            ),
        )
    )
    assert len(report.candidates) == 2
    assert len(
        {
            item.head.digest
            for item in report.candidates
        }
    ) == 2


def test_ambiguous_two_two_partition_fails_closed():
    policy = consensus_policy(
        min_agreeing_replicas=2,
        min_agreeing_failure_domains=2,
        min_agreement_fraction=0.5 + 1e-9,
    )
    # At >0.5 neither 2/4 group qualifies, so no unique quorum exists.
    report = DurableReplicaConsensusEvaluator(
        policy
    ).evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=replication(
                    journal_root=fp("c"),
                    receipt_root=fp("d"),
                ),
            ),
            member(
                "d",
                "z4",
                report=replication(
                    journal_root=fp("c"),
                    receipt_root=fp("d"),
                ),
            ),
        )
    )
    assert not report.certifiable
    assert report.selected is None


def test_unready_replica_does_not_vote():
    report = evaluator().evaluate(
        fleet(
            member("replica-a", "zone-a"),
            member("replica-b", "zone-b"),
            member(
                "replica-c",
                "zone-c",
                ready=False,
            ),
        )
    )
    assert report.selected is not None
    assert report.selected.ready_voters == 2
    assert report.votes[2].state is (
        DurableReplicaConsensusVoteState.UNREADY
    )


def test_required_unready_replica_blocks_when_fleet_quorum_blocks():
    report = evaluator().evaluate(
        DurableReplicaFleetReport(
            "primary",
            100.0,
            (
                member("a", "z1"),
                member("b", "z2"),
                member(
                    "c",
                    "z3",
                    required=True,
                    ready=False,
                ),
            ),
            (),
            fp("f"),
            2,
            2,
        )
    )
    assert not report.certifiable
    assert any(
        item.code
        == "consensus.fleet_quorum_unready"
        for item in report.findings
    )


def test_required_ready_dissenting_replica_blocks_selected_consensus():
    divergent = replication(
        journal_root=fp("c"),
        receipt_root=fp("d"),
    )
    report = evaluator().evaluate(
        DurableReplicaFleetReport(
            "primary",
            100.0,
            (
                member("a", "z1"),
                member("b", "z2"),
                member(
                    "c",
                    "z3",
                    required=True,
                    report=divergent,
                ),
            ),
            (),
            fp("f"),
            2,
            2,
        )
    )
    assert not report.certifiable
    assert report.split_brain


def test_member_with_invalid_source_integrity_is_invalid_vote():
    bad = replication(
        source_valid=False,
    )
    report = evaluator().evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=bad,
            ),
        )
    )
    vote = next(
        item
        for item in report.votes
        if item.target_id == "c"
    )
    assert vote.state is (
        DurableReplicaConsensusVoteState.INVALID
    )
    assert "source integrity" in vote.reason


def test_member_with_invalid_target_integrity_is_invalid_vote():
    bad = replication(
        target_valid=False,
    )
    report = evaluator().evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=bad,
            ),
        )
    )
    vote = next(
        item
        for item in report.votes
        if item.target_id == "c"
    )
    assert vote.state is (
        DurableReplicaConsensusVoteState.INVALID
    )
    assert "target integrity" in vote.reason


def test_target_must_exactly_match_source_heads():
    lag = replication(
        target_journal_sequence=4,
        target_journal_root=fp("9"),
        target_receipt_sequence=6,
        target_receipt_root=fp("8"),
    )
    report = evaluator().evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=lag,
                ready=True,
            ),
        )
    )
    vote = next(
        item
        for item in report.votes
        if item.target_id == "c"
    )
    assert vote.state is (
        DurableReplicaConsensusVoteState.INVALID
    )
    assert not vote.caught_up


def test_target_caught_up_requirement_can_be_disabled_explicitly():
    lag = replication(
        target_journal_sequence=4,
        target_journal_root=fp("9"),
        target_receipt_sequence=6,
        target_receipt_root=fp("8"),
    )
    report = evaluator(
        require_target_caught_up=False,
    ).evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=lag,
                ready=True,
            ),
        )
    )
    # Vote may participate, but require_target still protects actual promotion
    # from selecting a non-caught-up target.
    assert report.selected is not None
    vote = next(
        item
        for item in report.votes
        if item.target_id == "c"
    )
    assert not vote.caught_up


def test_require_target_accepts_agreeing_caught_up_member():
    report = evaluator().require_consensus(
        canonical_fleet(),
        target_id="replica-a",
    )
    vote = report.require_target(
        "replica-a"
    )
    assert vote.caught_up
    assert vote.state is (
        DurableReplicaConsensusVoteState.AGREEING
    )


def test_require_target_rejects_unknown_member():
    report = evaluator().require_consensus(
        canonical_fleet()
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="not a consensus fleet member",
    ):
        report.require_target("missing")


def test_require_consensus_rejects_split_brain():
    split = fleet(
        member("a", "z1"),
        member("b", "z2"),
        member(
            "c",
            "z3",
            report=replication(
                journal_root=fp("c"),
                receipt_root=fp("d"),
            ),
        ),
    )
    with pytest.raises(
        DurableReplicaConsensusError,
    ):
        evaluator().require_consensus(
            split
        )


def test_report_state_digest_ignores_observation_time_only_if_fleet_state_does():
    first = evaluator().evaluate(
        canonical_fleet()
    )
    second_fleet = replace(
        canonical_fleet(),
        observed_at=101.0,
    )
    second = evaluator().evaluate(
        second_fleet
    )
    assert first.state_digest == second.state_digest
    assert first.digest != second.digest


def test_report_digest_is_deterministic():
    source = canonical_fleet()
    first = evaluator().evaluate(
        source
    )
    second = evaluator().evaluate(
        source
    )
    assert first == second
    assert first.digest == second.digest


def test_report_serialization_exposes_split_brain_and_targets():
    report = evaluator().evaluate(
        canonical_fleet()
    )
    data = report.to_dict()
    assert data["certifiable"] is True
    assert data["split_brain"] is False
    assert data["agreeing_targets"] == [
        "replica-a",
        "replica-b",
        "replica-c",
    ]
    assert len(data["state_digest"]) == 64
    assert len(data["digest"]) == 64


def test_policy_digest_is_stable():
    first = consensus_policy()
    second = consensus_policy()
    assert first.digest == second.digest


@pytest.mark.parametrize(
    "changes",
    [
        {"min_agreeing_replicas": 0},
        {"min_agreeing_replicas": 1025},
        {"min_agreeing_failure_domains": 0},
        {"max_members": 0},
        {"max_findings": 0},
        {"min_agreement_fraction": 0.5},
        {"min_agreement_fraction": 1.1},
        {"min_agreement_fraction": float("nan")},
        {"require_fleet_quorum": "yes"},
        {"require_target_caught_up": 1},
    ],
)
def test_policy_validation(changes):
    with pytest.raises(ValueError):
        DurableReplicaConsensusPolicy(
            **changes
        )


def test_evaluator_requires_policy_type():
    with pytest.raises(TypeError):
        DurableReplicaConsensusEvaluator(
            object()
        )


def test_evaluate_requires_fleet_report():
    with pytest.raises(TypeError):
        evaluator().evaluate(object())


def test_member_bound_is_enforced():
    policy = consensus_policy(
        max_members=2,
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="bound",
    ):
        DurableReplicaConsensusEvaluator(
            policy
        ).evaluate(
            canonical_fleet()
        )


def test_head_validation():
    with pytest.raises(ValueError):
        DurableReplicaConsensusHead(
            -1,
            fp("a"),
            1,
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableReplicaConsensusHead(
            1,
            "bad",
            1,
            fp("b"),
        )


def test_vote_serialization_and_caught_up():
    report = evaluator().evaluate(
        canonical_fleet()
    )
    vote = report.votes[0]
    data = vote.to_dict()
    assert data["caught_up"] is True
    assert data["state"] == "agreeing"
    assert data["target_id"] == "replica-a"
    assert len(data["digest"]) == 64


def test_candidate_fraction():
    item = DurableReplicaConsensusCandidate(
        DurableReplicaConsensusHead(
            1,
            fp("a"),
            1,
            fp("b"),
        ),
        ("a", "b"),
        ("z1", "z2"),
        (),
        2,
        3,
    )
    assert item.agreement_fraction == pytest.approx(
        2 / 3
    )


def test_candidate_requires_sorted_unique_targets():
    with pytest.raises(ValueError, match="sorted"):
        DurableReplicaConsensusCandidate(
            DurableReplicaConsensusHead(
                1,
                fp("a"),
                1,
                fp("b"),
            ),
            ("b", "a"),
            ("z1",),
            (),
            2,
            2,
        )


def test_finding_validation():
    with pytest.raises(ValueError):
        DurableReplicaConsensusFinding(
            "",
            "message",
        )
    with pytest.raises(ValueError):
        DurableReplicaConsensusFinding(
            "code",
            "",
        )


def test_certificate_issue_binds_selected_head():
    auth = authority()
    signed = auth.issue(
        canonical_fleet(),
        target_id="replica-a",
    )
    certificate = signed.certificate
    assert certificate.source_id == "primary"
    assert certificate.journal_sequence == 5
    assert certificate.journal_root == fp("a")
    assert certificate.receipt_sequence == 7
    assert certificate.receipt_root == fp("b")
    assert "replica-a" in certificate.agreeing_targets
    assert len(certificate.certificate_id) == 64


def test_certificate_signature_artifact_type():
    signed = authority().issue(
        canonical_fleet()
    )
    assert (
        signed.signature.artifact_type
        == REPLICA_CONSENSUS_ARTIFACT_TYPE
    )
    assert (
        signed.signature.artifact_digest
        == signed.certificate.digest
    )


def test_static_certificate_verification():
    auth = authority()
    signed = auth.issue(
        canonical_fleet(),
        target_id="replica-b",
    )
    certificate = auth.verify_static(
        signed,
        source_id="primary",
        target_id="replica-b",
    )
    assert certificate == signed.certificate


def test_static_verification_enforces_target_membership():
    auth = authority()
    signed = auth.issue(
        canonical_fleet()
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="not covered",
    ):
        auth.verify_static(
            signed,
            target_id="missing",
        )


def test_live_report_verification():
    auth = authority()
    source = canonical_fleet()
    signed = auth.issue(
        source,
        target_id="replica-a",
    )
    report = auth.verify_report(
        signed,
        source,
        target_id="replica-a",
    )
    assert report.certifiable


def test_live_consensus_drift_invalidates_certificate():
    auth = authority()
    source = canonical_fleet()
    signed = auth.issue(source)
    changed = fleet(
        member("replica-a", "zone-a"),
        member("replica-b", "zone-b"),
        member(
            "replica-c",
            "zone-c",
            report=replication(
                journal_sequence=6,
                journal_root=fp("c"),
                receipt_sequence=8,
                receipt_root=fp("d"),
            ),
        ),
    )
    with pytest.raises(
        DurableReplicaConsensusError,
    ):
        auth.verify_report(
            signed,
            changed,
        )


def test_expired_certificate_is_rejected():
    now = [100.0]
    auth = authority(now=now)
    signed = auth.issue(
        canonical_fleet(),
        ttl_seconds=10.0,
    )
    now[0] = 111.0
    with pytest.raises(
        DurableReplicaConsensusError,
        match="expired",
    ):
        auth.verify_static(signed)


def test_historical_certificate_can_be_authenticated_without_time():
    now = [100.0]
    auth = authority(now=now)
    signed = auth.issue(
        canonical_fleet(),
        ttl_seconds=10.0,
    )
    now[0] = 1000.0
    assert auth.verify_static(
        signed,
        enforce_time=False,
    ) == signed.certificate


def test_future_certificate_is_rejected():
    issue_now = [110.0]
    issuer = authority(now=issue_now)
    signed = issuer.issue(
        canonical_fleet()
    )
    verify_now = [100.0]
    verifier = authority(
        now=verify_now
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="future",
    ):
        verifier.verify_static(signed)


def test_wrong_signing_key_rejects_certificate():
    signed = authority().issue(
        canonical_fleet()
    )
    other = DurableReplicaConsensusAuthority(
        signer(key=b"x" * 32),
        evaluator(),
        clock=lambda: 100.0,
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="signature",
    ):
        other.verify_static(signed)


def test_signed_metadata_tamper_is_rejected():
    auth = authority()
    signed = auth.issue(
        canonical_fleet()
    )
    metadata = dict(
        signed.signature.metadata
    )
    metadata["source_id"] = "other"
    forged_signature = SignedArtifact(
        signed.signature.artifact_type,
        signed.signature.artifact_digest,
        signed.signature.signer_id,
        signed.signature.issued_at,
        signed.signature.signature,
        metadata,
    )
    forged = SignedDurableReplicaConsensusCertificate(
        signed.certificate,
        forged_signature,
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="metadata",
    ):
        auth.verify_static(forged)


def test_certificate_ttl_validation():
    auth = authority()
    for ttl in (0, -1, 301, True):
        with pytest.raises(ValueError):
            auth.issue(
                canonical_fleet(),
                ttl_seconds=ttl,
            )


def test_authority_configuration_validation():
    with pytest.raises(TypeError, match="signer"):
        DurableReplicaConsensusAuthority(
            object(),
            evaluator(),
        )
    with pytest.raises(TypeError, match="evaluator"):
        DurableReplicaConsensusAuthority(
            signer(),
            object(),
        )
    with pytest.raises(ValueError):
        DurableReplicaConsensusAuthority(
            signer(),
            evaluator(),
            max_ttl_seconds=0,
        )
    with pytest.raises(TypeError, match="clock"):
        DurableReplicaConsensusAuthority(
            signer(),
            evaluator(),
            clock=object(),
        )


def test_nonce_factory_output_is_validated():
    auth = DurableReplicaConsensusAuthority(
        signer(),
        evaluator(),
        clock=lambda: 100.0,
        nonce_factory=lambda: "",
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="nonce",
    ):
        auth.issue(canonical_fleet())


def test_certificate_id_changes_with_nonce():
    first = authority(
        nonce="one"
    ).issue(canonical_fleet())
    second = authority(
        nonce="two"
    ).issue(canonical_fleet())
    assert (
        first.certificate.certificate_id
        != second.certificate.certificate_id
    )


def test_certificate_serialization():
    signed = authority().issue(
        canonical_fleet()
    )
    data = signed.to_dict()
    assert (
        data["certificate"]["source_id"]
        == "primary"
    )
    assert len(
        data["certificate_digest"]
    ) == 64
    assert data["signature"]


def test_certificate_rejects_unsorted_targets():
    with pytest.raises(ValueError, match="sorted"):
        DurableReplicaConsensusCertificate(
            1,
            fp("c"),
            "primary",
            1.0,
            2.0,
            "nonce",
            fp("s"),
            fp("p"),
            fp("f"),
            fp("q"),
            1,
            fp("a"),
            1,
            fp("b"),
            ("b", "a"),
            ("z1",),
        )


def test_signed_certificate_rejects_wrong_artifact_type():
    auth = authority()
    signed = auth.issue(
        canonical_fleet()
    )
    bad = SignedArtifact(
        "wrong",
        signed.certificate.digest,
        signed.signature.signer_id,
        signed.signature.issued_at,
        signed.signature.signature,
        signed.signature.metadata,
    )
    with pytest.raises(ValueError, match="artifact type"):
        SignedDurableReplicaConsensusCertificate(
            signed.certificate,
            bad,
        )


def test_selected_target_must_be_caught_up_even_if_policy_allows_lag_vote():
    lag = replication(
        target_journal_sequence=4,
        target_journal_root=fp("9"),
        target_receipt_sequence=6,
        target_receipt_root=fp("8"),
    )
    report = evaluator(
        require_target_caught_up=False,
    ).evaluate(
        fleet(
            member(
                "a",
                "z1",
                report=lag,
            ),
            member("b", "z2"),
            member("c", "z3"),
        )
    )
    assert report.certifiable
    with pytest.raises(
        DurableReplicaConsensusError,
        match="not caught up",
    ):
        report.require_target("a")


def test_consensus_policy_drift_changes_state_digest():
    source = canonical_fleet()
    strict = evaluator().evaluate(
        source
    )
    alternate = evaluator(
        min_agreement_fraction=0.8,
    ).evaluate(source)
    assert (
        strict.consensus_policy_digest
        != alternate.consensus_policy_digest
    )
    assert strict.state_digest != alternate.state_digest


def test_fleet_policy_drift_changes_state_digest():
    source = canonical_fleet()
    first = evaluator().evaluate(
        source
    )
    changed = replace(
        source,
        policy_digest=fp("9"),
    )
    second = evaluator().evaluate(
        changed
    )
    assert first.state_digest != second.state_digest


def test_vote_digest_binds_target_roots():
    report = evaluator().evaluate(
        canonical_fleet()
    )
    vote = report.votes[0]
    changed = replace(
        vote,
        target_journal_root=fp("9"),
    )
    assert vote.digest != changed.digest


def test_candidate_digest_binds_failure_domains():
    report = evaluator().evaluate(
        canonical_fleet()
    )
    candidate = report.selected
    changed = replace(
        candidate,
        failure_domains=(
            "zone-a",
            "zone-b",
            "zone-z",
        ),
    )
    assert candidate.digest != changed.digest


def test_report_requires_sorted_votes():
    source = evaluator().evaluate(
        canonical_fleet()
    )
    with pytest.raises(ValueError, match="target-sorted"):
        replace(
            source,
            votes=tuple(
                reversed(source.votes)
            ),
        )


def test_report_requires_selected_candidate_present():
    source = evaluator().evaluate(
        canonical_fleet()
    )
    foreign = replace(
        source.selected,
        head=DurableReplicaConsensusHead(
            99,
            fp("9"),
            99,
            fp("8"),
        ),
    )
    with pytest.raises(ValueError, match="not present"):
        replace(
            source,
            selected=foreign,
        )


def test_require_consensus_target_must_be_selected_member():
    source = canonical_fleet()
    report = evaluator().require_consensus(
        source,
        target_id="replica-c",
    )
    assert report.require_target(
        "replica-c"
    ).target_id == "replica-c"


def test_certificate_report_state_mismatch_is_rejected_even_same_heads():
    auth = authority()
    source = canonical_fleet()
    signed = auth.issue(source)
    changed = replace(
        source,
        policy_digest=fp("9"),
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="state",
    ):
        auth.verify_report(
            signed,
            changed,
        )


def test_static_verify_rejects_wrong_source_identity():
    auth = authority()
    signed = auth.issue(
        canonical_fleet()
    )
    with pytest.raises(
        DurableReplicaConsensusError,
        match="source_id",
    ):
        auth.verify_static(
            signed,
            source_id="other",
        )


def test_certificate_head_property_round_trips():
    signed = authority().issue(
        canonical_fleet()
    )
    cert = signed.certificate
    assert cert.head == DurableReplicaConsensusHead(
        cert.journal_sequence,
        cert.journal_root,
        cert.receipt_sequence,
        cert.receipt_root,
    )


def test_consensus_report_ready_votes_excludes_unready():
    report = evaluator().evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                ready=False,
            ),
        )
    )
    assert tuple(
        vote.target_id
        for vote in report.ready_votes
    ) == ("a", "b")


def test_dissenting_targets_are_sorted_by_vote_order():
    split = evaluator().evaluate(
        fleet(
            member("a", "z1"),
            member("b", "z2"),
            member(
                "c",
                "z3",
                report=replication(
                    journal_root=fp("c"),
                    receipt_root=fp("d"),
                ),
            ),
        )
    )
    # Strict split-brain policy prevents selection, so every ready target is
    # effectively outside a selected quorum.
    assert split.selected is None
    assert split.dissenting_targets == (
        "a",
        "b",
        "c",
    )
