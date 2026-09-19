from __future__ import annotations

import json

import pytest

from skeleton.automation.automation_safety import AutomationSafety
from skeleton.automation.control_plane import (
    AutomationControlError,
    AutomationControlPlane,
    AutomationOperation,
    AutomationPolicy,
    AutomationRequest,
    CircuitBreaker,
    CircuitState,
    MutationBudget,
    OperationRisk,
    PermitAuthority,
    PermitClaims,
    PermitKey,
    PermitUseLedger,
    build_actor_from_github,
)
from skeleton.security.defense_plane import (
    ActorIdentity,
    ContainmentMode,
    DefensePlane,
    DefensePolicy,
    TrustLevel,
)


SHA = "a" * 40
KEY = PermitKey("primary", b"k" * 32)


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def actor(
    *,
    run_id: int = 101,
    trust: TrustLevel = TrustLevel.TRUSTED,
    repository: str = "Apeloff1/Skeleton",
) -> ActorIdentity:
    return ActorIdentity(
        subject="github:security-automation",
        source="github-actions",
        repository=repository,
        workflow="Security Automation",
        run_id=run_id,
        run_attempt=1,
        ref="refs/heads/main",
        commit_sha=SHA,
        event="workflow_dispatch",
        trust=trust,
    )


def authority() -> PermitAuthority:
    return PermitAuthority(
        keys=(KEY,),
        active_key_id="primary",
        max_ttl_seconds=600.0,
    )


def claims(
    clock: Clock,
    actor_value: ActorIdentity,
    *,
    permit_id: str = "permit-0001",
    operations: tuple[AutomationOperation, ...] = (
        AutomationOperation.COMMENT,
    ),
    scopes: tuple[str, ...] = ("issue:123",),
    ttl: float = 300.0,
    max_uses: int = 1,
) -> PermitClaims:
    return PermitClaims(
        permit_id=permit_id,
        key_id="primary",
        actor_fingerprint=actor_value.fingerprint,
        repository=actor_value.repository,
        operations=operations,
        resource_scopes=scopes,
        issued_at=clock(),
        expires_at=clock() + ttl,
        max_uses=max_uses,
    )


def request(
    clock: Clock,
    actor_value: ActorIdentity,
    *,
    operation: AutomationOperation = AutomationOperation.COMMENT,
    resource: str = "issue:123",
    request_id: str = "request-0001",
    nonce: str = "nonce-0001",
) -> AutomationRequest:
    return AutomationRequest(
        request_id=request_id,
        nonce=nonce,
        issued_at=clock(),
        operation=operation,
        resource=resource,
        actor=actor_value,
        reason="security repair automation",
    )


def control_plane(
    clock: Clock,
    *,
    safety: AutomationSafety | None = None,
    policy: AutomationPolicy | None = None,
    defense: DefensePlane | None = None,
) -> AutomationControlPlane:
    return AutomationControlPlane(
        authority=authority(),
        defense=defense
        or DefensePlane(
            policy=DefensePolicy(),
            clock=clock,
        ),
        safety=safety or AutomationSafety(False, False, ""),
        policy=policy or AutomationPolicy(),
        clock=clock,
    )


def test_permit_round_trip_is_actor_and_repository_bound() -> None:
    clock = Clock()
    principal = actor()
    permit_authority = authority()
    permit_claims = claims(clock, principal)

    token = permit_authority.issue(permit_claims)
    verified = permit_authority.verify(token, actor=principal, now=clock())

    assert verified == permit_claims
    assert token.startswith("v1.")
    assert token.count(".") == 2


def test_permit_signature_tamper_is_rejected() -> None:
    clock = Clock()
    principal = actor()
    permit_authority = authority()
    token = permit_authority.issue(claims(clock, principal))

    prefix, payload, signature = token.split(".")
    tampered = f"{prefix}.{payload}.{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"

    with pytest.raises(AutomationControlError, match="verification failed"):
        permit_authority.verify(tampered, actor=principal, now=clock())


def test_permit_payload_tamper_is_rejected() -> None:
    clock = Clock()
    principal = actor()
    permit_authority = authority()
    token = permit_authority.issue(claims(clock, principal))
    prefix, payload, signature = token.split(".")
    replacement = ("A" if payload[0] != "A" else "B") + payload[1:]

    with pytest.raises(AutomationControlError):
        permit_authority.verify(
            f"{prefix}.{replacement}.{signature}",
            actor=principal,
            now=clock(),
        )


