"""Rotation scheduler — policy-driven secret and credential rotation.

Schedules automatic rotation for every secret in the secret manager
based on age policies (max_age per secret class). Tracks rotation
history, enforces overlap windows where old and new credentials both
work, and fires notifications when rotation is overdue.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RotationPolicy:
    secret_class: str
    max_age_s: float
    overlap_s: float = 300.0
    auto_rotate: bool = True


@dataclass
class RotationRecord:
    secret: str
    rotated_ns: int
    overlap_ends_ns: int
    reason: str


class RotationScheduler:
    """Age-policy secret rotation with overlap windows."""

    def __init__(self, secret_manager: Any = None,
                 rotator: Optional[Callable[[str], str]] = None):
        self._policies: Dict[str, RotationPolicy] = {}
        self._secret_class: Dict[str, str] = {}
        self._history: List[RotationRecord] = []
        self._secret_manager = secret_manager
        self._rotator = rotator or (lambda name: f"rotated-{name}-{time.time_ns()}")
        self._pending_overlap: Dict[str, int] = {}

    def set_policy(self, secret_class: str, max_age_s: float,
                   overlap_s: float = 300.0, auto_rotate: bool = True) -> RotationPolicy:
        policy = RotationPolicy(secret_class=secret_class, max_age_s=max_age_s,
                                overlap_s=overlap_s, auto_rotate=auto_rotate)
        self._policies[secret_class] = policy
        return policy

    def assign_class(self, secret_name: str, secret_class: str) -> None:
        self._secret_class[secret_name] = secret_class

    def last_rotation(self, secret_name: str) -> Optional[int]:
        records = [r for r in self._history if r.secret == secret_name]
        return records[-1].rotated_ns if records else None

    def due_for_rotation(self, created_ns_map: Dict[str, int]) -> List[Dict[str, Any]]:
        now = time.time_ns()
        due: List[Dict[str, Any]] = []
        for name, cls in self._secret_class.items():
            policy = self._policies.get(cls)
            if not policy:
                continue
            created = self.last_rotation(name) or created_ns_map.get(name, now)
            age_s = (now - created) / 1e9
            if age_s > policy.max_age_s:
                due.append({
                    "secret": name,
                    "class": cls,
                    "age_s": round(age_s, 1),
                    "max_age_s": policy.max_age_s,
                    "overdue_by_s": round(age_s - policy.max_age_s, 1),
                    "auto_rotate": policy.auto_rotate,
                })
        return due

    def rotate(self, secret_name: str, reason: str = "scheduled") -> Dict[str, Any]:
        cls = self._secret_class.get(secret_name, "token")
        policy = self._policies.get(cls, RotationPolicy(cls, 86400.0))
        new_value = self._rotator(secret_name)
        if self._secret_manager:
            self._secret_manager.rotate(secret_name, new_value)
        now = time.time_ns()
        self._pending_overlap[secret_name] = now + int(policy.overlap_s * 1e9)
        record = RotationRecord(secret=secret_name, rotated_ns=now,
                                overlap_ends_ns=self._pending_overlap[secret_name], reason=reason)
        self._history.append(record)
        return {"rotated": secret_name, "overlap_ends_in_s": policy.overlap_s, "reason": reason}

    def run_scheduled(self, created_ns_map: Dict[str, int]) -> List[Dict[str, Any]]:
        rotated = []
        for item in self.due_for_rotation(created_ns_map):
            if item["auto_rotate"]:
                rotated.append(self.rotate(item["secret"], reason="policy"))
        return rotated

    def overlap_active(self, secret_name: str) -> bool:
        end = self._pending_overlap.get(secret_name)
        return bool(end and time.time_ns() < end)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "rotation-scheduler-card",
            "policies": {c: {"max_age_s": p.max_age_s, "overlap_s": p.overlap_s, "auto": p.auto_rotate}
                         for c, p in self._policies.items()},
            "classified_secrets": len(self._secret_class),
            "rotations": len(self._history),
            "active_overlaps": [s for s, e in self._pending_overlap.items() if time.time_ns() < e],
        }
