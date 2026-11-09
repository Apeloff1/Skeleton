"""Admission validation for canonical automation envelopes.

This module keeps Secretary-style admission checks separate from execution.
It validates identity, evidence, and allowed envelope transitions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import CanonicalContractError, CanonicalEnvelope


ALLOWED_INPUT_KINDS = frozenset({"delegation"})
OUTPUT_KIND = "admission"


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    accepted: bool
    envelope: CanonicalEnvelope | None = None
    reason: str = ""


def validate_delegation(
    envelope: CanonicalEnvelope,
    *,
    repository: str,
    commit_sha: str,
) -> AdmissionResult:
    """Validate a Supervisor delegation before queue admission."""

    try:
        payload = envelope.canonical_payload()
    except CanonicalContractError as exc:
        return AdmissionResult(False, reason=str(exc))

    if envelope.kind not in ALLOWED_INPUT_KINDS:
        return AdmissionResult(False, reason="unsupported input kind")

    if envelope.identity.repository != repository:
        return AdmissionResult(False, reason="repository identity mismatch")

    if envelope.identity.commit_sha != commit_sha:
        return AdmissionResult(False, reason="commit identity mismatch")

    if not envelope.evidence:
        return AdmissionResult(False, reason="missing evidence")

    admitted = CanonicalEnvelope(
        schema_version=envelope.schema_version,
        kind=OUTPUT_KIND,
        identity=envelope.identity,
        evidence=envelope.evidence,
        constraints=tuple(sorted(set(envelope.constraints + ("worker_scope_required",)))),
        payload={"delegation": payload["payload"]},
    )

    return AdmissionResult(True, admitted)
