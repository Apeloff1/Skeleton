"""Digest-bound human approval checkpoints for autonomous creator actions (#807 B017).

This module is a policy/evidence contract, not an identity provider or execution
engine. High-impact action kinds are fixed by the contract and cannot be
caller-downgraded. Checkpoints bind the exact B013 work lease, proposed action
payload, requester, review evidence, and caller-supplied logical time.

Adapters are responsible for authenticating the recorded human identity. This
boundary records that identity and independently prevents requester self-
approval, stale lease reuse, payload substitution, expired decisions, and
approval reuse after lease renewal/reassignment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final, NoReturn

from skeleton.forge.creator.work_leases import (
    LeaseState,
    WorkLease,
    serialize_lease_state,
    sweep_expired_leases,
)
from skeleton.kernel.errors import SkeletonError
from skeleton.repo_intelligence.batch_plan import BatchPlan


APPROVAL_SCHEMA: Final = "creator.approval_boundary.v1"
APPROVAL_VERSION: Final = 1
MAX_CHECKPOINT_TTL_SECONDS: Final = 24 * 60 * 60
MAX_EVIDENCE_DIGESTS: Final = 256
MAX_RATIONALE_CHARS: Final = 4_096
MAX_ID_CHARS: Final = 128

HIGH_IMPACT_ACTIONS: Final = frozenset(
    {
        "publish_release",
        "deploy_external",
        "delete_persistent_state",
        "change_permissions",
        "use_credentials",
        "modify_security_policy",
        "merge_protected_branch",
        "external_side_effect",
    }
)
ROUTINE_ACTIONS: Final = frozenset(
    {
        "edit_draft",
        "preview",
        "run_tests",
        "export_preview",
    }
)
ACTION_KINDS: Final = HIGH_IMPACT_ACTIONS | ROUTINE_ACTIONS
DECISIONS: Final = frozenset({"approve", "deny"})

_ID_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class ApprovalBoundaryError(SkeletonError):
    """Approval checkpoint, decision, or authorization is invalid."""

    code = "CRE.APPROVAL_BOUNDARY"
    http_status = 409


@dataclass(frozen=True, slots=True)
class ApprovalCheckpoint:
    checkpoint_id: str
    action_id: str
    action_kind: str
    payload_digest: str
    requester_id: str
    lease_id: str
    lease_revision: int
    lease_digest: str
    batch_ids: tuple[str, ...]
    paths: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    requested_at: int
    expires_at: int
    requires_human: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": APPROVAL_SCHEMA,
            "schema_version": APPROVAL_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "payload_digest": self.payload_digest,
            "requester_id": self.requester_id,
            "lease_id": self.lease_id,
            "lease_revision": self.lease_revision,
            "lease_digest": self.lease_digest,
            "batch_ids": list(self.batch_ids),
            "paths": list(self.paths),
            "evidence_digests": list(self.evidence_digests),
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "requires_human": self.requires_human,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    checkpoint_digest: str
    approver_id: str
    approver_type: str
    decision: str
    decided_at: int
    evidence_digests: tuple[str, ...]
    rationale: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": APPROVAL_SCHEMA,
            "schema_version": APPROVAL_VERSION,
            "checkpoint_digest": self.checkpoint_digest,
            "approver_id": self.approver_id,
            "approver_type": self.approver_type,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "evidence_digests": list(self.evidence_digests),
            "rationale": self.rationale,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ApprovalAuthorization:
    checkpoint_digest: str
    decision_digest: str | None
    lease_digest: str
    payload_digest: str
    authorized_at: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": APPROVAL_SCHEMA,
            "schema_version": APPROVAL_VERSION,
            "checkpoint_digest": self.checkpoint_digest,
            "decision_digest": self.decision_digest,
            "lease_digest": self.lease_digest,
            "payload_digest": self.payload_digest,
            "authorized_at": self.authorized_at,
            "digest": self.digest,
        }


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise ApprovalBoundaryError(message, context={"reason": reason, **context})


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer", reason="malformed", field=name)
    if not minimum <= value <= maximum:
        _fail(
            f"{name} is outside the accepted range",
            reason="bound",
            field=name,
            minimum=minimum,
            maximum=maximum,
        )
    return value


def _id(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_ID_CHARS
        or _ID_RE.fullmatch(value) is None
    ):
        _fail(f"{name} is not a canonical identifier", reason="malformed", field=name)
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{name} must be a lowercase sha256 digest", reason="malformed", field=name)
    return value


def _evidence(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail(f"{field} must be an iterable of digests", reason="malformed", field=field)
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values, start=1):
        if index > MAX_EVIDENCE_DIGESTS:
            _fail(
                f"{field} exceeds evidence bound",
                reason="bound",
                maximum=MAX_EVIDENCE_DIGESTS,
            )
        digest = _sha256(field, value)
        if digest in seen:
            _fail(f"{field} contains duplicate evidence", reason="duplicate", digest=digest)
        seen.add(digest)
        result.append(digest)
    return tuple(sorted(result))


def _rationale(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("rationale must be non-empty canonical text", reason="malformed", field="rationale")
    if len(value) > MAX_RATIONALE_CHARS or any(
        ord(character) < 32 and character not in "\t" for character in value
    ):
        _fail("rationale exceeds bounds or contains controls", reason="malformed", field="rationale")
    return value


def approval_required(action_kind: str) -> bool:
    """Return the contract-defined approval requirement for an action kind."""
    if not isinstance(action_kind, str) or action_kind not in ACTION_KINDS:
        _fail("unknown creator action kind", reason="unknown_action_kind", action_kind=action_kind)
    return action_kind in HIGH_IMPACT_ACTIONS


def _active_lease(
    state: LeaseState,
    *,
    lease_id: str,
    requester_id: str,
    now: int,
    plan: BatchPlan | None,
) -> WorkLease:
    # Serialization is a public B013 full-state integrity check.
    serialize_lease_state(state, plan=plan)
    sweep = sweep_expired_leases(state, now=now, plan=plan)
    lease = next(
        (candidate for candidate in sweep.state.leases if candidate.lease_id == lease_id),
        None,
    )
    if lease is None:
        _fail("approval requires a live work lease", reason="lease_unavailable", lease_id=lease_id)
    if lease.owner_id != requester_id:
        _fail(
            "requester does not own the work lease",
            reason="lease_owner_mismatch",
            lease_id=lease_id,
        )
    return lease


def _checkpoint_payload(
    *,
    checkpoint_id: str,
    action_id: str,
    action_kind: str,
    payload_digest: str,
    requester_id: str,
    lease: WorkLease,
    evidence_digests: tuple[str, ...],
    requested_at: int,
    expires_at: int,
    requires_human: bool,
) -> dict[str, object]:
    return {
        "schema": APPROVAL_SCHEMA,
        "schema_version": APPROVAL_VERSION,
        "checkpoint_id": checkpoint_id,
        "action_id": action_id,
        "action_kind": action_kind,
        "payload_digest": payload_digest,
        "requester_id": requester_id,
        "lease_id": lease.lease_id,
        "lease_revision": lease.revision,
        "lease_digest": lease.digest,
        "batch_ids": list(lease.scope.batch_ids),
        "paths": list(lease.scope.paths),
        "evidence_digests": list(evidence_digests),
        "requested_at": requested_at,
        "expires_at": expires_at,
        "requires_human": requires_human,
    }


def create_approval_checkpoint(
    state: LeaseState,
    *,
    lease_id: str,
    requester_id: str,
    action_id: str,
    action_kind: str,
    payload_digest: str,
    evidence_digests: Iterable[str] = (),
    now: int,
    ttl_seconds: int,
    plan: BatchPlan | None = None,
) -> ApprovalCheckpoint:
    """Bind one proposed action to the exact active B013 lease and evidence."""

    canonical_lease_id = _id("lease_id", lease_id)
    canonical_requester = _id("requester_id", requester_id)
    canonical_action_id = _id("action_id", action_id)
    payload = _sha256("payload_digest", payload_digest)
    requires_human = approval_required(action_kind)
    evidence = _evidence(evidence_digests, field="evidence_digests")
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    ttl = _strict_int(
        "ttl_seconds",
        ttl_seconds,
        minimum=1,
        maximum=MAX_CHECKPOINT_TTL_SECONDS,
    )
    if current > 2**63 - 1 - ttl:
        _fail("checkpoint expiry would overflow logical time", reason="bound")

    lease = _active_lease(
        state,
        lease_id=canonical_lease_id,
        requester_id=canonical_requester,
        now=current,
        plan=plan,
    )
    expires_at = min(current + ttl, lease.expires_at)
    if expires_at <= current:
        _fail("approval checkpoint cannot outlive an expired lease", reason="lease_unavailable")

    checkpoint_id = _digest(
        {
            "action_id": canonical_action_id,
            "action_kind": action_kind,
            "payload_digest": payload,
            "requester_id": canonical_requester,
            "lease_digest": lease.digest,
            "requested_at": current,
        }
    )
    checkpoint_payload = _checkpoint_payload(
        checkpoint_id=checkpoint_id,
        action_id=canonical_action_id,
        action_kind=action_kind,
        payload_digest=payload,
        requester_id=canonical_requester,
        lease=lease,
        evidence_digests=evidence,
        requested_at=current,
        expires_at=expires_at,
        requires_human=requires_human,
    )
    return ApprovalCheckpoint(
        checkpoint_id=checkpoint_id,
        action_id=canonical_action_id,
        action_kind=action_kind,
        payload_digest=payload,
        requester_id=canonical_requester,
        lease_id=lease.lease_id,
        lease_revision=lease.revision,
        lease_digest=lease.digest,
        batch_ids=lease.scope.batch_ids,
        paths=lease.scope.paths,
        evidence_digests=evidence,
        requested_at=current,
        expires_at=expires_at,
        requires_human=requires_human,
        digest=_digest(checkpoint_payload),
    )


def validate_checkpoint(checkpoint: ApprovalCheckpoint) -> None:
    if not isinstance(checkpoint, ApprovalCheckpoint):
        _fail("checkpoint must be ApprovalCheckpoint", reason="malformed")
    action_kind = checkpoint.action_kind
    requires_human = approval_required(action_kind)
    if checkpoint.requires_human is not requires_human:
        _fail("checkpoint approval requirement was tampered", reason="derived_field_drift")
    _sha256("checkpoint_id", checkpoint.checkpoint_id)
    _id("action_id", checkpoint.action_id)
    _sha256("payload_digest", checkpoint.payload_digest)
    _id("requester_id", checkpoint.requester_id)
    _id("lease_id", checkpoint.lease_id)
    _strict_int("lease_revision", checkpoint.lease_revision, minimum=1, maximum=2**31 - 1)
    _sha256("lease_digest", checkpoint.lease_digest)
    evidence = _evidence(checkpoint.evidence_digests, field="evidence_digests")
    requested = _strict_int("requested_at", checkpoint.requested_at, minimum=0, maximum=2**63 - 1)
    expires = _strict_int("expires_at", checkpoint.expires_at, minimum=0, maximum=2**63 - 1)
    if expires <= requested:
        _fail("checkpoint expiry must follow request time", reason="malformed")
    derived_id = _digest(
        {
            "action_id": checkpoint.action_id,
            "action_kind": action_kind,
            "payload_digest": checkpoint.payload_digest,
            "requester_id": checkpoint.requester_id,
            "lease_digest": checkpoint.lease_digest,
            "requested_at": requested,
        }
    )
    if checkpoint.checkpoint_id != derived_id:
        _fail("checkpoint id mismatch", reason="digest_mismatch")
    pseudo_lease = type("_LeaseView", (), {})()
    pseudo_lease.lease_id = checkpoint.lease_id
    pseudo_lease.revision = checkpoint.lease_revision
    pseudo_lease.digest = checkpoint.lease_digest
    pseudo_lease.scope = type("_ScopeView", (), {
        "batch_ids": checkpoint.batch_ids,
        "paths": checkpoint.paths,
    })()
    payload = _checkpoint_payload(
        checkpoint_id=checkpoint.checkpoint_id,
        action_id=checkpoint.action_id,
        action_kind=action_kind,
        payload_digest=checkpoint.payload_digest,
        requester_id=checkpoint.requester_id,
        lease=pseudo_lease,
        evidence_digests=evidence,
        requested_at=requested,
        expires_at=expires,
        requires_human=requires_human,
    )
    if checkpoint.digest != _digest(payload):
        _fail("checkpoint digest mismatch", reason="digest_mismatch")


def _decision_payload(
    *,
    checkpoint_digest: str,
    approver_id: str,
    decision: str,
    decided_at: int,
    evidence_digests: tuple[str, ...],
    rationale: str,
) -> dict[str, object]:
    return {
        "schema": APPROVAL_SCHEMA,
        "schema_version": APPROVAL_VERSION,
        "checkpoint_digest": checkpoint_digest,
        "approver_id": approver_id,
        "approver_type": "human",
        "decision": decision,
        "decided_at": decided_at,
        "evidence_digests": list(evidence_digests),
        "rationale": rationale,
    }


def record_human_decision(
    checkpoint: ApprovalCheckpoint,
    *,
    approver_id: str,
    decision: str,
    now: int,
    evidence_digests: Iterable[str] = (),
    rationale: str,
) -> ApprovalDecision:
    """Record one separate human decision for a high-impact checkpoint."""

    validate_checkpoint(checkpoint)
    if not checkpoint.requires_human:
        _fail("routine action does not require a human decision", reason="approval_not_required")
    canonical_approver = _id("approver_id", approver_id)
    if canonical_approver == checkpoint.requester_id:
        _fail("requester cannot approve their own action", reason="self_approval")
    if decision not in DECISIONS:
        _fail("decision must be approve or deny", reason="malformed", field="decision")
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    if current < checkpoint.requested_at:
        _fail("decision cannot predate checkpoint", reason="time_regression")
    if current >= checkpoint.expires_at:
        _fail("approval checkpoint has expired", reason="checkpoint_expired")
    evidence = _evidence(evidence_digests, field="decision_evidence_digests")
    reason = _rationale(rationale)
    payload = _decision_payload(
        checkpoint_digest=checkpoint.digest,
        approver_id=canonical_approver,
        decision=decision,
        decided_at=current,
        evidence_digests=evidence,
        rationale=reason,
    )
    return ApprovalDecision(
        checkpoint_digest=checkpoint.digest,
        approver_id=canonical_approver,
        approver_type="human",
        decision=decision,
        decided_at=current,
        evidence_digests=evidence,
        rationale=reason,
        digest=_digest(payload),
    )


def validate_decision(
    decision: ApprovalDecision,
    checkpoint: ApprovalCheckpoint,
) -> None:
    validate_checkpoint(checkpoint)
    if not isinstance(decision, ApprovalDecision):
        _fail("decision must be ApprovalDecision", reason="malformed")
    if not checkpoint.requires_human:
        _fail("routine action cannot consume approval decision", reason="approval_not_required")
    if decision.checkpoint_digest != checkpoint.digest:
        _fail("decision is bound to a different checkpoint", reason="checkpoint_mismatch")
    approver = _id("approver_id", decision.approver_id)
    if decision.approver_type != "human":
        _fail("high-impact approval must record human approver type", reason="approver_type")
    if approver == checkpoint.requester_id:
        _fail("requester cannot approve their own action", reason="self_approval")
    if decision.decision not in DECISIONS:
        _fail("unsupported approval decision", reason="malformed")
    decided = _strict_int("decided_at", decision.decided_at, minimum=0, maximum=2**63 - 1)
    if decided < checkpoint.requested_at or decided >= checkpoint.expires_at:
        _fail("decision time is outside checkpoint lifetime", reason="checkpoint_expired")
    evidence = _evidence(decision.evidence_digests, field="decision_evidence_digests")
    rationale = _rationale(decision.rationale)
    payload = _decision_payload(
        checkpoint_digest=checkpoint.digest,
        approver_id=approver,
        decision=decision.decision,
        decided_at=decided,
        evidence_digests=evidence,
        rationale=rationale,
    )
    if decision.digest != _digest(payload):
        _fail("approval decision digest mismatch", reason="digest_mismatch")


def authorize_action(
    checkpoint: ApprovalCheckpoint,
    state: LeaseState,
    *,
    now: int,
    payload_digest: str,
    decision: ApprovalDecision | None = None,
    plan: BatchPlan | None = None,
) -> ApprovalAuthorization:
    """Authorize only an exact action under the still-live original lease."""

    validate_checkpoint(checkpoint)
    current = _strict_int("now", now, minimum=0, maximum=2**63 - 1)
    payload = _sha256("payload_digest", payload_digest)
    if payload != checkpoint.payload_digest:
        _fail("action payload differs from approved checkpoint", reason="payload_mismatch")
    if current < checkpoint.requested_at:
        _fail("authorization cannot predate checkpoint", reason="time_regression")
    if current >= checkpoint.expires_at:
        _fail("approval checkpoint has expired", reason="checkpoint_expired")

    lease = _active_lease(
        state,
        lease_id=checkpoint.lease_id,
        requester_id=checkpoint.requester_id,
        now=current,
        plan=plan,
    )
    if (
        lease.revision != checkpoint.lease_revision
        or lease.digest != checkpoint.lease_digest
    ):
        _fail(
            "work lease changed after approval checkpoint",
            reason="lease_changed",
            lease_id=lease.lease_id,
        )
    if (
        checkpoint.batch_ids != lease.scope.batch_ids
        or checkpoint.paths != lease.scope.paths
    ):
        _fail(
            "checkpoint scope differs from bound work lease",
            reason="lease_scope_drift",
            lease_id=lease.lease_id,
        )

    decision_digest: str | None = None
    if checkpoint.requires_human:
        if decision is None:
            _fail("high-impact action requires human approval", reason="approval_required")
        validate_decision(decision, checkpoint)
        if decision.decided_at > current:
            _fail("approval decision is from the future", reason="time_regression")
        if decision.decision != "approve":
            _fail("human decision denied the action", reason="approval_denied")
        decision_digest = decision.digest
    elif decision is not None:
        _fail("routine action must not consume unrelated approval", reason="approval_not_required")

    auth_payload = {
        "schema": APPROVAL_SCHEMA,
        "schema_version": APPROVAL_VERSION,
        "checkpoint_digest": checkpoint.digest,
        "decision_digest": decision_digest,
        "lease_digest": lease.digest,
        "payload_digest": payload,
        "authorized_at": current,
    }
    return ApprovalAuthorization(
        checkpoint_digest=checkpoint.digest,
        decision_digest=decision_digest,
        lease_digest=lease.digest,
        payload_digest=payload,
        authorized_at=current,
        digest=_digest(auth_payload),
    )


def validate_authorization(
    authorization: ApprovalAuthorization,
    checkpoint: ApprovalCheckpoint,
    state: LeaseState,
    *,
    now: int,
    payload_digest: str,
    decision: ApprovalDecision | None = None,
    plan: BatchPlan | None = None,
) -> None:
    """Recompute authorization from current lease/checkpoint/decision evidence."""
    if not isinstance(authorization, ApprovalAuthorization):
        _fail("authorization must be ApprovalAuthorization", reason="malformed")
    expected = authorize_action(
        checkpoint,
        state,
        now=now,
        payload_digest=payload_digest,
        decision=decision,
        plan=plan,
    )
    if authorization != expected:
        _fail("authorization derived identity mismatch", reason="digest_mismatch")


def serialize_checkpoint(checkpoint: ApprovalCheckpoint) -> str:
    validate_checkpoint(checkpoint)
    return _canonical_json(checkpoint.to_dict()).decode("ascii")


def serialize_decision(
    decision: ApprovalDecision,
    checkpoint: ApprovalCheckpoint,
) -> str:
    validate_decision(decision, checkpoint)
    return _canonical_json(decision.to_dict()).decode("ascii")


__all__ = [
    "ACTION_KINDS",
    "APPROVAL_SCHEMA",
    "APPROVAL_VERSION",
    "ApprovalAuthorization",
    "ApprovalBoundaryError",
    "ApprovalCheckpoint",
    "ApprovalDecision",
    "DECISIONS",
    "HIGH_IMPACT_ACTIONS",
    "MAX_CHECKPOINT_TTL_SECONDS",
    "MAX_EVIDENCE_DIGESTS",
    "ROUTINE_ACTIONS",
    "approval_required",
    "authorize_action",
    "create_approval_checkpoint",
    "record_human_decision",
    "serialize_checkpoint",
    "serialize_decision",
    "validate_authorization",
    "validate_checkpoint",
    "validate_decision",
]
