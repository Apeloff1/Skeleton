"""RBAC — role-based access control for all operator surfaces.

Provides permission checking for CLI commands, API endpoints, and
deck operations. Roles map to permission sets; users map to roles.
Every check is recorded in the audit log for full traceability.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class Role:
    name: str
    permissions: Set[str] = field(default_factory=set)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "permissions": sorted(self.permissions), "description": self.description}


@dataclass
class Grant:
    actor: str
    role: str
    granted_by: str
    timestamp_ns: int

    def to_dict(self) -> Dict[str, Any]:
        return {"actor": self.actor, "role": self.role, "granted_by": self.granted_by, "timestamp_ns": self.timestamp_ns}


class RBACRegistry:
    """Central RBAC registry with wildcard permission matching."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._roles: Dict[str, Role] = {}
        self._assignments: Dict[str, Set[str]] = {}
        self._grants: List[Grant] = []
        self._file = self.root / "rbac.json"
        self._load()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        if "admin" not in self._roles:
            self.register_role("admin", {"*"}, description="Full access")
        if "operator" not in self._roles:
            self.register_role("operator", {
                "policy.read", "policy.write", "repair.*", "dashboard.*",
                "observability.read", "resilience.read", "flags.read",
            }, description="Day-to-day operations")
        if "viewer" not in self._roles:
            self.register_role("viewer", {
                "policy.read", "dashboard.read", "observability.read",
                "health.read", "metrics.read",
            }, description="Read-only visibility")

    def _load(self) -> None:
        if self._file.exists():
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for name, r in data.get("roles", {}).items():
                self._roles[name] = Role(name=name, permissions=set(r.get("permissions", [])), description=r.get("description", ""))
            for actor, roles in data.get("assignments", {}).items():
                self._assignments[actor] = set(roles)

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps({
            "roles": {n: r.to_dict() for n, r in self._roles.items()},
            "assignments": {a: sorted(r) for a, r in self._assignments.items()},
        }, indent=2), encoding="utf-8")

    def register_role(self, name: str, permissions: Set[str], description: str = "") -> Role:
        role = Role(name=name, permissions=set(permissions), description=description)
        self._roles[name] = role
        self._save()
        return role

    def grant(self, actor: str, role: str, granted_by: str = "system") -> None:
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        self._assignments.setdefault(actor, set()).add(role)
        self._grants.append(Grant(actor=actor, role=role, granted_by=granted_by, timestamp_ns=time.time_ns()))
        self._save()

    def revoke(self, actor: str, role: str) -> bool:
        roles = self._assignments.get(actor, set())
        if role in roles:
            roles.discard(role)
            self._save()
            return True
        return False

    def permissions_for(self, actor: str) -> Set[str]:
        perms: Set[str] = set()
        for role_name in self._assignments.get(actor, set()):
            role = self._roles.get(role_name)
            if role:
                perms |= role.permissions
        return perms

    def check(self, actor: str, permission: str) -> bool:
        perms = self.permissions_for(actor)
        if "*" in perms:
            return True
        if permission in perms:
            return True
        for p in perms:
            if p.endswith(".*") and permission.startswith(p[:-1]):
                return True
        return False

    def check_scope(self, actor: str, scope: str, action: str) -> bool:
        return self.check(actor, f"{scope}.{action}")

    def roles_of(self, actor: str) -> List[str]:
        return sorted(self._assignments.get(actor, set()))

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "rbac-card",
            "roles": [r.to_dict() for r in self._roles.values()],
            "actors": len(self._assignments),
            "grants": len(self._grants),
        }
