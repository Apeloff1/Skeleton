"""Stateful admission and authorization guard for AI execution authority.

The guard is intentionally separate from the immutable contract module.  It
owns bounded replay memory, revocation state, and monotonic usage ledgers.  It
does not execute tools; callers must receive an ALLOW decision before invoking
any side-effecting adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
import hashlib
import re
from threading import RLock
from typing import Any, Callable, ParamSpec, TypeVar

from skeleton.ai.runtime.contracts.ai_execution import AIExecutionRequest
from skeleton.ai.runtime.contracts.canonical import canonical_json_bytes
from skeleton.ai.runtime.contracts.execution_authority import (
    AdmissionReceipt,
    AuthorityConsumptionReceipt,
    AuthorityEvidenceBundle,
    AuthorityRevocationReceipt,
    AuthorityStateCheckpoint,
    ExecutionAuthority,
    ExecutionAuthorityError,
    ResourceUsage,
    validate_authority_attenuation,
)


_REPLAY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _synchronized(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Serialize guard operations so budget and receipt updates are atomic."""

    @wraps(method)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        if not args:
            raise RuntimeError("synchronized guard method requires self")
        guard = args[0]
        lock = getattr(guard, "_lock", None)
        if lock is None:
            raise RuntimeError("execution authority guard lock is unavailable")
        with lock:
            return method(*args, **kwargs)

    return wrapped


MAX_AUTHORITY_DELEGATION_DEPTH = 32
MAX_GUARD_AUTHORITIES = 4096
MAX_GUARD_REPLAY_KEYS = 16384


