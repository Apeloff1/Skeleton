from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from skeleton.shells.isolation import (
    IsolationLevel,
    IsolationObservation,
    IsolationRequirement,
)
from skeleton.skills.privileged_transaction import (
    PrivilegedToolTransactionError,
    qualify_privileged_tool_transaction,
)
from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolRiskClass,
    ToolSideEffectClass,
    approval_ref_for_request,
)


NOW = datetime(2026, 9, 28, 0, 10, tzinfo=timezone.utc)


def _uuid(seed: int) -> str:
    return str(UUID(int=seed))


def _manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="bounded repository write",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        capabilities=("repo:write",),
        authority_class=ToolAuthorityClass.PRIVILEGED,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        approval_policy=ToolApprovalPolicy.ALWAYS,
        network_policy="none",
        data_policy="internal",
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
        timeout_seconds=30.0,
    )


def _request(*, approval: str | None = None) -> ToolExecutionRequest:
    base = ToolExecutionRequest(
        request_id=_uuid(1),
        operation_id=_uuid(2),
        execution_id="exec-1",
        turn_id="turn-1",
        call_id="call-1",
        tenant_id="tenant-a",
        tool_id="repo.write",
        idempotency_key="idem-1",
        arguments={"path": "docs/result.txt"},
        requested_at=NOW,
        approval_ref=approval,
        delegated_authority_ref="delegation:bounded",
    )
    if approval is not None:
        return base
    return replace(base, approval_ref=approval_ref_for_request(base))


def _receipt(
    request: ToolExecutionRequest,
    **overrides: object,
) -> ToolExecutionReceipt:
    values: dict[str, object] = {
        "receipt_id": _uuid(3),
        "request_id": request.request_id,
        "operation_id": request.operation_id,
        "execution_id": request.execution_id,
        "turn_id": request.turn_id,
        "call_id": request.call_id,
        "tenant_id": request.tenant_id,
        "tool_id": request.tool_id,
        "idempotency_key": request.idempotency_key,
        "arguments_digest": request.arguments_digest,
        "status": ToolExecutionStatus.SUCCEEDED,
        "started_at": NOW,
        "finished_at": NOW,
        "result_ref": "artifact://result/1",
        "approval_ref": request.approval_ref,
        "data_class": request.data_class,
        "transfer_purpose": request.transfer_purpose,
        "governance_decision_ref": "governance:allow:1",
        "postcondition_verified": True,
        "metered_tool_calls": 1,
    }
    values.update(overrides)
    return ToolExecutionReceipt(**values)


def _requirement() -> IsolationRequirement:
    return IsolationRequirement(
        level=IsolationLevel.SANDBOXED,
        require_private_tmp=True,
        require_clean_environment=True,
        require_readonly_source=True,
        allow_network=False,
        allow_home=False,
        allowed_write_roots=("/tmp/skeleton-output",),
    )


def _observation() -> IsolationObservation:
    return IsolationObservation(
        private_tmp=True,
        clean_environment=True,
        readonly_source=True,
        network_enabled=False,
        home_visible=False,
        write_roots=("/tmp/skeleton-output",),
    )


def _decision(
    *,
    manifest: ToolManifest | None = None,
    request: ToolExecutionRequest | None = None,
    receipt: ToolExecutionReceipt | None = None,
    requirement: IsolationRequirement | None = None,
    observation: IsolationObservation | None = None,
    persisted: bool = True,
):
    req = request or _request()
    return qualify_privileged_tool_transaction(
        manifest=manifest or _manifest(),
        request=req,
        receipt=receipt or _receipt(req),
        isolation_requirement=requirement or _requirement(),
        isolation_observation=observation or _observation(),
        receipt_persisted=persisted,
    )


def test_privileged_transaction_accepts_complete_canonical_evidence() -> None:
    decision = _decision()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.decision_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "privileged_tool_transaction"
    assert evidence.digest == decision.decision_digest


