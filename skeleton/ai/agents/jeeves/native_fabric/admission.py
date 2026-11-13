"""Deterministic source-only admission decision synthesis for a native AI run.

The final execution permission is held by the existing source-verified model
installer and native execution spine. This layer combines independent host
proof, resource, telemetry and context receipts, refusing partial success.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .budgets import BudgetLedger, ResourceBudget
from .context import ContextEnvelope
from .contracts import (
    ContractHold, Proof, Scope, Verdict, exact_integer, fingerprint,
    identifier, require_same_scope,
)
from .health import HealthAssessment


@dataclass(frozen=True, slots=True)
class AdmissionInputs:
    request_id: str
    scope: Scope
    approved_proof: Proof
    context: ContextEnvelope
    health: HealthAssessment
    resources: ResourceBudget
    current_epoch: int
    already_pending: bool
    exact_native_token_check: bool
    source_verified: bool
    rights_approved: bool

    def __post_init__(self):
        identifier(self.request_id, "request")
        if not isinstance(self.scope, Scope):
            raise ContractHold("admission scope not typed")
        if not isinstance(self.approved_proof, Proof):
            raise ContractHold("typed approval proof required")
        if not isinstance(self.context, ContextEnvelope):
            raise ContractHold("actual context receipt required")
        if not isinstance(self.health, HealthAssessment):
            raise ContractHold("typed health state required")
        if not isinstance(self.resources, ResourceBudget):
            raise ContractHold("typed admitted reservation required")
        exact_integer(self.current_epoch, maximum=4102444800)
        for value in (
            self.already_pending, self.exact_native_token_check,
            self.source_verified, self.rights_approved,
        ):
            if type(value) is not bool:
                raise ContractHold("strict observed approval booleans required")


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    request_id: str
    scope_sha256: str
    approved: bool
    checks: tuple[str, ...]
    holds: tuple[str, ...]
    reservation_id: str | None

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.admission_decision.v1",
            "request_id": self.request_id, "scope_sha256": self.scope_sha256,
            "approved_for_additional_native_admission": self.approved,
            "checks": list(self.checks), "holds": list(self.holds),
            "reservation_id": self.reservation_id,
            "physical_device_qualified": False,
            "source_rights_independently_verified_here": False,
            "release_certified": False,
        }


def preflight(inputs: AdmissionInputs) -> AdmissionDecision:
    if not isinstance(inputs, AdmissionInputs):
        raise ContractHold("typed admission inputs required")
    checks, holds = [], []
    if inputs.approved_proof.scope == inputs.scope:
        v = inputs.approved_proof.valid_at(
            inputs.current_epoch, scope=inputs.scope,
        )
        if v.accepted:
            checks.append("operator_proof")
        else:
            holds.append(v.code)
    else:
        holds.append("principal_mismatch")
    if inputs.context.scope_sha256 == inputs.scope.binding:
        checks.append("scope_bound_context")
    else:
        holds.append("cross_scope_context")
    if inputs.context.has_loss:
        holds.append("context_omission")
    else:
        checks.append("all_context_retained")
    if inputs.health.can_activate:
        checks.append("resource_telemetry")
    else:
        holds.append("device_telemetry")
    if inputs.resources.empty:
        holds.append("empty_resource_reservation")
    else:
        checks.append("bounded_reservation")
    if inputs.already_pending:
        holds.append("uncertain_previous_inference")
    else:
        checks.append("no_unresolved_inference")
    if not inputs.exact_native_token_check:
        holds.append("native_tokenizer_unverified")
    else:
        checks.append("native_tokenizer_exact")
    if not inputs.source_verified:
        holds.append("model_source_unverified")
    else:
        checks.append("installed_model_source")
    if not inputs.rights_approved:
        holds.append("model_rights_unapproved")
    else:
        checks.append("model_rights_source_receipt")
    return AdmissionDecision(
        request_id=inputs.request_id,
        scope_sha256=inputs.scope.binding,
        approved=not holds,
        checks=tuple(checks), holds=tuple(holds),
        reservation_id=None,
    )


def reserve_after_preflight(
    decision: AdmissionDecision, *,
    ledger: BudgetLedger,
    budget: ResourceBudget,
    timeout_ms: int,
) -> AdmissionDecision:
    if not isinstance(decision, AdmissionDecision):
        raise ContractHold("typed preflight decision required")
    if not isinstance(ledger, BudgetLedger):
        raise ContractHold("resource ledger required")
    exact_integer(timeout_ms, minimum=1, maximum=600000)
    if not decision.approved or decision.holds:
        raise ContractHold("cannot reserve blocked native work")
    if decision.reservation_id is not None:
        raise ContractHold("admission already reserved; no duplicate")
    ticket = ledger.reserve(
        reservation_id=decision.request_id,
        scope_sha256=decision.scope_sha256,
        requested=budget,
        deadline_ms=timeout_ms,
    )
    return AdmissionDecision(
        request_id=decision.request_id,
        scope_sha256=decision.scope_sha256,
        approved=True,
        checks=(*decision.checks, "budget_reserved"),
        holds=(), reservation_id=ticket.reservation_id,
    )


__all__ = ["AdmissionInputs", "AdmissionDecision",
           "preflight", "reserve_after_preflight"]
