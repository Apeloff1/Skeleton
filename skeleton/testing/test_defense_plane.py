from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.security.defense_plane import (
    ActionClass,
    ActorIdentity,
    ContainmentMode,
    DecisionCode,
    DefenseConfigurationError,
    DefenseIntegrityError,
    DefensePlane,
    DefensePolicy,
    IntegrityLedger,
    ReplayWindow,
    SecurityRequest,
    SignalKind,
    SlidingWindowBudget,
    TrustLevel,
)


SHA = "a" * 40


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def actor(
    *,
    trust: TrustLevel = TrustLevel.TRUSTED,
    subject: str = "github:automation",
    run_id: int = 100,
) -> ActorIdentity:
    return ActorIdentity(
        subject=subject,
        source="github-actions",
        repository="Apeloff1/Skeleton",
        workflow="Merge Readiness",
        run_id=run_id,
        run_attempt=1,
        ref="refs/heads/main",
        commit_sha=SHA,
        event="workflow_dispatch",
        trust=trust,
    )


def request(
    clock: Clock,
    *,
    action: ActionClass = ActionClass.READ,
    capabilities: frozenset[str] | None = None,
    actor_value: ActorIdentity | None = None,
    request_id: str = "request-0001",
    nonce: str = "nonce-0001",
    resource: str = "repo:Apeloff1/Skeleton",
    issued_at: float | None = None,
    metadata: tuple[tuple[str, str], ...] = (),
) -> SecurityRequest:
    if capabilities is None:
        capabilities = {
            ActionClass.OBSERVE: frozenset(),
            ActionClass.READ: frozenset({"resource.read"}),
            ActionClass.WRITE: frozenset({"resource.write"}),
            ActionClass.EXECUTE: frozenset({"execution.run"}),
            ActionClass.NETWORK: frozenset({"network.egress"}),
            ActionClass.CREDENTIAL: frozenset({"secret.read"}),
            ActionClass.POLICY: frozenset({"policy.write"}),
            ActionClass.RELEASE: frozenset({"release.write"}),
        }[action]
    return SecurityRequest(
        request_id=request_id,
        nonce=nonce,
        issued_at=clock() if issued_at is None else issued_at,
        action=action,
        resource=resource,
        actor=actor_value or actor(),
        capabilities=capabilities,
        metadata=metadata,
    )


def plane(clock: Clock, **policy_overrides: object) -> DefensePlane:
    return DefensePlane(
        policy=DefensePolicy(**policy_overrides),
        clock=clock,
    )


def test_trusted_read_is_allowed_and_audited() -> None:
    clock = Clock()
    defense = plane(clock)

    decision = defense.evaluate(request(clock))

    assert decision.allowed
    assert decision.code is DecisionCode.ALLOW
    assert defense.ledger.verify()
    entries = defense.ledger.entries()
    assert len(entries) == 1
    assert entries[0].decision == DecisionCode.ALLOW.value


def test_trusted_write_requires_explicit_capability() -> None:
    clock = Clock()
    defense = plane(clock)

    denied = defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            capabilities=frozenset(),
        )
    )

    assert not denied.allowed
    assert denied.code is DecisionCode.DENY_CAPABILITY
    assert denied.missing_capabilities == ("resource.write",)


def test_untrusted_actor_is_observe_only_by_default() -> None:
    clock = Clock()
    defense = plane(clock)
    outsider = actor(trust=TrustLevel.UNTRUSTED, subject="external:observer")

    observed = defense.evaluate(
        request(
            clock,
            action=ActionClass.OBSERVE,
            capabilities=frozenset(),
            actor_value=outsider,
            request_id="request-observe",
            nonce="nonce-observe",
        )
    )
    denied = defense.evaluate(
        request(
            clock,
            action=ActionClass.READ,
            capabilities=frozenset({"resource.read"}),
            actor_value=outsider,
            request_id="request-read01",
            nonce="nonce-read01",
        )
    )

    assert observed.allowed
    assert not denied.allowed
    assert denied.code is DecisionCode.DENY_TRUST


def test_policy_can_allow_untrusted_read_without_allowing_mutation() -> None:
    clock = Clock()
    defense = plane(clock, allow_untrusted_reads=True)
    outsider = actor(trust=TrustLevel.UNTRUSTED, subject="external:reader")

    read = defense.evaluate(
        request(
            clock,
            action=ActionClass.READ,
            actor_value=outsider,
            request_id="request-read02",
            nonce="nonce-read02",
        )
    )
    write = defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            actor_value=outsider,
            request_id="request-write1",
            nonce="nonce-write1",
        )
    )

    assert read.allowed
    assert not write.allowed
    assert write.code is DecisionCode.DENY_TRUST