class AuthorizationDisposition(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    disposition: AuthorizationDisposition
    reason: str
    authority_digest: str
    usage: ResourceUsage
    replay_key: str = ""
    receipt: AuthorityConsumptionReceipt | None = None

    @property
    def allowed(self) -> bool:
        return self.disposition is AuthorizationDisposition.ALLOW


@dataclass(slots=True)
class _AuthorityState:
    authority: ExecutionAuthority
    usage: ResourceUsage
    descendant_usage: ResourceUsage
    revoked: bool = False
    admission_receipt_digest: str | None = None
    consumption_count: int = 0
    latest_receipt_digest: str | None = None
    admitted_at: datetime | None = None
    last_authorized_at: datetime | None = None
    revocation_receipt: AuthorityRevocationReceipt | None = None


class ExecutionAuthorityGuard:
    """Bounded fail-closed authority state for one runtime process."""

    def __init__(
        self,
        *,
        max_authorities: int = MAX_GUARD_AUTHORITIES,
        max_replay_keys: int = MAX_GUARD_REPLAY_KEYS,
    ) -> None:
        for name, value in (
            ("max_authorities", max_authorities),
            ("max_replay_keys", max_replay_keys),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.max_authorities = max_authorities
        self.max_replay_keys = max_replay_keys
        self._lock = RLock()
        self._authorities: dict[str, _AuthorityState] = {}
        self._authority_order: list[str] = []
        self._replay_digests: dict[str, str] = {}
        self._replay_order: list[str] = []
        self._admission_receipts: dict[str, AdmissionReceipt] = {}
        self._authorization_receipts: dict[str, AuthorityConsumptionReceipt] = {}

    @staticmethod
    def _aware(now: datetime | None) -> datetime:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExecutionAuthorityError("now must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_replay_key(replay_key: str) -> str:
        if not isinstance(replay_key, str) or _REPLAY_KEY.fullmatch(replay_key) is None:
            raise ExecutionAuthorityError("invalid replay_key")
        return replay_key

    @staticmethod
    def _admission_replay_payload_digest(
        *,
        authority_digest: str,
        request_identity_digest: str,
        operation_id: str,
        execution_id: str,
    ) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "authority_digest": authority_digest,
                    "request_identity_digest": request_identity_digest,
                    "operation_id": operation_id,
                    "execution_id": execution_id,
                }
            )
        ).hexdigest()

    @staticmethod
    def _replay_payload_digest(
        *,
        authority_digest: str,
        capability: str,
        delta: ResourceUsage,
    ) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "authority_digest": authority_digest,
                    "capability": capability,
                    "delta": delta.as_dict(),
                }
            )
        ).hexdigest()

    def _remember_replay(self, replay_key: str, digest: str) -> None:
        if replay_key in self._replay_digests:
            return
        if len(self._replay_order) >= self.max_replay_keys:
            raise ExecutionAuthorityError(
                "replay guard capacity exhausted; refusing to forget replay state"
            )
        self._replay_digests[replay_key] = digest
        self._replay_order.append(replay_key)

    def _lineage_error(
        self,
        state: _AuthorityState,
        *,
        now: datetime,
    ) -> str | None:
        current = state
        visited = {current.authority.digest}
        depth = 0
        while current.authority.parent_authority_digest is not None:
            depth += 1
            if depth > MAX_AUTHORITY_DELEGATION_DEPTH:
                return "authority lineage exceeds maximum depth"
            parent_digest = current.authority.parent_authority_digest
            if parent_digest in visited:
                return "authority lineage contains a cycle"
            visited.add(parent_digest)
            parent = self._authorities.get(parent_digest)
            if parent is None:
                return "ancestor authority is unavailable"
            if parent.revoked:
                return "ancestor authority is revoked"
            if parent.authority.expired(now=now):
                return "ancestor authority is expired"
            try:
                validate_authority_attenuation(parent.authority, current.authority)
            except ExecutionAuthorityError:
                return "authority lineage attenuation is invalid"
            current = parent
        return None

    def _ancestor_states(self, state: _AuthorityState) -> tuple[_AuthorityState, ...]:
        """Return nearest-parent-first lineage after _lineage_error validation."""

        ancestors: list[_AuthorityState] = []
        current = state
        while current.authority.parent_authority_digest is not None:
            parent = self._authorities.get(current.authority.parent_authority_digest)
            if parent is None:
                raise ExecutionAuthorityError("ancestor authority is unavailable")
            ancestors.append(parent)
            current = parent
        return tuple(ancestors)

    @staticmethod
    def _aggregate_usage(state: _AuthorityState) -> ResourceUsage:
        return state.usage.add(state.descendant_usage)

    def _remember_authority(self, authority: ExecutionAuthority) -> _AuthorityState:
        digest = authority.digest
        existing = self._authorities.get(digest)
        if existing is not None:
            if existing.authority != authority:
                raise ExecutionAuthorityError(
                    "authority digest collision with different contract"
                )
            return existing
        if len(self._authority_order) >= self.max_authorities:
            raise ExecutionAuthorityError(
                "authority guard capacity exhausted; refusing to forget usage state"
            )
        state = _AuthorityState(
            authority=authority,
            usage=ResourceUsage(),
            descendant_usage=ResourceUsage(),
        )
        self._authorities[digest] = state
        self._authority_order.append(digest)
        return state

    @_synchronized
    def admit(
        self,
        *,
        authority: ExecutionAuthority,
        request: AIExecutionRequest,
        receipt_id: str,
        replay_key: str,
        now: datetime | None = None,
    ) -> AdmissionReceipt:
        """Bind one execution request to an authority and return durable evidence."""

        instant = self._aware(now)
        replay_key = self._validate_replay_key(replay_key)
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        if not isinstance(request, AIExecutionRequest):
            raise ExecutionAuthorityError("request must be AIExecutionRequest")
        if instant < authority.issued_at:
            raise ExecutionAuthorityError("authority is not active yet")
        if authority.expired(now=instant):
            raise ExecutionAuthorityError("authority is expired")
        if request.operation_id != authority.operation_id:
            raise ExecutionAuthorityError("operation identity mismatch")
        if request.execution_id != authority.execution_id:
            raise ExecutionAuthorityError("execution identity mismatch")

        if authority.parent_authority_digest is not None:
            parent_state = self._authorities.get(authority.parent_authority_digest)
            if parent_state is None:
                raise ExecutionAuthorityError("parent authority has not been admitted")
            if parent_state.revoked:
                raise ExecutionAuthorityError("parent authority is revoked")
            if parent_state.authority.expired(now=instant):
                raise ExecutionAuthorityError("parent authority is expired")
            lineage_error = self._lineage_error(parent_state, now=instant)
            if lineage_error is not None:
                raise ExecutionAuthorityError(lineage_error)
            validate_authority_attenuation(parent_state.authority, authority)

        state = self._remember_authority(authority)
        if state.revoked:
            raise ExecutionAuthorityError("authority is revoked")

        admission_replay_digest = self._admission_replay_payload_digest(
            authority_digest=authority.digest,
            request_identity_digest=request.identity_digest,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
        )

        prior = self._replay_digests.get(replay_key)
        if prior is not None:
            if prior != admission_replay_digest:
                raise ExecutionAuthorityError("replay_key reused for different admission")
            existing_receipt = self._admission_receipts.get(replay_key)
            if existing_receipt is None:
                raise ExecutionAuthorityError("admission replay state is inconsistent")
            return existing_receipt

        receipt = AdmissionReceipt(
            receipt_id=receipt_id,
            authority_digest=authority.digest,
            request_identity_digest=request.identity_digest,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            admitted_at=instant,
            expires_at=authority.expires_at,
            replay_key=replay_key,
        )
        self._remember_replay(replay_key, admission_replay_digest)
        self._admission_receipts[replay_key] = receipt
        if state.admission_receipt_digest is None:
            state.admission_receipt_digest = receipt.digest
            state.admitted_at = instant
        return receipt

    @_synchronized
    def authorize(
        self,
        *,
        authority: ExecutionAuthority,
        capability: str,
        delta: ResourceUsage | None = None,
        replay_key: str,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Atomically authorize one accounted capability use.

        A repeated replay_key with identical content returns REPLAY and does not
        consume budget twice. Reusing the key with changed content fails closed.
        """

        instant = self._aware(now)
        replay_key = self._validate_replay_key(replay_key)
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        usage_delta = delta or ResourceUsage()
        if not isinstance(usage_delta, ResourceUsage):
            raise ExecutionAuthorityError("delta must be ResourceUsage")

        state = self._authorities.get(authority.digest)
        if state is None:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authority has not been admitted",
                authority.digest,
                ResourceUsage(),
                replay_key,
            )
        if state.authority != authority:
            raise ExecutionAuthorityError("admitted authority content mismatch")
        if state.admitted_at is not None and instant < state.admitted_at:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authorization time predates admission",
                authority.digest,
                state.usage,
                replay_key,
            )
        if state.last_authorized_at is not None and instant < state.last_authorized_at:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authorization time regressed",
                authority.digest,
                state.usage,
                replay_key,
            )
        if state.revoked:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authority is revoked",
                authority.digest,
                state.usage,
                replay_key,
            )
        lineage_error = self._lineage_error(state, now=instant)
        if lineage_error is not None:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                lineage_error,
                authority.digest,
                state.usage,
                replay_key,
            )
        if authority.expired(now=instant):
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authority is expired",
                authority.digest,
                state.usage,
                replay_key,
            )

        replay_digest = self._replay_payload_digest(
            authority_digest=authority.digest,
            capability=capability,
            delta=usage_delta,
        )
        prior = self._replay_digests.get(replay_key)
        if prior is not None:
            if prior != replay_digest:
                raise ExecutionAuthorityError(
                    "replay_key reused with different authorization payload"
                )
            existing_receipt = self._authorization_receipts.get(replay_key)
            if existing_receipt is None:
                raise ExecutionAuthorityError(
                    "authorization replay state is inconsistent"
                )
            return AuthorizationDecision(
                AuthorizationDisposition.REPLAY,
                "authorization replay already accounted",
                authority.digest,
                state.usage,
                replay_key,
                existing_receipt,
            )

        if not usage_delta.has_monotonic_charge:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authorization requires a non-zero metered resource charge",
                authority.digest,
                state.usage,
                replay_key,
            )

        projected = state.usage.add(usage_delta)
        aggregate_projected = self._aggregate_usage(state).add(usage_delta)
        if not authority.permits(
            capability,
            usage=aggregate_projected,
            now=instant,
        ):
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "capability or resource budget denied",
                authority.digest,
                state.usage,
                replay_key,
            )

        ancestors = self._ancestor_states(state)
        for ancestor in ancestors:
            aggregate_projected = self._aggregate_usage(ancestor).add(usage_delta)
            if not ancestor.authority.permits(
                capability,
                usage=aggregate_projected,
                now=instant,
            ):
                return AuthorizationDecision(
                    AuthorizationDisposition.DENY,
                    "ancestor capability or aggregate resource budget denied",
                    authority.digest,
                    state.usage,
                    replay_key,
                )

        receipt = AuthorityConsumptionReceipt(
            authority_digest=authority.digest,
            operation_id=authority.operation_id,
            execution_id=authority.execution_id,
            actor_id=authority.actor_id,
            capability=capability,
            sequence=state.consumption_count + 1,
            replay_key=replay_key,
            authorized_at=instant,
            delta_usage=usage_delta,
            total_usage=projected,
            previous_receipt_digest=state.latest_receipt_digest,
        )
        self._remember_replay(replay_key, replay_digest)
        self._authorization_receipts[replay_key] = receipt
        state.usage = projected
        for ancestor in ancestors:
            ancestor.descendant_usage = ancestor.descendant_usage.add(usage_delta)
        state.consumption_count = receipt.sequence
        state.latest_receipt_digest = receipt.digest
        state.last_authorized_at = instant
        return AuthorizationDecision(
            AuthorizationDisposition.ALLOW,
            "authorized",
            authority.digest,
            state.usage,
            replay_key,
            receipt,
        )

    @_synchronized
    def revoke(
        self,
        authority: ExecutionAuthority,
        *,
        revoked_by: str = "runtime",
        reason_code: str = "explicit.revocation",
        now: datetime | None = None,
    ) -> AuthorityRevocationReceipt:
        """Revoke admitted authority and return stable tamper-evident evidence."""

        instant = self._aware(now)
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        if state is None:
            raise ExecutionAuthorityError("authority has not been admitted")
        if state.authority != authority:
            raise ExecutionAuthorityError("admitted authority content mismatch")
        if state.admitted_at is not None and instant < state.admitted_at:
            raise ExecutionAuthorityError("revocation time predates admission")
        if state.last_authorized_at is not None and instant < state.last_authorized_at:
            raise ExecutionAuthorityError("revocation time predates latest consumption")
        if state.revoked:
            receipt = state.revocation_receipt
            if receipt is None:
                raise ExecutionAuthorityError("revocation evidence is inconsistent")
            if receipt.revoked_by != revoked_by or receipt.reason_code != reason_code:
                raise ExecutionAuthorityError(
                    "authority already revoked with different evidence"
                )
            return receipt

        receipt = AuthorityRevocationReceipt(
            authority_digest=authority.digest,
            operation_id=authority.operation_id,
            execution_id=authority.execution_id,
            revoked_by=revoked_by,
            reason_code=reason_code,
            revoked_at=instant,
            latest_consumption_digest=state.latest_receipt_digest,
        )
        state.revocation_receipt = receipt
        state.revoked = True
        return receipt

    @_synchronized
    def checkpoint(
        self,
        authority: ExecutionAuthority,
        *,
        now: datetime | None = None,
    ) -> AuthorityStateCheckpoint:
        """Create a restart-safe checkpoint without exposing mutable guard state."""

        instant = self._aware(now)
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        if state is None:
            raise ExecutionAuthorityError("authority has not been admitted")
        if state.authority != authority:
            raise ExecutionAuthorityError("admitted authority content mismatch")
        if state.admission_receipt_digest is None:
            raise ExecutionAuthorityError("authority admission evidence is missing")

        admission = next(
            (
                receipt
                for receipt in self._admission_receipts.values()
                if receipt.digest == state.admission_receipt_digest
            ),
            None,
        )
        if admission is None:
            raise ExecutionAuthorityError("admission receipt state is inconsistent")
        receipts = tuple(
            sorted(
                (
                    receipt
                    for receipt in self._authorization_receipts.values()
                    if receipt.authority_digest == authority.digest
                ),
                key=lambda receipt: receipt.sequence,
            )
        )
        checkpoint = AuthorityStateCheckpoint(
            authority=authority,
            admission_receipt=admission,
            consumption_receipts=receipts,
            revocation_receipt=state.revocation_receipt,
            created_at=instant,
        )
        if checkpoint.final_usage != state.usage:
            raise ExecutionAuthorityError("checkpoint usage does not match guard state")
        if len(receipts) != state.consumption_count:
            raise ExecutionAuthorityError("checkpoint receipt count does not match guard state")
        expected_latest = None if not receipts else receipts[-1].digest
        if expected_latest != state.latest_receipt_digest:
            raise ExecutionAuthorityError(
                "checkpoint latest receipt does not match guard state"
            )
        return checkpoint

    @_synchronized
    def restore_checkpoint(self, checkpoint: AuthorityStateCheckpoint) -> None:
        """Restore authority state without permitting budget or replay reset."""

        if not isinstance(checkpoint, AuthorityStateCheckpoint):
            raise ExecutionAuthorityError(
                "checkpoint must be AuthorityStateCheckpoint"
            )
        authority = checkpoint.authority
        if authority.digest in self._authorities:
            raise ExecutionAuthorityError("checkpoint authority is already admitted")
        if len(self._authority_order) >= self.max_authorities:
            raise ExecutionAuthorityError(
                "authority guard capacity exhausted; refusing checkpoint restore"
            )

        ancestors: tuple[_AuthorityState, ...] = ()
        if authority.parent_authority_digest is not None:
            parent_state = self._authorities.get(authority.parent_authority_digest)
            if parent_state is None:
                raise ExecutionAuthorityError(
                    "checkpoint parent authority must be restored first"
                )
            validate_authority_attenuation(parent_state.authority, authority)
            lineage_error = self._lineage_error(parent_state, now=checkpoint.created_at)
            if lineage_error is not None:
                raise ExecutionAuthorityError(lineage_error)
            ancestors = (parent_state,) + self._ancestor_states(parent_state)
            for ancestor in ancestors:
                aggregate_projected = self._aggregate_usage(ancestor).add(
                    checkpoint.final_usage
                )
                if not ancestor.authority.budget.permits(aggregate_projected):
                    raise ExecutionAuthorityError(
                        "checkpoint restore exceeds ancestor aggregate resource budget"
                    )

        receipts = checkpoint.consumption_receipts
        replay_keys = [checkpoint.admission_receipt.replay_key]
        replay_keys.extend(receipt.replay_key for receipt in receipts)
        if len(set(replay_keys)) != len(replay_keys):
            raise ExecutionAuthorityError("checkpoint contains duplicate replay keys")
        for replay_key in replay_keys:
            self._validate_replay_key(replay_key)
            if replay_key in self._replay_digests:
                raise ExecutionAuthorityError(
                    "checkpoint replay key conflicts with existing guard state"
                )
        if len(self._replay_order) + len(replay_keys) > self.max_replay_keys:
            raise ExecutionAuthorityError(
                "replay guard capacity exhausted; refusing checkpoint restore"
            )

        state = self._remember_authority(authority)
        admission = checkpoint.admission_receipt
        admission_digest = self._admission_replay_payload_digest(
            authority_digest=authority.digest,
            request_identity_digest=admission.request_identity_digest,
            operation_id=admission.operation_id,
            execution_id=admission.execution_id,
        )
        self._remember_replay(admission.replay_key, admission_digest)
        self._admission_receipts[admission.replay_key] = admission
        state.admission_receipt_digest = admission.digest
        state.admitted_at = admission.admitted_at

        for receipt in receipts:
            replay_digest = self._replay_payload_digest(
                authority_digest=authority.digest,
                capability=receipt.capability,
                delta=receipt.delta_usage,
            )
            self._remember_replay(receipt.replay_key, replay_digest)
            self._authorization_receipts[receipt.replay_key] = receipt

        state.usage = checkpoint.final_usage
        for ancestor in ancestors:
            ancestor.descendant_usage = ancestor.descendant_usage.add(
                checkpoint.final_usage
            )
        state.consumption_count = len(receipts)
        state.latest_receipt_digest = None if not receipts else receipts[-1].digest
        state.last_authorized_at = (
            None if not receipts else receipts[-1].authorized_at
        )
        state.revocation_receipt = checkpoint.revocation_receipt
        state.revoked = checkpoint.revocation_receipt is not None

    @_synchronized
    def seal_evidence(
        self,
        authority: ExecutionAuthority,
        *,
        now: datetime | None = None,
    ) -> AuthorityEvidenceBundle:
        """Seal compact evidence for admission and all accounted consumption."""

        instant = self._aware(now)
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        if state is None:
            raise ExecutionAuthorityError("authority has not been admitted")
        if state.authority != authority:
            raise ExecutionAuthorityError("admitted authority content mismatch")
        if state.admission_receipt_digest is None:
            raise ExecutionAuthorityError("authority admission evidence is missing")
        if state.admitted_at is not None and instant < state.admitted_at:
            raise ExecutionAuthorityError("evidence seal time predates admission")
        if state.last_authorized_at is not None and instant < state.last_authorized_at:
            raise ExecutionAuthorityError("evidence seal time predates latest consumption")
        if (
            state.revocation_receipt is not None
            and instant < state.revocation_receipt.revoked_at
        ):
            raise ExecutionAuthorityError("evidence seal time predates revocation")
        return AuthorityEvidenceBundle(
            authority_digest=authority.digest,
            operation_id=authority.operation_id,
            execution_id=authority.execution_id,
            admission_receipt_digest=state.admission_receipt_digest,
            consumption_count=state.consumption_count,
            latest_consumption_digest=state.latest_receipt_digest,
            final_usage=state.usage,
            revoked=state.revoked,
            descendant_usage=state.descendant_usage,
            sealed_at=instant,
            revocation_receipt_digest=(
                None
                if state.revocation_receipt is None
                else state.revocation_receipt.digest
            ),
        )

    @_synchronized
    def effective_usage_for(self, authority: ExecutionAuthority) -> ResourceUsage:
        """Return direct plus descendant usage charged to this authority."""

        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        return ResourceUsage() if state is None else self._aggregate_usage(state)

    @_synchronized
    def usage_for(self, authority: ExecutionAuthority) -> ResourceUsage:
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        return ResourceUsage() if state is None else state.usage

    @_synchronized
    def snapshot(self) -> dict[str, Any]:
        """Return deterministic observability state without exposing mutability."""

        authorities = []
        for digest in sorted(self._authorities):
            state = self._authorities[digest]
            authorities.append(
                {
                    "authority_digest": digest,
                    "authority_id": state.authority.authority_id,
                    "operation_id": state.authority.operation_id,
                    "execution_id": state.authority.execution_id,
                    "revoked": state.revoked,
                    "usage": state.usage.as_dict(),
                    "descendant_usage": state.descendant_usage.as_dict(),
                    "aggregate_usage": self._aggregate_usage(state).as_dict(),
                    "consumption_count": state.consumption_count,
                    "latest_receipt_digest": state.latest_receipt_digest,
                    "admission_receipt_digest": state.admission_receipt_digest,
                    "revocation_receipt_digest": (
                        None
                        if state.revocation_receipt is None
                        else state.revocation_receipt.digest
                    ),
                    "admitted_at": (
                        None if state.admitted_at is None else state.admitted_at.isoformat()
                    ),
                    "last_authorized_at": (
                        None
                        if state.last_authorized_at is None
                        else state.last_authorized_at.isoformat()
                    ),
                    "expires_at": state.authority.expires_at.isoformat(),
                }
            )
        return {
            "authorities": authorities,
            "authority_count": len(authorities),
            "replay_key_count": len(self._replay_digests),
            "admission_receipt_count": len(self._admission_receipts),
            "authorization_receipt_count": len(self._authorization_receipts),
        }


__all__ = [
    "AuthorizationDecision",
    "AuthorizationDisposition",
    "ExecutionAuthorityGuard",
    "MAX_AUTHORITY_DELEGATION_DEPTH",
    "MAX_GUARD_AUTHORITIES",
    "MAX_GUARD_REPLAY_KEYS",
]
