"""Durable conflict-key leases for autonomous repository work."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

MAX_LEASES = 2048
MAX_BYTES = 2 * 1024 * 1024


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkLease:
    lease_id: str
    objective_id: str
    holder: str
    acquired_at: int
    expires_at: int
    conflict_keys: tuple[str, ...]
    repository_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("lease_id", "objective_id", "holder", "repository_fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if isinstance(self.acquired_at, bool) or not isinstance(self.acquired_at, int) or self.acquired_at <= 0:
            raise ValueError("acquired_at must be positive")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at <= self.acquired_at:
            raise ValueError("expires_at must exceed acquired_at")
        keys = tuple(sorted({str(item).strip() for item in self.conflict_keys if str(item).strip()}))
        if not keys:
            raise ValueError("lease requires conflict keys")
        object.__setattr__(self, "conflict_keys", keys)

    def as_dict(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "objective_id": self.objective_id,
            "holder": self.holder,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "conflict_keys": list(self.conflict_keys),
            "repository_fingerprint": self.repository_fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "WorkLease":
        return cls(
            lease_id=str(value.get("lease_id", "")),
            objective_id=str(value.get("objective_id", "")),
            holder=str(value.get("holder", "")),
            acquired_at=int(value.get("acquired_at", 0)),
            expires_at=int(value.get("expires_at", 0)),
            conflict_keys=tuple(value.get("conflict_keys", ())),
            repository_fingerprint=str(value.get("repository_fingerprint", "")),
        )


@dataclass(slots=True)
class LeaseRegistry:
    leases: dict[str, WorkLease] = field(default_factory=dict)

    def prune(self, now: int) -> tuple[str, ...]:
        expired = tuple(sorted(
            lease_id
            for lease_id, lease in self.leases.items()
            if lease.expires_at <= now
        ))
        for lease_id in expired:
            self.leases.pop(lease_id, None)
        return expired

    def active_conflicts(self, now: int) -> tuple[str, ...]:
        self.prune(now)
        return tuple(sorted({
            key
            for lease in self.leases.values()
            for key in lease.conflict_keys
        }))

    def can_acquire(self, conflict_keys: Iterable[str], now: int) -> bool:
        requested = {str(item).strip() for item in conflict_keys if str(item).strip()}
        return not requested.intersection(self.active_conflicts(now))

    def acquire(
        self,
        *,
        objective_id: str,
        holder: str,
        conflict_keys: Iterable[str],
        repository_fingerprint: str,
        now: int,
        ttl_seconds: int = 3600,
    ) -> WorkLease:
        if len(self.leases) >= MAX_LEASES:
            self.prune(now)
        if len(self.leases) >= MAX_LEASES:
            raise RuntimeError("lease registry capacity exceeded")
        keys = tuple(sorted({str(item).strip() for item in conflict_keys if str(item).strip()}))
        if not self.can_acquire(keys, now):
            raise RuntimeError("requested work conflicts with an active lease")
        lease_id = _checksum([
            objective_id,
            holder,
            keys,
            repository_fingerprint,
            now,
        ])[:32]
        lease = WorkLease(
            lease_id=lease_id,
            objective_id=objective_id,
            holder=holder,
            acquired_at=now,
            expires_at=now + ttl_seconds,
            conflict_keys=keys,
            repository_fingerprint=repository_fingerprint,
        )
        self.leases[lease_id] = lease
        return lease

    def release(self, lease_id: str) -> bool:
        return self.leases.pop(lease_id, None) is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "leases": [
                self.leases[key].as_dict()
                for key in sorted(self.leases)
            ],
        }

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        state = self.as_dict()
        envelope = {
            "checksum": _checksum(state),
            "state": state,
        }
        rendered = _canonical(envelope) + "\n"
        if len(rendered.encode("utf-8")) > MAX_BYTES:
            raise RuntimeError("lease registry exceeds byte budget")
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            text=True,
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: str | Path) -> "LeaseRegistry":
        raw = Path(path).read_bytes()
        if len(raw) > MAX_BYTES:
            raise RuntimeError("lease registry exceeds byte budget")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
            raise ValueError("invalid lease registry envelope")
        state = payload["state"]
        if payload.get("checksum") != _checksum(state):
            raise ValueError("lease registry checksum mismatch")
        if state.get("version") != 1 or not isinstance(state.get("leases"), list):
            raise ValueError("unsupported lease registry state")
        leases: dict[str, WorkLease] = {}
        for item in state["leases"]:
            if not isinstance(item, dict):
                raise ValueError("invalid lease record")
            lease = WorkLease.from_dict(item)
            if lease.lease_id in leases:
                raise ValueError("duplicate lease id")
            leases[lease.lease_id] = lease
        return cls(leases)
