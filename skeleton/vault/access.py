"""Access control for the vault — who may touch which secret.

Sealing and rotation are useless if any caller can open any secret.
AccessPolicy assigns roles (admin, reader, rotator) with glob-style
patterns over secret ids, and every check is auditable via the same
notify hook RotationScheduler uses.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import VaultError


class AccessDenied(VaultError):
    code = "VLT.ACCESS_DENIED"
    http_status = 403


@dataclass(frozen=True)
class Role:
    name: str
    patterns: tuple  # glob patterns like "payments/*", "*"
    allow: tuple = ("read",)  # which actions are permitted


class AccessPolicy:
    """Role-based access gate with glob patterns and an audit hook."""

    def __init__(
        self,
        *,
        notify: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self._roles: Dict[str, Role] = {}
        self._grants: Dict[str, tuple] = {}  # subject -> role names
        self._notify = notify

    def define(self, role: Role) -> None:
        self._roles[role.name] = role

    def grant(self, subject: str, role_name: str) -> None:
        if role_name not in self._roles:
            raise AccessDenied("unknown role", context={"role": role_name})
        existing = self._grants.get(subject, ())
        if role_name not in existing:
            self._grants[subject] = existing + (role_name,)

    def revoke(self, subject: str, role_name: str) -> None:
        existing = self._grants.get(subject, ())
        self._grants[subject] = tuple(r for r in existing if r != role_name)

    def check(self, subject: str, secret_id: str, action: str) -> None:
        for role_name in self._grants.get(subject, ()):
            role = self._roles.get(role_name)
            if role is None:
                continue
            if action not in role.allow:
                continue
            if any(fnmatch.fnmatchcase(secret_id, p) for p in role.patterns):
                self._emit(subject, secret_id, action, true_outcome=True)
                return
        self._emit(subject, secret_id, action, true_outcome=False)
        raise AccessDenied(
            "access denied",
            context={"subject": subject, "secret": secret_id, "action": action},
        )

    def _emit(self, subject: str, secret_id: str, action: str, true_outcome: bool) -> None:
        if self._notify is not None:
            self._notify({
                "subject": subject,
                "secret_id": secret_id,
                "action": action,
                "outcome": "granted" if true_outcome else "denied",
            })