def test_permit_is_bound_to_exact_actor_provenance() -> None:
    clock = Clock()
    first = actor(run_id=1)
    second = actor(run_id=2)
    token = authority().issue(claims(clock, first))

    with pytest.raises(AutomationControlError, match="actor binding"):
        authority().verify(token, actor=second, now=clock())


def test_permit_is_bound_to_repository() -> None:
    clock = Clock()
    principal = actor(repository="Apeloff1/Skeleton")
    other_repo = actor(repository="Apeloff1/Other")
    permit_claims = PermitClaims(
        permit_id="permit-repo1",
        key_id="primary",
        actor_fingerprint=other_repo.fingerprint,
        repository=principal.repository,
        operations=(AutomationOperation.COMMENT,),
        resource_scopes=("issue:123",),
        issued_at=clock(),
        expires_at=clock() + 60,
        max_uses=1,
    )
    token = authority().issue(permit_claims)

    with pytest.raises(AutomationControlError, match="actor binding"):
        authority().verify(token, actor=other_repo, now=clock())


def test_expired_permit_is_rejected() -> None:
    clock = Clock()
    principal = actor()
    permit_authority = authority()
    token = permit_authority.issue(claims(clock, principal, ttl=10.0))

    clock.advance(11.0)

    with pytest.raises(AutomationControlError, match="expired"):
        permit_authority.verify(token, actor=principal, now=clock())


def test_overlong_permit_ttl_is_rejected_at_issue_time() -> None:
    clock = Clock()
    principal = actor()
    with pytest.raises(AutomationControlError, match="ttl exceeds"):
        authority().issue(claims(clock, principal, ttl=601.0))


def test_unknown_signing_key_is_rejected() -> None:
    with pytest.raises(AutomationControlError, match="active permit key"):
        PermitAuthority(keys=(KEY,), active_key_id="missing")


def test_weak_signing_key_is_rejected() -> None:
    with pytest.raises(AutomationControlError, match="at least 32"):
        PermitKey("weak", b"short")


def test_permit_operations_are_unique_and_bounded() -> None:
    clock = Clock()
    principal = actor()

    with pytest.raises(AutomationControlError, match="unique"):
        PermitClaims(
            permit_id="permit-dupe",
            key_id="primary",
            actor_fingerprint=principal.fingerprint,
            repository=principal.repository,
            operations=(
                AutomationOperation.COMMENT,
                AutomationOperation.COMMENT,
            ),
            resource_scopes=("issue:123",),
            issued_at=clock(),
            expires_at=clock() + 60,
            max_uses=1,
        )


@pytest.mark.parametrize(
    "scope",
    [
        "*",
        "issue*",
        "issue:12*3",
        "repo/**/secret",
    ],
)
def test_unsafe_resource_scope_shapes_are_rejected(scope: str) -> None:
    clock = Clock()
    principal = actor()

    with pytest.raises(AutomationControlError):
        claims(clock, principal, scopes=(scope,))


def test_exact_resource_scope_authorizes_only_exact_resource() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(claims(clock, principal, scopes=("issue:123",)))

    allowed = cp.authorize(
        request(clock, principal, resource="issue:123"),
        permit_token=token,
    )

    assert allowed.allowed


def test_prefix_resource_scope_authorizes_bounded_family() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(
        claims(
            clock,
            principal,
            scopes=("issue:*",),
            max_uses=2,
        )
    )

    first = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:123",
            request_id="request-scope01",
            nonce="nonce-scope001",
        ),
        permit_token=token,
    )
    second = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:999",
            request_id="request-scope02",
            nonce="nonce-scope002",
        ),
        permit_token=token,
    )

    assert first.allowed
    assert second.allowed


def test_resource_outside_permit_scope_is_denied() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(claims(clock, principal, scopes=("issue:123",)))

    decision = cp.authorize(
        request(clock, principal, resource="issue:124"),
        permit_token=token,
    )

    assert not decision.allowed
    assert "resource" in decision.reason


def test_operation_outside_permit_scope_is_denied() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(
        claims(
            clock,
            principal,
            operations=(AutomationOperation.COMMENT,),
            scopes=("issue:123",),
        )
    )

    decision = cp.authorize(
        request(
            clock,
            principal,
            operation=AutomationOperation.UPDATE_ISSUE,
            resource="issue:123",
        ),
        permit_token=token,
    )

    assert not decision.allowed
    assert "operation" in decision.reason


def test_mutation_without_permit_is_denied() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)

    decision = cp.authorize(request(clock, principal))

    assert not decision.allowed
    assert decision.reason == "mutating automation requires a permit"


def test_read_only_operation_does_not_require_permit() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)

    decision = cp.authorize(
        request(
            clock,
            principal,
            operation=AutomationOperation.READ_REPOSITORY,
            resource="repo:Apeloff1/Skeleton",
        )
    )

    assert decision.allowed