@pytest.mark.parametrize(
    "action",
    [ActionClass.CREDENTIAL, ActionClass.POLICY, ActionClass.RELEASE],
)
def test_authenticated_actor_cannot_cross_privileged_boundary(action: ActionClass) -> None:
    clock = Clock()
    defense = plane(clock)
    authenticated = actor(
        trust=TrustLevel.AUTHENTICATED,
        subject="service:authenticated",
    )

    decision = defense.evaluate(
        request(
            clock,
            action=action,
            actor_value=authenticated,
            request_id=f"request-{action.value.replace('.', '-')}",
            nonce=f"nonce-{action.value.replace('.', '-')}",
        )
    )

    assert not decision.allowed
    assert decision.code is DecisionCode.DENY_TRUST


def test_stale_request_fails_closed() -> None:
    clock = Clock()
    defense = plane(clock, max_request_age_seconds=60.0)

    decision = defense.evaluate(
        request(
            clock,
            issued_at=clock() - 61.0,
            request_id="request-stale1",
            nonce="nonce-stale1",
        )
    )

    assert not decision.allowed
    assert decision.code is DecisionCode.DENY_STALE


def test_future_request_fails_closed() -> None:
    clock = Clock()
    defense = plane(clock, max_future_skew_seconds=10.0)

    decision = defense.evaluate(
        request(
            clock,
            issued_at=clock() + 11.0,
            request_id="request-future",
            nonce="nonce-future",
        )
    )

    assert not decision.allowed
    assert decision.code is DecisionCode.DENY_FUTURE


def test_exact_request_identity_is_one_shot() -> None:
    clock = Clock()
    defense = plane(clock)
    item = request(clock)

    first = defense.evaluate(item)
    second = defense.evaluate(item)

    assert first.allowed
    assert not second.allowed
    assert second.code is DecisionCode.DENY_REPLAY


def test_request_id_can_be_reused_only_with_fresh_nonce() -> None:
    clock = Clock()
    defense = plane(clock)

    first = defense.evaluate(
        request(clock, request_id="request-shared", nonce="nonce-first1")
    )
    second = defense.evaluate(
        request(clock, request_id="request-shared", nonce="nonce-second")
    )

    assert first.allowed
    assert second.allowed


def test_replay_key_is_actor_bound() -> None:
    clock = Clock()
    defense = plane(clock)
    first_actor = actor(subject="automation:first", run_id=1)
    second_actor = actor(subject="automation:second", run_id=2)

    first = defense.evaluate(
        request(
            clock,
            actor_value=first_actor,
            request_id="request-shared",
            nonce="nonce-shared1",
        )
    )
    second = defense.evaluate(
        request(
            clock,
            actor_value=second_actor,
            request_id="request-shared",
            nonce="nonce-shared1",
        )
    )

    assert first.allowed
    assert second.allowed


def test_write_budget_is_per_actor_and_bounded() -> None:
    clock = Clock()
    defense = plane(
        clock,
        max_writes_per_window=2,
        mutation_window_seconds=60.0,
    )

    decisions = [
        defense.evaluate(
            request(
                clock,
                action=ActionClass.WRITE,
                request_id=f"request-write{i}",
                nonce=f"nonce-write{i}",
            )
        )
        for i in range(3)
    ]

    assert [item.allowed for item in decisions] == [True, True, False]
    assert decisions[-1].code is DecisionCode.DENY_BUDGET


def test_write_budget_recovers_after_window() -> None:
    clock = Clock()
    defense = plane(
        clock,
        max_writes_per_window=1,
        mutation_window_seconds=10.0,
    )

    assert defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            request_id="request-budget1",
            nonce="nonce-budget1",
        )
    ).allowed
    assert not defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            request_id="request-budget2",
            nonce="nonce-budget2",
        )
    ).allowed

    clock.advance(11.0)

    assert defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            request_id="request-budget3",
            nonce="nonce-budget3",
        )
    ).allowed


