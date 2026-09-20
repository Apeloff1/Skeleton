"""Compatibility adapters for moving automation messages to canonical envelopes.

The adapter layer keeps legacy orchestration payloads outside the shared
contract boundary while preserving identity and evidence needed for validation.
"""

from __future__ import annotations

from typing import Any

from .canonical import CanonicalEnvelope, EvidenceRef, Identity


class DelegationAdapterError(ValueError):
    """Raised when a delegation payload cannot become canonical."""


def delegation_to_canonical(
    delegation: dict[str, Any],
) -> CanonicalEnvelope:
    """Convert a legacy delegation payload into a bounded canonical envelope.

    The resulting envelope carries intent and evidence only. It does not grant
    execution authority.
    """

    repository = str(delegation.get("repository", ""))
    commit_sha = str(delegation.get("commit_sha", ""))
    plan = delegation.get("plan")

    if not repository or not commit_sha:
        raise DelegationAdapterError("missing repository identity")
    if plan is None:
        raise DelegationAdapterError("missing delegation plan")

    evidence_digest = str(
        delegation.get("snapshot_fingerprint", "")
    )

    evidence = ()
    if evidence_digest:
        evidence = (
            EvidenceRef(
                source="supervisor_snapshot",
                digest=evidence_digest,
                category="repository_state",
            ),
        )

    return CanonicalEnvelope(
        schema_version=1,
        kind="delegation",
        identity=Identity(
            repository=repository,
            commit_sha=commit_sha,
            run_id=str(delegation.get("run_id", "")),
            run_attempt=str(delegation.get("run_attempt", "")),
        ),
        evidence=evidence,
        constraints=(
            "planning_only",
            "secretary_admission_required",
        ),
        payload={"plan": plan},
    )