def test_operator_pause_preempts_permit_processing() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(
        clock,
        safety=AutomationSafety(True, False, "maintenance"),
    )
    token = authority().issue(claims(clock, principal))

    decision = cp.authorize(request(clock, principal), permit_token=token)

    assert not decision.allowed
    assert "paused" in decision.reason
    assert cp.uses.uses("permit-0001") == 0


def test_operator_quarantine_preempts_permit_processing() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(
        clock,
        safety=AutomationSafety(False, True, "incident"),
    )
    token = authority().issue(claims(clock, principal))

    decision = cp.authorize(request(clock, principal), permit_token=token)

    assert not decision.allowed
    assert "quarantined" in decision.reason
    assert cp.uses.uses("permit-0001") == 0


def test_permit_request_identity_is_one_shot() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(
        claims(clock, principal, max_uses=5)
    )
    item = request(clock, principal)

    first = cp.authorize(item, permit_token=token)
    second = cp.authorize(item, permit_token=token)

    assert first.allowed
    assert not second.allowed
    assert "replayed" in second.reason


def test_permit_max_uses_is_enforced() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(
        claims(clock, principal, scopes=("issue:*",), max_uses=2)
    )

    first = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:1",
            request_id="request-use001",
            nonce="nonce-use0001",
        ),
        permit_token=token,
    )
    second = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:2",
            request_id="request-use002",
            nonce="nonce-use0002",
        ),
        permit_token=token,
    )
    third = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:3",
            request_id="request-use003",
            nonce="nonce-use0003",
        ),
        permit_token=token,
    )

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert cp.uses.uses("permit-0001") == 2


def test_mutation_budget_limits_one_actor_run() -> None:
    clock = Clock()
    principal = actor()
    policy = AutomationPolicy(max_mutations_per_run=1)
    cp = control_plane(clock, policy=policy)
    token = authority().issue(
        claims(clock, principal, scopes=("issue:*",), max_uses=3)
    )

    first = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:1",
            request_id="request-budget1",
            nonce="nonce-budget1",
        ),
        permit_token=token,
    )
    second = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:2",
            request_id="request-budget2",
            nonce="nonce-budget2",
        ),
        permit_token=token,
    )

    assert first.allowed
    assert not second.allowed
    assert second.reason == "automation mutation budget is exhausted"


def test_mutation_budget_is_actor_provenance_scoped() -> None:
    clock = Clock()
    first_actor = actor(run_id=1)
    second_actor = actor(run_id=2)
    policy = AutomationPolicy(max_mutations_per_run=1)
    cp = control_plane(clock, policy=policy)

    first_token = authority().issue(
        claims(clock, first_actor, permit_id="permit-first", scopes=("issue:*",))
    )
    second_token = authority().issue(
        claims(clock, second_actor, permit_id="permit-second", scopes=("issue:*",))
    )

    assert cp.authorize(
        request(
            clock,
            first_actor,
            resource="issue:1",
            request_id="request-first1",
            nonce="nonce-first01",
        ),
        permit_token=first_token,
    ).allowed
    assert cp.authorize(
        request(
            clock,
            second_actor,
            resource="issue:2",
            request_id="request-second",
            nonce="nonce-second1",
        ),
        permit_token=second_token,
    ).allowed


@pytest.mark.parametrize(
    "operation",
    [
        AutomationOperation.DELETE_BRANCH,
        AutomationOperation.RELEASE,
        AutomationOperation.POLICY_CHANGE,
        AutomationOperation.SECRET_READ,
    ],
)
def test_destructive_automation_is_disabled_by_default(
    operation: AutomationOperation,
) -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)

    decision = cp.authorize(
        request(
            clock,
            principal,
            operation=operation,
            resource="policy:protected",
        )
    )

    assert not decision.allowed
    assert "destructive" in decision.reason


def test_destructive_operation_needs_explicit_policy_and_permit() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(
        clock,
        policy=AutomationPolicy(allow_destructive=True),
    )
    token = authority().issue(
        claims(
            clock,
            principal,
            permit_id="permit-delete",
            operations=(AutomationOperation.DELETE_BRANCH,),
            scopes=("branch:stale",),
        )
    )

    decision = cp.authorize(
        request(
            clock,
            principal,
            operation=AutomationOperation.DELETE_BRANCH,
            resource="branch:stale",
        ),
        permit_token=token,
    )

    assert decision.allowed