@pytest.mark.parametrize(
    ("mode", "action", "allowed"),
    [
        (ContainmentMode.NORMAL, ActionClass.POLICY, True),
        (ContainmentMode.RESTRICTED, ActionClass.WRITE, True),
        (ContainmentMode.RESTRICTED, ActionClass.EXECUTE, False),
        (ContainmentMode.QUARANTINE, ActionClass.READ, True),
        (ContainmentMode.QUARANTINE, ActionClass.WRITE, False),
        (ContainmentMode.LOCKDOWN, ActionClass.OBSERVE, True),
        (ContainmentMode.LOCKDOWN, ActionClass.READ, False),
    ],
)
def test_containment_modes_reduce_authority(
    mode: ContainmentMode,
    action: ActionClass,
    allowed: bool,
) -> None:
    clock = Clock()
    defense = plane(clock)
    defense.set_mode(mode)

    decision = defense.evaluate(
        request(
            clock,
            action=action,
            request_id=f"request-{mode.value}-{action.value}".replace(".", "-"),
            nonce=f"nonce-{mode.value}-{action.value}".replace(".", "-"),
        )
    )

    assert decision.allowed is allowed
    if not allowed:
        assert decision.code is DecisionCode.DENY_CONTAINMENT


@pytest.mark.parametrize(
    "metadata",
    [
        (("permissions", "write-all"),),
        (("grant", "network.egress"),),
        (("admin", "true"),),
        (("secret", "read"),),
        (("bypass", "enabled"),),
    ],
)
def test_authority_escalation_in_request_metadata_is_denied(
    metadata: tuple[tuple[str, str], ...],
) -> None:
    clock = Clock()
    defense = plane(clock)

    decision = defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            request_id="request-escalate",
            nonce="nonce-escalate",
            metadata=metadata,
        )
    )

    assert not decision.allowed
    assert decision.code is DecisionCode.DENY_ESCALATION


def test_benign_metadata_does_not_trigger_escalation_detector() -> None:
    clock = Clock()
    defense = plane(clock)

    decision = defense.evaluate(
        request(
            clock,
            action=ActionClass.WRITE,
            request_id="request-meta001",
            nonce="nonce-meta001",
            metadata=(
                ("automation_operation", "issue.comment"),
                ("permit_id", "permit-0001"),
            ),
        )
    )

    assert decision.allowed


def test_repeated_hostile_signals_quarantine_actor() -> None:
    clock = Clock()
    defense = plane(
        clock,
        quarantine_threshold=5,
        quarantine_seconds=30.0,
    )
    principal = actor(subject="automation:suspicious")

    score = defense.report_signal(
        principal.fingerprint,
        SignalKind.CAPABILITY_ESCALATION,
    )
    assert score == 5

    decision = defense.evaluate(
        request(
            clock,
            actor_value=principal,
            request_id="request-quarantine",
            nonce="nonce-quarantine",
        )
    )

    assert not decision.allowed
    assert decision.code is DecisionCode.DENY_QUARANTINE


def test_quarantine_expires_after_ttl() -> None:
    clock = Clock()
    defense = plane(
        clock,
        quarantine_threshold=5,
        quarantine_seconds=10.0,
    )
    principal = actor(subject="automation:recoverable")

    defense.report_signal(
        principal.fingerprint,
        SignalKind.CAPABILITY_ESCALATION,
    )
    blocked = defense.evaluate(
        request(
            clock,
            actor_value=principal,
            request_id="request-blocked1",
            nonce="nonce-blocked1",
        )
    )
    assert blocked.code is DecisionCode.DENY_QUARANTINE

    clock.advance(11.0)

    allowed = defense.evaluate(
        request(
            clock,
            actor_value=principal,
            request_id="request-afterttl",
            nonce="nonce-afterttl",
        )
    )
    assert allowed.allowed


def test_replay_signal_can_auto_quarantine_after_repeated_abuse() -> None:
    clock = Clock()
    defense = plane(
        clock,
        quarantine_threshold=6,
        quarantine_seconds=60.0,
    )
    principal = actor(subject="automation:replayer")
    first = request(
        clock,
        actor_value=principal,
        request_id="request-replay1",
        nonce="nonce-replay01",
    )
    assert defense.evaluate(first).allowed
    assert defense.evaluate(first).code is DecisionCode.DENY_REPLAY

    second = request(
        clock,
        actor_value=principal,
        request_id="request-replay2",
        nonce="nonce-replay02",
    )
    assert defense.evaluate(second).allowed
    assert defense.evaluate(second).code is DecisionCode.DENY_REPLAY

    blocked = defense.evaluate(
        request(
            clock,
            actor_value=principal,
            request_id="request-final01",
            nonce="nonce-final001",
        )
    )
    assert blocked.code is DecisionCode.DENY_QUARANTINE


def test_actor_fingerprint_changes_with_execution_provenance() -> None:
    first = actor(run_id=1)
    second = actor(run_id=2)
    assert first.fingerprint != second.fingerprint

    changed_sha = replace(first, commit_sha="b" * 40)
    assert first.fingerprint != changed_sha.fingerprint


