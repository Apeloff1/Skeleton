from __future__ import annotations

from dataclasses import replace

from skeleton.automation.automation_safety import AutomationSafety
from skeleton.automation.control_plane import (
    AutomationControlPlane,
    AutomationOperation,
    AutomationPolicy,
    AutomationRequest,
    CircuitState,
    PermitAuthority,
    PermitClaims,
    PermitKey,
    build_actor_from_github,
)
from skeleton.security.defense_plane import DefensePlane, TrustLevel


NOW = 1_800_000_000.0
KEY = PermitKey("current", b"x" * 32)


def actor(*, trusted: bool = True):
    return build_actor_from_github(
        subject="automation:repair",
        repository="Apeloff1/Skeleton",
        workflow="Repair",
        run_id=100,
        run_attempt=1,
        ref="refs/heads/main",
        commit_sha="b" * 40,
        event="workflow_run",
        trusted=trusted,
    )


def request(
    operation: AutomationOperation = AutomationOperation.CREATE_ISSUE,
    *,
    nonce: str = "nonce-0001",
    resource: str = "repo:Apeloff1/Skeleton/issues/new",
):
    return AutomationRequest(
        request_id="req-automation-0001",
        nonce=nonce,
        issued_at=NOW,
        operation=operation,
        resource=resource,
        actor=actor(),
        reason="repair deterministic failure",
    )


def permit_for(req: AutomationRequest, *, operations=None, scopes=None, max_uses=1):
    claims = PermitClaims(
        permit_id="permit-00000001",
        key_id="current",
        actor_fingerprint=req.actor.fingerprint,
        repository=req.actor.repository,
        operations=tuple(operations or (req.operation,)),
        resource_scopes=tuple(scopes or ("repo:Apeloff1/Skeleton/issues/*",)),
        issued_at=NOW - 1,
        expires_at=NOW + 120,
        max_uses=max_uses,
    )
    authority = PermitAuthority((KEY,), active_key_id="current")
    return authority, authority.issue(claims)


def control(req: AutomationRequest, authority: PermitAuthority, **policy_overrides):
    return AutomationControlPlane(
        authority=authority,
        defense=DefensePlane(clock=lambda: NOW),
        safety=AutomationSafety(paused=False, quarantined=False),
        policy=AutomationPolicy(**policy_overrides),
        clock=lambda: NOW,
    )


def test_signed_permit_authorizes_exact_mutation() -> None:
    req = request()
    authority, token = permit_for(req)
    decision = control(req, authority).authorize(req, permit_token=token)
    assert decision.allowed is True
    assert decision.permit_id == "permit-00000001"


def test_tampered_permit_is_denied_without_raw_error() -> None:
    req = request()
    authority, token = permit_for(req)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    decision = control(req, authority).authorize(req, permit_token=tampered)
    assert decision.allowed is False
    assert decision.reason == "automation permit verification failed"


def test_permit_is_bound_to_actor_identity() -> None:
    req = request()
    authority, token = permit_for(req)
    other_actor = replace(actor(), run_id=101)
    other = replace(req, actor=other_actor, nonce="nonce-0002")
    decision = control(other, authority).authorize(other, permit_token=token)
    assert decision.allowed is False


def test_permit_operation_and_resource_scope_are_both_required() -> None:
    req = request()
    authority, token = permit_for(
        req,
        operations=(AutomationOperation.COMMENT,),
    )
    assert control(req, authority).authorize(req, permit_token=token).allowed is False

    authority2, token2 = permit_for(
        req,
        scopes=("repo:Apeloff1/Skeleton/pulls/*",),
    )
    assert control(req, authority2).authorize(req, permit_token=token2).allowed is False


def test_permit_replay_or_use_exhaustion_is_denied() -> None:
    req = request()
    authority, token = permit_for(req, max_uses=1)
    cp = control(req, authority)
    assert cp.authorize(req, permit_token=token).allowed is True
    replay = replace(req, nonce="nonce-0002", request_id="req-automation-0002")
    assert cp.authorize(replay, permit_token=token).allowed is False


def test_operator_quarantine_preempts_permit() -> None:
    req = request()
    authority, token = permit_for(req)
    cp = AutomationControlPlane(
        authority=authority,
        defense=DefensePlane(clock=lambda: NOW),
        safety=AutomationSafety(paused=False, quarantined=True, reason="incident"),
        clock=lambda: NOW,
    )
    assert cp.authorize(req, permit_token=token).reason == "automation is quarantined"


def test_destructive_operations_disabled_by_default() -> None:
    req = request(
        AutomationOperation.DELETE_BRANCH,
        resource="repo:Apeloff1/Skeleton/refs/heads/tmp",
    )
    authority, token = permit_for(
        req,
        scopes=("repo:Apeloff1/Skeleton/refs/heads/*",),
    )
    decision = control(req, authority).authorize(req, permit_token=token)
    assert decision.allowed is False
    assert "destructive automation is disabled" in decision.reason


def test_circuit_breaker_opens_after_repeated_bad_authority() -> None:
    req = request()
    authority, token = permit_for(req)
    cp = control(req, authority, failure_threshold=2)

    for index in range(2):
        bad = replace(
            req,
            request_id=f"req-automation-000{index + 2}",
            nonce=f"nonce-000{index + 2}",
        )
        assert cp.authorize(bad, permit_token=token + "bad").allowed is False

    assert cp.breaker is not None
    assert cp.breaker.state(req.actor) is CircuitState.OPEN
    fresh = replace(req, request_id="req-automation-0009", nonce="nonce-0009")
    assert cp.authorize(fresh, permit_token=token).reason == "automation circuit breaker is open"


def test_untrusted_actor_cannot_cross_defense_plane() -> None:
    req = request()
    req = replace(req, actor=actor(trusted=False))
    authority, token = permit_for(req)
    decision = control(req, authority).authorize(req, permit_token=token)
    assert decision.allowed is False
    assert decision.defense_code
