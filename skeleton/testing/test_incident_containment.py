from __future__ import annotations

import pytest

from skeleton.security.defense_plane import ContainmentMode, DefensePlane
from skeleton.security.incident_containment import (
    IncidentCoordinator,
    IncidentIntegrityError,
    IncidentPhase,
    IncidentPolicy,
    IncidentSeverity,
    IncidentSignal,
    IncidentStateError,
    RecoveryAuthority,
    RecoveryClaims,
    RecoveryKey,
    digest_evidence,
)


RECOVERY_KEY = RecoveryKey("recovery-primary", b"r" * 32)


class Clock:
    def __init__(self, now: float = 2_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def signal(
    clock: Clock,
    *,
    severity: IncidentSeverity = IncidentSeverity.MEDIUM,
    subject: str = "github:automation",
    kind: str = "policy_tamper",
    marker: str = "evidence-1",
    summary: str = "bounded security observation",
    observed_at: float | None = None,
) -> IncidentSignal:
    return IncidentSignal(
        source="security-gate",
        kind=kind,
        severity=severity,
        subject=subject,
        observed_at=clock() if observed_at is None else observed_at,
        evidence_digest=digest_evidence(marker),
        summary=summary,
    )


def authority() -> RecoveryAuthority:
    return RecoveryAuthority(
        keys=(RECOVERY_KEY,),
        active_key_id="recovery-primary",
        max_ttl_seconds=600.0,
    )


def coordinator(
    clock: Clock,
    *,
    policy: IncidentPolicy | None = None,
    max_incidents: int = 4096,
) -> IncidentCoordinator:
    return IncidentCoordinator(
        defense=DefensePlane(clock=clock),
        recovery_authority=authority(),
        policy=policy or IncidentPolicy(),
        clock=clock,
        max_incidents=max_incidents,
    )


def recovery_claims(
    clock: Clock,
    record,
    *,
    token_id: str = "recovery-token-0001",
    to_mode: ContainmentMode = ContainmentMode.NORMAL,
    ttl: float = 300.0,
) -> RecoveryClaims:
    return RecoveryClaims(
        token_id=token_id,
        key_id="recovery-primary",
        incident_id=record.incident_id,
        subject=record.subject,
        operator="security-operator",
        from_mode=record.required_mode,
        to_mode=to_mode,
        issued_at=clock(),
        expires_at=clock() + ttl,
    )


def test_evidence_digest_is_fixed_size_and_does_not_retain_raw_input() -> None:
    raw = "sensitive runtime diagnostic fixture"
    digest = digest_evidence(raw)

    assert len(digest) == 64
    assert raw not in digest
    assert digest == digest_evidence(raw)


def test_evidence_digest_rejects_unbounded_input() -> None:
    with pytest.raises(IncidentIntegrityError, match="exceeds maximum"):
        digest_evidence(b"x" * (1_048_576 + 1))


@pytest.mark.parametrize(
    ("severity", "expected_mode"),
    [
        (IncidentSeverity.INFO, ContainmentMode.NORMAL),
        (IncidentSeverity.LOW, ContainmentMode.NORMAL),
        (IncidentSeverity.MEDIUM, ContainmentMode.RESTRICTED),
        (IncidentSeverity.HIGH, ContainmentMode.QUARANTINE),
        (IncidentSeverity.CRITICAL, ContainmentMode.LOCKDOWN),
    ],
)
def test_severity_maps_to_monotonic_initial_containment(
    severity: IncidentSeverity,
    expected_mode: ContainmentMode,
) -> None:
    clock = Clock()
    control = coordinator(clock)

    record = control.observe(signal(clock, severity=severity))

    assert record.required_mode is expected_mode
    assert control.defense.mode is expected_mode
    assert record.phase is IncidentPhase.DETECTED


def test_duplicate_signal_is_idempotent() -> None:
    clock = Clock()
    control = coordinator(clock)
    observation = signal(clock, severity=IncidentSeverity.HIGH)

    first = control.observe(observation)
    second = control.observe(observation)

    assert first.incident_id == second.incident_id
    assert second.signal_count == 1
    assert second.score == first.score
    assert len(control.defense.ledger.entries()) == 1


def test_distinct_signals_accumulate_score_and_escalate() -> None:
    clock = Clock()
    control = coordinator(clock)

    first = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.LOW,
            marker="first",
            kind="rate_abuse",
        )
    )
    assert first.required_mode is ContainmentMode.NORMAL

    clock.advance(1)
    second = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.LOW,
            marker="second",
            kind="rate_abuse",
        )
    )
    assert second.score == 6
    assert second.required_mode is ContainmentMode.NORMAL
    assert second.phase is IncidentPhase.TRIAGE

    clock.advance(1)
    third = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.INFO,
            marker="third",
            kind="rate_abuse",
        )
    )
    assert third.score == 7
    assert third.required_mode is ContainmentMode.RESTRICTED
    assert control.defense.mode is ContainmentMode.RESTRICTED


