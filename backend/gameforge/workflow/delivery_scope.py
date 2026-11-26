"""Verified principal scope for workflow custody. Request bodies never choose it."""
from __future__ import annotations
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from core.auth_security import auth_enforced

@dataclass(frozen=True)
class DeliveryScope:
    tenant: str
    owner: str

    @property
    def key(self) -> str:
        value = json.dumps([self.tenant, self.owner], separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(value.encode("ascii")).hexdigest()

_SYSTEM = DeliveryScope("internal", "system")
_LOCAL = DeliveryScope("local", "local")
_current: ContextVar[DeliveryScope] = ContextVar("workflow_scope", default=_SYSTEM)

def current_scope() -> DeliveryScope:
    return _current.get()

def scope_for_user(user: dict | None) -> DeliveryScope | None:
    if isinstance(user, dict) and not user.get("dev_mode"):
        owner = user.get("email") or user.get("user_id")
        tenant = user.get("tenant_id") or "default"
        if (isinstance(owner, str) and isinstance(tenant, str)
                and 1 <= len(owner.strip()) <= 320 and 1 <= len(tenant.strip()) <= 256
                and owner.strip() != "anonymous"):
            return DeliveryScope(tenant.strip(), owner.strip())
        return None
    return _LOCAL if not auth_enforced() else None

@contextmanager
def use_scope(scope: DeliveryScope):
    if not isinstance(scope, DeliveryScope):
        raise ValueError("trusted workflow scope required")
    token = _current.set(scope)
    try:
        yield
    finally:
        _current.reset(token)
