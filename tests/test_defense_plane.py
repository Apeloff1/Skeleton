from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.security.defense_plane import (
    ActionClass,
    ActorIdentity,
    ContainmentMode,
    DecisionCode,
    DefensePlane,
    DefensePolicy,
    IntegrityLedger,
    SecurityRequest,
    SignalKind,
    TrustLevel,
)


NOW = 1_800_000_000.0


def actor(*, trust: TrustLevel = TrustLevel.TRUSTED) -> ActorIdentity:
    return ActorIdentity(
        subject="automation:ci",
        source="github-actions",
        repository="Apeloff1/Skeleton",
        workflow="Security",
        run_id=123,
        run_attempt=1,
        ref="refs/heads/main",
        commit_sha="a" * 40,
        event="workflow_run",
        trust=trust,
    )


def request(
    *,
    action: ActionClass = ActionClass.WRITE,
    capabilities=frozenset({"resource.write"}),
    nonce: str = "nonce-0001",
    issued_at: float = NOW,
    metadata=(),
    identity: ActorIdentity | None = None,
) -> SecurityRequest:
    return SecurityRequest(
        request_id="req-00000001",
        nonce=nonce,
        issued_at=issued_at,
        action=action,
        resource="repo:Apeloff1/Skeleton/issues/1",
        actor=identity or actor(),
        capabilities=frozenset(capabilities),
        metadata=tuple(metadata),
    )


def plane(**policy_overrides) -> DefensePlane:
    policy = DefensePolicy(**policy_overrides)
    return DefensePlane(policy=policy, clock=lambda: NOW)


def test_allows_fresh_trusted_capability_bound_request() -> None:
    decision = plane().evaluate(request())
    assert decision.allowed is True
    assert decision.code is DecisionCode.ALLOW


def test_denies_replay_of_same_actor_request_and_nonce() -> None:
    security = plane()
    first = security.evaluate(request())
    second = security.evaluate(request())
    assert first.allowed is True
    assert second.allowed is False
    assert second.code is DecisionCode.DENY_REPLAY


def test_denies_stale_and_future_requests() -> None:
    assert plane().evaluate(request(issued_at=NOW - 301)).code is DecisionCode.DENY_STALE
    assert plane().evaluate(request(issued_at=NOW + 31)).code is DecisionCode.DENY_FUTURE


def test_untrusted_actor_cannot_mutate() -> None:
    decision = plane().evaluate(request(identity=actor(trust=TrustLevel.UNTRUSTED)))
    assert decision.code is DecisionCode.DENY_TRUST


def test_missing_capability_denies() -> None:
    decision = plane().evaluate(request(capabilities=frozenset()))
    assert decision.code is DecisionCode.DENY_CAPABILITY
    assert decision.missing_capabilities == ("resource.write",)


def test_metadata_cannot_widen_authority() -> None:
    decision = plane().evaluate(
        request(metadata=(("permissions", "admin"),))
    )
    assert decision.code is DecisionCode.DENY_ESCALATION


def test_restricted_mode_blocks_privileged_actions() -> None:
    security = plane()
    security.set_mode(ContainmentMode.RESTRICTED)
    decision = security.evaluate(
        request(
            action=ActionClass.EXECUTE,
            capabilities=frozenset({"execution.run"}),
        )
    )
    assert decision.code is DecisionCode.DENY_CONTAINMENT


def test_lockdown_allows_observation_only() -> None:
    security = plane()
    security.set_mode(ContainmentMode.LOCKDOWN)
    allowed = security.evaluate(
        request(
            action=ActionClass.OBSERVE,
            capabilities=frozenset(),
        )
    )
    denied = security.evaluate(
        replace(
            request(
                action=ActionClass.READ,
                capabilities=frozenset({"resource.read"}),
                nonce="nonce-0002",
            ),
            request_id="req-00000002",
        )
    )
    assert allowed.allowed is True
    assert denied.code is DecisionCode.DENY_CONTAINMENT


def test_budget_exhaustion_fails_closed() -> None:
    security = plane(max_writes_per_window=1)
    assert security.evaluate(request()).allowed
    second = replace(request(nonce="nonce-0002"), request_id="req-00000002")
    assert security.evaluate(second).code is DecisionCode.DENY_BUDGET


def test_signals_auto_quarantine_subject() -> None:
    security = plane(quarantine_threshold=5)
    subject = actor().fingerprint
    score = security.report_signal(subject, SignalKind.CAPABILITY_ESCALATION)
    assert score >= 5
    later = security.evaluate(request(nonce="nonce-0009"))
    assert later.code is DecisionCode.DENY_QUARANTINE


def test_integrity_ledger_detects_tampering() -> None:
    ledger = IntegrityLedger(hmac_key=b"k" * 32)
    ledger.append(
        timestamp=NOW,
        event="defense.decision",
        subject="subject",
        decision="allow",
        request_fingerprint="f" * 64,
    )
    assert ledger.verify() is True
    original = ledger._entries[0]
    ledger._entries[0] = replace(original, decision="deny")
    assert ledger.verify() is False