def test_containment_never_auto_deescalates_on_lower_severity_signal() -> None:
    clock = Clock()
    control = coordinator(clock)

    critical = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.CRITICAL,
            marker="critical",
            kind="malware",
        )
    )
    assert critical.required_mode is ContainmentMode.LOCKDOWN

    clock.advance(1)
    later = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.INFO,
            marker="low-later",
            kind="other",
        )
    )

    assert later.required_mode is ContainmentMode.LOCKDOWN
    assert control.defense.mode is ContainmentMode.LOCKDOWN


def test_quarantine_or_lockdown_locally_quarantines_subject() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:suspicious",
            kind="sandbox_escape",
        )
    )

    entry = control.defense.quarantines.active(
        record.subject,
        now=clock(),
    )
    assert entry is not None
    assert "incident containment" in entry.reason


def test_stale_signal_fails_closed() -> None:
    clock = Clock()
    control = coordinator(
        clock,
        policy=IncidentPolicy(max_signal_age_seconds=60.0),
    )

    with pytest.raises(IncidentIntegrityError, match="stale"):
        control.observe(
            signal(
                clock,
                observed_at=clock() - 61.0,
            )
        )


def test_future_signal_fails_closed() -> None:
    clock = Clock()
    control = coordinator(
        clock,
        policy=IncidentPolicy(max_future_skew_seconds=10.0),
    )

    with pytest.raises(IncidentIntegrityError, match="future"):
        control.observe(
            signal(
                clock,
                observed_at=clock() + 11.0,
            )
        )


def test_mark_contained_requires_actual_containment_threshold() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.LOW)
    )

    with pytest.raises(IncidentStateError, match="threshold"):
        control.mark_contained(record.incident_id)


def test_mark_contained_records_phase_without_lowering_mode() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )

    contained = control.mark_contained(record.incident_id)

    assert contained.phase is IncidentPhase.CONTAINED
    assert contained.required_mode is ContainmentMode.QUARANTINE
    assert control.defense.mode is ContainmentMode.QUARANTINE


def test_recovery_token_round_trip() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    claims = recovery_claims(
        clock,
        record,
        to_mode=ContainmentMode.RESTRICTED,
    )

    token = authority().issue(claims)
    verified = authority().verify(token, now=clock())

    assert verified == claims


def test_recovery_token_tamper_is_rejected() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.RESTRICTED,
        )
    )
    version, payload, signature = token.split(".")
    forged = (
        f"{version}.{payload}."
        f"{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"
    )

    with pytest.raises(IncidentIntegrityError, match="verification failed"):
        authority().verify(forged, now=clock())


def test_expired_recovery_token_is_rejected() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.RESTRICTED,
            ttl=5.0,
        )
    )
    clock.advance(6)

    with pytest.raises(IncidentIntegrityError, match="expired"):
        authority().verify(token, now=clock())


def test_recovery_requires_strictly_lower_target_mode() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )

    with pytest.raises(IncidentIntegrityError, match="strictly reduce"):
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.QUARANTINE,
        )


def test_authenticated_recovery_can_reduce_containment() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.CRITICAL,
            kind="malware",
        )
    )

    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.QUARANTINE,
        )
    )
    updated = control.apply_recovery(token)

    assert updated.phase is IncidentPhase.RECOVERY
    assert updated.required_mode is ContainmentMode.QUARANTINE
    assert updated.recovery_count == 1
    assert control.defense.mode is ContainmentMode.QUARANTINE


def test_recovery_to_normal_enters_monitoring_and_releases_subject() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:recovering",
        )
    )
    assert control.defense.quarantines.active(record.subject, now=clock())

    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.NORMAL,
        )
    )
    updated = control.apply_recovery(token)

    assert updated.phase is IncidentPhase.MONITORING
    assert updated.required_mode is ContainmentMode.NORMAL
    assert control.defense.mode is ContainmentMode.NORMAL
    assert control.defense.quarantines.active(record.subject, now=clock()) is None


def test_recovery_token_is_one_shot() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.NORMAL,
        )
    )

    control.apply_recovery(token)

    with pytest.raises(IncidentStateError, match="already been consumed"):
        control.apply_recovery(token)


def test_stale_recovery_token_cannot_override_new_escalation() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH, marker="first")
    )
    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.NORMAL,
        )
    )

    clock.advance(1)
    escalated = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.CRITICAL,
            marker="second",
            kind="malware",
        )
    )
    assert escalated.required_mode is ContainmentMode.LOCKDOWN

    with pytest.raises(IncidentStateError, match="stale"):
        control.apply_recovery(token)