@pytest.mark.parametrize(
    ("mutator", "reason"),
    (
        (
            lambda request, receipt: (
                request,
                replace(receipt, governance_decision_ref=None),
            ),
            "governance-decision-missing",
        ),
        (
            lambda request, receipt: (
                request,
                replace(receipt, postcondition_verified=False),
            ),
            "postcondition-not-verified",
        ),
        (
            lambda request, receipt: (
                request,
                replace(receipt, metered_tool_calls=0),
            ),
            "admission-metering-invalid",
        ),
        (
            lambda request, receipt: (
                request,
                replace(receipt, status=ToolExecutionStatus.FAILED, result_ref=None, error_code="boom"),
            ),
            "execution-not-successful",
        ),
        (
            lambda request, receipt: (
                request,
                replace(receipt, tenant_id="tenant-b"),
            ),
            "request-receipt-tenant_id-mismatch",
        ),
        (
            lambda request, receipt: (
                request,
                replace(receipt, arguments_digest="f" * 64),
            ),
            "request-receipt-arguments_digest-mismatch",
        ),
    ),
)
def test_privileged_transaction_fails_closed_on_runtime_evidence_drift(
    mutator,
    reason: str,
) -> None:
    request = _request()
    request, receipt = mutator(request, _receipt(request))

    decision = _decision(request=request, receipt=receipt)

    assert decision.accepted is False
    assert reason in decision.reasons
    with pytest.raises(PrivilegedToolTransactionError):
        decision.accepted_evidence_ref()


def test_privileged_transaction_requires_durable_receipt() -> None:
    decision = _decision(persisted=False)

    assert decision.accepted is False
    assert "durable-receipt-missing" in decision.reasons


def test_privileged_transaction_requires_sandboxed_level() -> None:
    decision = _decision(
        requirement=IsolationRequirement(
            level=IsolationLevel.WORKSPACE,
            require_private_tmp=True,
            require_clean_environment=True,
            require_readonly_source=True,
            allow_network=False,
            allow_home=False,
            allowed_write_roots=("/tmp/skeleton-output",),
        )
    )

    assert decision.accepted is False
    assert "privileged-transaction-requires-sandboxed-level" in decision.reasons


def test_privileged_transaction_rejects_observed_sandbox_escape() -> None:
    decision = _decision(
        observation=IsolationObservation(
            private_tmp=False,
            clean_environment=True,
            readonly_source=True,
            network_enabled=True,
            home_visible=True,
            write_roots=("/tmp/escape",),
        )
    )

    assert decision.accepted is False
    assert any(reason.startswith("sandbox:") for reason in decision.reasons)
    assert "network-policy-bypass" in decision.reasons


def test_privileged_transaction_binds_approval_to_exact_request() -> None:
    request = _request(approval="approval:wrong")
    receipt = _receipt(request)

    decision = _decision(request=request, receipt=receipt)

    assert decision.accepted is False
    assert "approval-request-binding-mismatch" in decision.reasons


def test_privileged_transaction_detects_receipt_approval_drift() -> None:
    request = _request()
    receipt = replace(_receipt(request), approval_ref="approval:other")

    decision = _decision(request=request, receipt=receipt)

    assert decision.accepted is False
    assert "approval-receipt-binding-mismatch" in decision.reasons


def test_manifest_digest_changes_when_authority_contract_changes() -> None:
    baseline = _decision()
    changed = _decision(
        manifest=replace(
            _manifest(),
            network_policy="restricted",
        )
    )

    assert baseline.manifest_digest != changed.manifest_digest
    assert baseline.decision_digest != changed.decision_digest


def test_isolation_observation_is_part_of_decision_identity() -> None:
    baseline = _decision()
    changed = _decision(
        observation=replace(
            _observation(),
            write_roots=("/tmp/skeleton-output/subdir",),
        )
    )

    assert changed.accepted is True
    assert baseline.isolation_observation_digest != changed.isolation_observation_digest
    assert baseline.decision_digest != changed.decision_digest