def test_repository_defense_lockdown_blocks_mutating_automation() -> None:
    clock = Clock()
    principal = actor()
    defense = DefensePlane(clock=clock)
    defense.set_mode(ContainmentMode.LOCKDOWN)
    cp = control_plane(clock, defense=defense)
    token = authority().issue(claims(clock, principal))

    decision = cp.authorize(request(clock, principal), permit_token=token)

    assert not decision.allowed
    assert decision.defense_code == "deny.containment"


def test_untrusted_actor_cannot_mutate_even_with_valid_self_bound_permit() -> None:
    clock = Clock()
    principal = actor(trust=TrustLevel.UNTRUSTED)
    cp = control_plane(clock)
    token = authority().issue(claims(clock, principal))

    decision = cp.authorize(request(clock, principal), permit_token=token)

    assert not decision.allowed
    assert decision.defense_code == "deny.trust"


def test_receipt_ledger_records_allowed_and_denied_decisions_without_resource_plaintext() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(clock)
    token = authority().issue(claims(clock, principal, max_uses=2))

    allowed = cp.authorize(
        request(
            clock,
            principal,
            request_id="request-receipt",
            nonce="nonce-receipt1",
        ),
        permit_token=token,
    )
    denied = cp.authorize(
        request(
            clock,
            principal,
            resource="issue:999",
            request_id="request-denied1",
            nonce="nonce-denied01",
        ),
        permit_token=token,
    )

    assert allowed.allowed
    assert not denied.allowed
    receipts = cp.receipts.entries()
    assert len(receipts) == 2
    assert receipts[0].allowed is True
    assert receipts[1].allowed is False
    assert receipts[0].resource_digest
    assert not hasattr(receipts[0], "resource")


def test_repeated_authorization_failures_open_circuit() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(
        clock,
        policy=AutomationPolicy(failure_threshold=2),
    )
    bad_token = authority().issue(
        claims(
            clock,
            actor(run_id=999),
            permit_id="permit-wrongactor",
        )
    )

    first = cp.authorize(
        request(
            clock,
            principal,
            request_id="request-fail001",
            nonce="nonce-fail0001",
        ),
        permit_token=bad_token,
    )
    second = cp.authorize(
        request(
            clock,
            principal,
            request_id="request-fail002",
            nonce="nonce-fail0002",
        ),
        permit_token=bad_token,
    )
    third = cp.authorize(
        request(
            clock,
            principal,
            request_id="request-fail003",
            nonce="nonce-fail0003",
        ),
        permit_token=bad_token,
    )

    assert not first.allowed
    assert not second.allowed
    assert not third.allowed
    assert third.reason == "automation circuit breaker is open"


def test_circuit_breaker_transitions_to_half_open_then_closed() -> None:
    clock = Clock()
    principal = actor()
    policy = AutomationPolicy(
        failure_threshold=1,
        breaker_open_seconds=10.0,
        half_open_successes=2,
    )
    breaker = CircuitBreaker(policy, clock=clock)

    assert breaker.state(principal) is CircuitState.CLOSED
    assert breaker.record_failure(principal) is CircuitState.OPEN
    assert breaker.state(principal) is CircuitState.OPEN

    clock.advance(11.0)

    assert breaker.state(principal) is CircuitState.HALF_OPEN
    assert breaker.record_success(principal) is CircuitState.HALF_OPEN
    assert breaker.record_success(principal) is CircuitState.CLOSED


def test_failed_half_open_probe_reopens_circuit() -> None:
    clock = Clock()
    principal = actor()
    policy = AutomationPolicy(
        failure_threshold=1,
        breaker_open_seconds=5.0,
        half_open_successes=2,
    )
    breaker = CircuitBreaker(policy, clock=clock)

    breaker.record_failure(principal)
    clock.advance(6.0)
    assert breaker.state(principal) is CircuitState.HALF_OPEN
    assert breaker.record_failure(principal) is CircuitState.OPEN


def test_successful_execution_outcome_resets_closed_breaker_failure_count() -> None:
    clock = Clock()
    principal = actor()
    cp = control_plane(
        clock,
        policy=AutomationPolicy(failure_threshold=3),
    )
    assert cp.breaker is not None

    cp.breaker.record_failure(principal)
    assert cp.breaker.state(principal) is CircuitState.CLOSED

    read_request = request(
        clock,
        principal,
        operation=AutomationOperation.READ_REPOSITORY,
        resource="repo:Apeloff1/Skeleton",
    )
    decision = cp.authorize(read_request)
    assert decision.allowed
    assert cp.record_outcome(read_request, succeeded=True) is CircuitState.CLOSED

    cp.breaker.record_failure(principal)
    cp.breaker.record_failure(principal)
    assert cp.breaker.state(principal) is CircuitState.CLOSED