@pytest.mark.parametrize(
    "sha",
    ["a" * 39, "g" * 40, "A" * 40, "", "../main"],
)
def test_actor_rejects_invalid_commit_identity(sha: str) -> None:
    with pytest.raises(DefenseIntegrityError):
        ActorIdentity(
            subject="github:automation",
            source="github-actions",
            repository="Apeloff1/Skeleton",
            workflow="CI",
            run_id=1,
            run_attempt=1,
            ref="refs/heads/main",
            commit_sha=sha,
            event="push",
            trust=TrustLevel.TRUSTED,
        )


def test_request_rejects_duplicate_metadata_keys() -> None:
    clock = Clock()
    with pytest.raises(DefenseIntegrityError, match="duplicate metadata"):
        request(
            clock,
            metadata=(("key", "one"), ("key", "two")),
        )


def test_request_rejects_unknown_capability_shape() -> None:
    clock = Clock()
    with pytest.raises(DefenseIntegrityError, match="capability"):
        request(
            clock,
            capabilities=frozenset({"../../root"}),
        )


def test_replay_window_is_bounded() -> None:
    replay = ReplayWindow(ttl_seconds=100.0, max_entries=2)

    assert not replay.seen_or_record("first", 1.0)
    assert not replay.seen_or_record("second", 1.0)
    assert not replay.seen_or_record("third", 1.0)
    assert len(replay) == 2


def test_replay_window_expires_entries() -> None:
    replay = ReplayWindow(ttl_seconds=5.0, max_entries=10)

    assert not replay.seen_or_record("first", 1.0)
    assert replay.seen_or_record("first", 2.0)
    assert not replay.seen_or_record("first", 7.0)


def test_sliding_window_budget_is_bounded_and_recovers() -> None:
    budget = SlidingWindowBudget(window_seconds=10.0)
    key = ("actor", "write")

    assert budget.allow(key, limit=2, now=1.0)
    assert budget.allow(key, limit=2, now=2.0)
    assert not budget.allow(key, limit=2, now=3.0)
    assert budget.count(key, now=3.0) == 2
    assert budget.allow(key, limit=2, now=12.1)


def test_ledger_hash_chain_verifies() -> None:
    ledger = IntegrityLedger()
    ledger.append(
        timestamp=1.0,
        event="security.event",
        subject="actor",
        decision="allow",
        request_fingerprint="a" * 64,
    )
    ledger.append(
        timestamp=2.0,
        event="security.event",
        subject="actor",
        decision="deny",
        request_fingerprint="b" * 64,
    )

    assert ledger.verify()


def test_hmac_authenticated_ledger_verifies() -> None:
    ledger = IntegrityLedger(hmac_key=b"k" * 32)
    entry = ledger.append(
        timestamp=1.0,
        event="security.event",
        subject="actor",
        decision="allow",
        request_fingerprint="a" * 64,
    )

    assert len(entry.mac) == 64
    assert ledger.verify()


def test_ledger_rejects_weak_hmac_key() -> None:
    with pytest.raises(DefenseConfigurationError, match="at least 32"):
        IntegrityLedger(hmac_key=b"weak")


def test_ledger_remains_verifiable_after_bounded_eviction() -> None:
    ledger = IntegrityLedger(max_entries=2)
    for index in range(5):
        ledger.append(
            timestamp=float(index + 1),
            event="security.event",
            subject="actor",
            decision="allow",
            request_fingerprint=f"{index:064x}",
        )

    assert len(ledger.entries()) == 2
    assert ledger.verify()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_request_age_seconds", 0),
        ("max_future_skew_seconds", float("nan")),
        ("replay_ttl_seconds", -1),
        ("mutation_window_seconds", float("inf")),
        ("quarantine_seconds", 0),
        ("max_writes_per_window", 0),
        ("quarantine_threshold", -1),
    ],
)
def test_defense_policy_rejects_invalid_limits(field: str, value: object) -> None:
    kwargs = {field: value}
    with pytest.raises(DefenseConfigurationError):
        DefensePolicy(**kwargs)


def test_snapshot_exposes_only_bounded_control_state() -> None:
    clock = Clock()
    defense = plane(clock)
    defense.evaluate(request(clock))

    snapshot = defense.snapshot()

    assert snapshot == {
        "mode": "normal",
        "ledger_entries": 1,
        "ledger_valid": True,
        "replay_entries": 1,
        "timestamp": clock(),
    }
    assert "resource" not in snapshot
    assert "metadata" not in snapshot
