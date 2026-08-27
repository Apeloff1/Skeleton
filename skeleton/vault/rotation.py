"""Rotation policy — secrets that expire, overlap, and revoke cleanly.

A vault that stores secrets forever is a liability with a delay fuse. The
rotation policy gives every secret a lifecycle: a maximum age, an
automatic successor generation, a grace window during which both the old
and new secret validate (so in-flight callers don't break), and a final
revocation that is recorded in an append-only audit log.

Design laws
-----------
- Rotation is proactive: ``rotate_due()`` is driven by the scheduler, not
  by a failed authentication attempt.
- Overlap is bounded and explicit: both secrets validate during the grace
  window, the old one is revoked exactly at window end, and every
  transition lands in the audit log with a reason.
- The generator is injected — the policy decides *when*, never *what*.
  Callers supply their own secret material, keeping the policy free of
  any particular secret scheme.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import RotationError
from skeleton.kernel.events import DomainEvent, EventBus


class SecretState(Enum):
    ACTIVE = auto()
    GRACE = auto()          # superseded but still validating
    REVOKED = auto()


@dataclass
class SecretVersion:
    version: int
    material: str
    created_at: float
    state: SecretState = SecretState.ACTIVE
    grace_until: Optional[float] = None


@dataclass(frozen=True)
class AuditRecord:
    secret_id: str
    from_version: Optional[int]
    to_version: int
    reason: str
    occurred_at: float = field(default_factory=time.time)


@dataclass
class ManagedSecret:
    secret_id: str
    max_age_s: float
    grace_s: float
    versions: List[SecretVersion] = field(default_factory=list)

    @property
    def active(self) -> Optional[SecretVersion]:
        for v in reversed(self.versions):
            if v.state == SecretState.ACTIVE:
                return v
        return None


class RotationPolicy:
    """Lifecycle manager for versioned secrets."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self._secrets: Dict[str, ManagedSecret] = {}
        self._audit: List[AuditRecord] = []
        self._bus = bus
        self._now = clock or time.time

    def register(self, secret_id: str, material: str, *,
                 max_age_s: float = 86400.0, grace_s: float = 3600.0) -> SecretVersion:
        if max_age_s <= 0 or grace_s < 0 or grace_s >= max_age_s:
            raise RotationError(
                "invalid rotation windows",
                context={"max_age_s": max_age_s, "grace_s": grace_s},
            )
        secret = ManagedSecret(secret_id=secret_id, max_age_s=max_age_s, grace_s=grace_s)
        version = SecretVersion(version=1, material=material, created_at=self._now())
        secret.versions.append(version)
        self._secrets[secret_id] = secret
        self._audit.append(AuditRecord(secret_id, None, 1, "registered"))
        return version

    def rotate_due(self) -> List[str]:
        """Secret ids whose active version is older than max_age."""
        now = self._now()
        due: List[str] = []
        for sid, secret in self._secrets.items():
            active = secret.active
            if active and now - active.created_at >= secret.max_age_s:
                due.append(sid)
        return due

    def rotate(self, secret_id: str, new_material: str, *,
               reason: str = "scheduled") -> SecretVersion:
        secret = self._require(secret_id)
        old = secret.active
        if old is not None:
            old.state = SecretState.GRACE
            old.grace_until = self._now() + secret.grace_s
        version = SecretVersion(
            version=(old.version + 1) if old else 1,
            material=new_material,
            created_at=self._now(),
        )
        secret.versions.append(version)
        self._audit.append(AuditRecord(secret_id,
                                       old.version if old else None,
                                       version.version, reason))
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="vault.secret.rotated",
                    payload={"secret_id": secret_id, "to_version": version.version,
                             "reason": reason, "grace_until": version.created_at + secret.grace_s},
                    correlation_id=f"rot_{secret_id}_{version.version}",
                )
            )
        return version

    def validate(self, secret_id: str, material: str) -> bool:
        """True if material matches the active version or one in grace."""
        secret = self._secrets.get(secret_id)
        if secret is None:
            return False
        now = self._now()
        for version in secret.versions:
            if version.state == SecretState.ACTIVE and version.material == material:
                return True
            if (version.state == SecretState.GRACE
                    and version.material == material
                    and version.grace_until is not None
                    and now <= version.grace_until):
                return True
        return False

    def sweep_expired_grace(self) -> List[str]:
        """Revoke grace versions past their window. Returns revoked ids."""
        now = self._now()
        revoked: List[str] = []
        for sid, secret in self._secrets.items():
            for version in secret.versions:
                if (version.state == SecretState.GRACE
                        and version.grace_until is not None
                        and now > version.grace_until):
                    version.state = SecretState.REVOKED
                    revoked.append(sid)
                    self._audit.append(AuditRecord(sid, version.version,
                                                   version.version, "grace expired"))
                    if self._bus:
                        self._bus.publish(
                            DomainEvent(
                                topic="vault.secret.revoked",
                                payload={"secret_id": sid, "version": version.version},
                                correlation_id=f"rev_{sid}_{version.version}",
                            )
                        )
        return revoked

    def audit_log(self, secret_id: Optional[str] = None) -> List[AuditRecord]:
        return [a for a in self._audit if secret_id is None or a.secret_id == secret_id]

    def _require(self, secret_id: str) -> ManagedSecret:
        secret = self._secrets.get(secret_id)
        if secret is None:
            raise RotationError("unknown secret", context={"secret_id": secret_id})
        return secret

    def stats(self) -> Dict[str, Any]:
        return {
            "secrets_managed": len(self._secrets),
            "due_for_rotation": len(self.rotate_due()),
            "audit_records": len(self._audit),
        }


class RotationTrigger(str, Enum):
    SCHEDULED = "scheduled"
    COMPROMISE = "compromise"
    MANUAL = "manual"


class RotationScheduler:
    """Drives RotationPolicy.rotate_due() with an injected generator."""

    def __init__(self, policy: RotationPolicy, *,
                 generator: Optional[Callable[[str], str]] = None) -> None:
        self.policy = policy
        self._generator = generator or (lambda sid: f"{sid}-{int(time.time())}")
        self._runs = 0

    def tick(self, *, reason: str = RotationTrigger.SCHEDULED.value) -> List[str]:
        rotated: List[str] = []
        for sid in self.policy.rotate_due():
            self.policy.rotate(sid, self._generator(sid), reason=reason)
            rotated.append(sid)
        expired = self.policy.sweep_expired_grace()
        self._runs += 1
        return rotated + [f"revoked:{s}" for s in expired]

    def stats(self) -> Dict[str, int]:
        return {"runs": self._runs, "secrets": len(self.policy._secrets)}