def test_build_actor_from_github_preserves_exact_provenance() -> None:
    principal = build_actor_from_github(
        subject="github:security-automation",
        repository="Apeloff1/Skeleton",
        workflow="Security Automation",
        run_id=42,
        run_attempt=2,
        ref="refs/heads/main",
        commit_sha=SHA,
        event="workflow_dispatch",
        trusted=True,
    )

    assert principal.repository == "Apeloff1/Skeleton"
    assert principal.run_id == 42
    assert principal.run_attempt == 2
    assert principal.trust is TrustLevel.TRUSTED


def test_permit_json_duplicate_fields_fail_closed() -> None:
    clock = Clock()
    principal = actor()
    permit_authority = authority()
    token = permit_authority.issue(claims(clock, principal))
    version, encoded, signature = token.split(".")

    import base64

    padding = "=" * ((4 - len(encoded) % 4) % 4)
    payload = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    parsed = json.loads(payload)
    duplicate_json = (
        "{"
        + f'"v":1,"v":1,"permit_id":{json.dumps(parsed["permit_id"])},'
        + f'"key_id":{json.dumps(parsed["key_id"])},'
        + f'"actor_fingerprint":{json.dumps(parsed["actor_fingerprint"])},'
        + f'"repository":{json.dumps(parsed["repository"])},'
        + f'"operations":{json.dumps(parsed["operations"])},'
        + f'"resource_scopes":{json.dumps(parsed["resource_scopes"])},'
        + f'"issued_at":{json.dumps(parsed["issued_at"])},'
        + f'"expires_at":{json.dumps(parsed["expires_at"])},'
        + f'"max_uses":{json.dumps(parsed["max_uses"])},'
        + f'"generation":{json.dumps(parsed["generation"])}'
        + "}"
    )
    forged_encoded = base64.urlsafe_b64encode(
        duplicate_json.encode("utf-8")
    ).decode("ascii").rstrip("=")
    forged_signature = __import__("hmac").new(
        KEY.secret,
        f"v1.{forged_encoded}".encode("ascii"),
        __import__("hashlib").sha256,
    ).hexdigest()

    with pytest.raises(AutomationControlError, match="duplicate permit field"):
        permit_authority.verify(
            f"{version}.{forged_encoded}.{forged_signature}",
            actor=principal,
            now=clock(),
        )


def test_permit_use_ledger_never_resurrects_exhausted_permit_after_eviction() -> None:
    clock = Clock()
    principal = actor()
    ledger = PermitUseLedger(max_entries=1)
    first_claims = claims(clock, principal, permit_id="permit-exhaust", max_uses=1)
    first_request = request(
        clock,
        principal,
        request_id="request-exhaust",
        nonce="nonce-exhaust1",
    )
    assert ledger.consume(first_claims, first_request)

    other_claims = claims(clock, principal, permit_id="permit-other01", max_uses=1)
    other_request = request(
        clock,
        principal,
        request_id="request-other01",
        nonce="nonce-other001",
    )
    assert ledger.consume(other_claims, other_request)

    fresh_request = request(
        clock,
        principal,
        request_id="request-exhaust2",
        nonce="nonce-exhaust2",
    )
    assert not ledger.consume(first_claims, fresh_request)
    assert ledger.uses("permit-exhaust") == 1


def test_mutation_budget_reports_exact_risk_count() -> None:
    principal = actor()
    budget = MutationBudget(AutomationPolicy(max_mutations_per_run=2))

    assert budget.count(principal, OperationRisk.MUTATION) == 0
    assert budget.consume(principal, OperationRisk.MUTATION)
    assert budget.count(principal, OperationRisk.MUTATION) == 1
    assert budget.consume(principal, OperationRisk.MUTATION)
    assert not budget.consume(principal, OperationRisk.MUTATION)


@pytest.mark.parametrize(
    ("operation", "risk"),
    [
        (AutomationOperation.OBSERVE, OperationRisk.READ_ONLY),
        (AutomationOperation.COMMENT, OperationRisk.MUTATION),
        (AutomationOperation.MERGE_PULL_REQUEST, OperationRisk.PRIVILEGED),
        (AutomationOperation.RELEASE, OperationRisk.DESTRUCTIVE),
    ],
)
def test_operation_risk_classification_is_closed(
    operation: AutomationOperation,
    risk: OperationRisk,
) -> None:
    clock = Clock()
    item = request(
        clock,
        actor(),
        operation=operation,
        resource="resource:test",
    )
    assert item.risk is risk
