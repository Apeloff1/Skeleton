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
import hashlib
import re
from typing import Any

from skeleton.ai.runtime.contracts.ai_execution import AIExecutionRequest
from skeleton.ai.runtime.contracts.canonical import canonical_json_bytes
from skeleton.ai.runtime.contracts.execution_authority import (
    AdmissionReceipt,
    ExecutionAuthority,
    ExecutionAuthorityError,
    ResourceUsage,
    validate_authority_attenuation,
)


_REPLAY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")

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

    @property
    def allowed(self) -> bool:
        return self.disposition is AuthorizationDisposition.ALLOW


@dataclass(slots=True)
class _AuthorityState:
    authority: ExecutionAuthority
    usage: ResourceUsage
    revoked: bool = False


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
        self._authorities: dict[str, _AuthorityState] = {}
        self._authority_order: list[str] = []
        self._replay_digests: dict[str, str] = {}
        self._replay_order: list[str] = {}
        self._admission_receipts: dict[str, AdmissionReceipt] = []

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
        while len(self._replay_order) >= self.max_replay_keys:
            oldest = self._replay_order.pop(0)
            self._replay_digests.pop(oldest, None)
            self._admission_receipts.pop(oldest, None)
        self._replay_digests[replay_key] = digest
        self._replay_order.append(replay_key)

    def _remember_authority(self, authority: ExecutionAuthority) -> _AuthorityState:
        digest = authority.digest
        existing = self._authorities.get(digest)
        if existing is not None:
            if existing.authority != authority:
                raise ExecutionAuthorityError(
                    "authority digest collision with different contract"
                )
            return existing
        while len(self._authority_order) >= self.max_authorities:
            oldest = self._authority_order.pop(0)
            self._authorities.pop(oldest, None)
        state = _AuthorityState(authority=authority, usage=ResourceUsage())
        self._authorities[digest] = state
        self._authority_order.append(digest)
        return state

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
            validate_authority_attenuation(parent_state.authority, authority)

        state = self._remember_authority(authority)
        if state.revoked:
            raise ExecutionAuthorityError("authority is revoked")

        admission_replay_digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "authority_digest": authority.digest,
                    "request_identity_digest": request.identity_digest,
                    "operation_id": request.operation_id,
                    "execution_id": request.execution_id,
                }
            )
        ).hexdigest()

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
        return receipt

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
        if state.revoked:
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "authority is revoked",
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
            return AuthorizationDecision(
                AuthorizationDisposition.REPLAY,
                "authorization replay already accounted",
                authority.digest,
                state.usage,
                replay_key,
            )

        projected = state.usage.add(usage_delta)
        if not authority.permits(capability, usage=projected, now=instant):
            return AuthorizationDecision(
                AuthorizationDisposition.DENY,
                "capability or resource budget denied",
                authority.digest,
                state.usage,
                replay_key,
            )

        state.usage = projected
        self._remember_replay(replay_key, replay_digest)
        return AuthorizationDecision(
            AuthorizationDisposition.ALLOW,
            "authorized",
            authority.digest,
            state.usage,
            replay_key,
        )

    def revoke(self, authority: ExecutionAuthority) -> None:
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        if state is not None:
            state.revoked = True

    def usage_for(self, authority: ExecutionAuthority) -> ResourceUsage:
        if not isinstance(authority, ExecutionAuthority):
            raise ExecutionAuthorityError("authority must be ExecutionAuthority")
        state = self._authorities.get(authority.digest)
        return ResourceUsage() if state is None else state.usage

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
                    "expires_at": state.authority.expires_at.isoformat(),
                }
            )
        return {
            "authorities": authorities,
            "authority_count": len(authorities),
            "replay_key_count": len(self._replay_digests),
            "admission_receipt_count": len(self._admission_receipts),
        }


__all__ = [
    "AuthorizationDecision",
    "AuthorizationDisposition",
    "ExecutionAuthorityGuard",
    "MAX_GUARD_AUTHORITIES",
    "MAX_GUARD_REPLAY_KEYS",
]