def test_one_incident_cannot_lower_below_other_active_incident_floor() -> None:
    clock = Clock()
    control = coordinator(clock)

    first = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.CRITICAL,
            subject="github:first",
            marker="first",
            kind="malware",
        )
    )
    clock.advance(1)
    second = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:second",
            marker="second",
            kind="sandbox_escape",
        )
    )
    assert control.defense.mode is ContainmentMode.LOCKDOWN

    token = authority().issue(
        recovery_claims(
            clock,
            first,
            to_mode=ContainmentMode.NORMAL,
        )
    )

    with pytest.raises(IncidentStateError, match="another active incident"):
        control.apply_recovery(token)

    assert control.get(second.incident_id).required_mode is ContainmentMode.QUARANTINE
    assert control.defense.mode is ContainmentMode.LOCKDOWN


def test_incident_cannot_close_without_authenticated_recovery() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )

    with pytest.raises(IncidentStateError, match="authenticated recovery"):
        control.close(record.incident_id)


def test_incident_can_close_after_recovery_to_normal() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    token = authority().issue(
        recovery_claims(
            clock,
            record,
            to_mode=ContainmentMode.NORMAL,
        )
    )
    recovered = control.apply_recovery(token)
    closed = control.close(recovered.incident_id)

    assert closed.phase is IncidentPhase.CLOSED
    assert closed.active is False
    assert control.active_incidents() == ()
    assert control.defense.mode is ContainmentMode.NORMAL


def test_active_incidents_are_never_evicted_under_capacity_pressure() -> None:
    clock = Clock()
    control = coordinator(clock, max_incidents=1)
    control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:first",
            marker="first",
        )
    )
    clock.advance(1)

    with pytest.raises(IncidentStateError, match="refusing to evict"):
        control.observe(
            signal(
                clock,
                severity=IncidentSeverity.HIGH,
                subject="github:second",
                marker="second",
            )
        )


def test_closed_incident_can_be_evicted_for_new_evidence() -> None:
    clock = Clock()
    control = coordinator(clock, max_incidents=1)
    first = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:first",
            marker="first",
        )
    )
    token = authority().issue(
        recovery_claims(
            clock,
            first,
            to_mode=ContainmentMode.NORMAL,
        )
    )
    control.apply_recovery(token)
    control.close(first.incident_id)

    clock.advance(1)
    second = control.observe(
        signal(
            clock,
            severity=IncidentSeverity.HIGH,
            subject="github:second",
            marker="second",
        )
    )

    assert second.subject == "github:second"
    with pytest.raises(IncidentStateError):
        control.get(first.incident_id)


def test_raw_evidence_is_not_present_in_incident_record() -> None:
    clock = Clock()
    control = coordinator(clock)
    raw = "sensitive diagnostic body that must not persist"
    observation = IncidentSignal(
        source="security-gate",
        kind="other",
        severity=IncidentSeverity.MEDIUM,
        subject="github:automation",
        observed_at=clock(),
        evidence_digest=digest_evidence(raw),
        summary="diagnostic matched policy",
    )

    record = control.observe(observation)

    assert raw not in repr(record)
    assert record.evidence_digests == (digest_evidence(raw),)


def test_recovery_key_must_be_strong() -> None:
    with pytest.raises(IncidentIntegrityError, match="at least 32"):
        RecoveryKey("weak", b"short")


def test_recovery_authority_requires_active_key() -> None:
    with pytest.raises(IncidentIntegrityError, match="unavailable"):
        RecoveryAuthority(
            keys=(RECOVERY_KEY,),
            active_key_id="missing",
        )


@pytest.mark.parametrize(
    ("restricted", "quarantine", "lockdown"),
    [
        (10, 5, 20),
        (5, 20, 10),
    ],
)
def test_incident_thresholds_must_be_monotonic(
    restricted: int,
    quarantine: int,
    lockdown: int,
) -> None:
    with pytest.raises(Exception, match="monotonic"):
        IncidentPolicy(
            restricted_score=restricted,
            quarantine_score=quarantine,
            lockdown_score=lockdown,
        )


def test_incident_ledger_remains_verifiable_across_lifecycle() -> None:
    clock = Clock()
    control = coordinator(clock)
    record = control.observe(
        signal(clock, severity=IncidentSeverity.HIGH)
    )
    control.mark_contained(record.incident_id)
    token = authority().issue(
        recovery_claims(
            clock,
            control.get(record.incident_id),
            to_mode=ContainmentMode.NORMAL,
        )
    )
    control.apply_recovery(token)
    control.close(record.incident_id)

    assert control.defense.ledger.verify()
    events = [entry.event for entry in control.defense.ledger.entries()]
    assert "incident.signal" in events
    assert "incident.contained" in events
    assert "incident.recovery" in events
    assert "incident.closed" in events
