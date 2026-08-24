"""Credential rotation scheduler for the vault.

Secrets age: tokens expire, keys leak, employees leave. The rotation
scheduler ensures every credential in the vault is refreshed before
it becomes a liability.

- RotationPolicy: age-based, usage-count-based, or manual trigger
- RotationScheduler: tracks versions, schedules rotations, coordinates
  handoff with consumers via the optional notify hook
- Audit trail: every rotation is logged with actor, reason, and outcome
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import VaultError


class RotationError(VaultError):
    code = "VLT.ROTATION"


class RotationTrigger(str, Enum):
    AGE = "AGE"
    USAGE = "USAGE"
    MANUAL = "MANUAL"


@dataclass
class RotationPolicy:
    max_age_s: float = 86400.0 * 90  # 90 days
    max_uses: Optional[int] = None
    trigger: RotationTrigger = RotationTrigger.AGE


@dataclass
class SecretVersion:
    secret_id: str
    version: int
    created_at: float
    expires_at: float
    uses: int = 0
    rotated: bool = False


class RotationScheduler:
    """Tracks secret lifetimes and performs rotations."""

    def __init__(
        self,
        *,
        notify: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._notify = notify
        self._now = clock or time.monotonic
        self._secrets: Dict[str, SecretVersion] = {}
        self._policies: Dict[str, RotationPolicy] = {}
        self._log: List[Dict[str, Any]] = []

    def register(self, secret_id: str, policy: RotationPolicy) -> None:
        self._policies[secret_id] = policy
        self._touch(secret_id)

    def use(self, secret_id: str) -> None:
        version = self._require(secret_id)
        version.uses += 1
        policy = self._policies.get(secret_id, RotationPolicy())
        if policy.max_uses is not None and version.uses >= policy.max_uses:
            self._rotate(secret_id, RotationTrigger.USAGE)

    def sweep(self) -> Tuple[str, ...]:
        """Expire old secrets; call on a timer. Returns IDs that rotated."""
        now = self._now()
        due = [
            sid
            for sid, policy in self._policies.items()
            if sid in self._secrets and self._secrets[sid].expires_at <= now
        ]
        for sid in due:
            self._rotate(sid, RotationTrigger.AGE)
        return tuple(due)

    def rotate_now(
        self, secret_id: str, *, actor: str = "manual", reason: str = ""
    ) -> SecretVersion:
        return self._rotate(secret_id, RotationTrigger.MANUAL, actor=actor, reason=reason)

    def _rotate(
        self,
        secret_id: str,
        trigger: RotationTrigger,
        *,
        actor: str = "scheduler",
        reason: str = "",
    ) -> SecretVersion:
        old = self._secrets.pop(secret_id, None)
        new = self._touch(secret_id)
        entry = {
            "secret_id": secret_id,
            "trigger": trigger.value,
            "actor": actor,
            "reason": reason,
            "old_version": old.version if old else None,
            "new_version": new.version,
            "at": self._now(),
        }
        self._log.append(entry)
        if self._notify is not None:
            self._notify(secret_id, entry)
        return new

    def _touch(self, secret_id: str) -> SecretVersion:
        policy = self._policies.get(secret_id, RotationPolicy())
        now = self._now()
        version = SecretVersion(
            secret_id=secret_id,
            version=(
                self._secrets[secret_id].version + 1
                if secret_id in self._secrets
                else 1
            ),
            created_at=now,
            expires_at=now + policy.max_age_s,
        )
        self._secrets[secret_id] = version
        return version

    def _require(self, secret_id: str) -> SecretVersion:
        if secret_id not in self._secrets:
            raise RotationError(
                "secret not registered", context={"secret": secret_id}
            )
        return self._secrets[secret_id]

    def status(self, secret_id: str) -> Dict[str, Any]:
        version = self._require(secret_id)
        policy = self._policies.get(secret_id, RotationPolicy())
        return {
            "secret": secret_id,
            "version": version.version,
            "age_s": round(self._now() - version.created_at, 1),
            "uses": version.uses,
            "expires_in_s": round(version.expires_at - self._now(), 1),
            "policy": {
                "max_age_s": policy.max_age_s,
                "max_uses": policy.max_uses,
                "trigger": policy.trigger.value,
            },
        }

    def audit_log(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(self._log)
