"""Reverse-proxy contracts — sibling of Zaibatsu.Gate YARP + HttpClient policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    hedge_timeout_s: float = 10.0
    retry_safe_methods_only: bool = True
    require_idempotency_key_on_mutate_retry: bool = True
    circuit_fail_threshold: int = 5
    circuit_reset_s: float = 30.0

    def allows_retry(self, method: str, *, has_idempotency_key: bool) -> bool:
        m = (method or "GET").upper()
        if m in {"GET", "HEAD", "OPTIONS"}:
            return True
        if not self.retry_safe_methods_only:
            return True
        # Mutating: only with idempotency key (Gate doctrine).
        return bool(has_idempotency_key) if self.require_idempotency_key_on_mutate_retry else False

    def as_dict(self) -> Dict[str, object]:
        return {
            "max_retries": self.max_retries,
            "hedge_timeout_s": self.hedge_timeout_s,
            "retry_safe_methods_only": self.retry_safe_methods_only,
            "require_idempotency_key_on_mutate_retry": self.require_idempotency_key_on_mutate_retry,
            "circuit_fail_threshold": self.circuit_fail_threshold,
            "circuit_reset_s": self.circuit_reset_s,
        }


@dataclass(frozen=True)
class ProxyUpstream:
    name: str
    base_url: str
    health_path: str
    timeout_s: float
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def health_url(self) -> str:
        return self.base_url.rstrip("/") + self.health_path

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "health_path": self.health_path,
            "timeout_s": self.timeout_s,
            "health_url": self.health_url(),
            "retry": self.retry.as_dict(),
        }


def default_upstreams() -> Tuple[ProxyUpstream, ...]:
    return (
        ProxyUpstream("rust_spine", "http://localhost:8001", "/ready", 10.0),
        ProxyUpstream("forge", "http://localhost:8002", "/health", 15.0),
        ProxyUpstream("swarm", "http://localhost:8003", "/ready", 10.0),
        ProxyUpstream("jeeves", "http://localhost:8004", "/health", 20.0),
        ProxyUpstream("cognition", "http://localhost:8005", "/ready", 12.0),
        ProxyUpstream("lafs", "http://localhost:8006", "/ready", 8.0),
        ProxyUpstream("studio", "http://localhost:8007", "/health", 30.0),
        ProxyUpstream("court", "http://localhost:8008", "/ready", 10.0),
        ProxyUpstream("treasury", "http://localhost:8009", "/ready", 10.0),
        ProxyUpstream("governance", "http://localhost:8010", "/ready", 10.0),
    )


def validate_proxy_plan(upstreams: Sequence[ProxyUpstream]) -> Dict[str, object]:
    errors: List[str] = []
    names = set()
    for u in upstreams:
        if u.name in names:
            errors.append(f"duplicate_upstream:{u.name}")
        names.add(u.name)
        if not u.base_url.startswith("http"):
            errors.append(f"bad_base_url:{u.name}")
        if u.timeout_s <= 0:
            errors.append(f"bad_timeout:{u.name}")
        if u.retry.max_retries < 0:
            errors.append(f"bad_retries:{u.name}")
    return {"ok": not errors, "errors": errors, "count": len(upstreams)}

def plan_upstream_rust_spine(*, timeout_s: float = 10.0) -> ProxyUpstream:
    return ProxyUpstream("rust_spine", "http://localhost:8001", "/ready", timeout_s)

def audit_upstream_rust_spine(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "rust_spine":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_forge(*, timeout_s: float = 15.0) -> ProxyUpstream:
    return ProxyUpstream("forge", "http://localhost:8002", "/health", timeout_s)

def audit_upstream_forge(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "forge":
        errs.append("name_mismatch")
    if upstream.health_path != "/health":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_swarm(*, timeout_s: float = 10.0) -> ProxyUpstream:
    return ProxyUpstream("swarm", "http://localhost:8003", "/ready", timeout_s)

def audit_upstream_swarm(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "swarm":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_jeeves(*, timeout_s: float = 20.0) -> ProxyUpstream:
    return ProxyUpstream("jeeves", "http://localhost:8004", "/health", timeout_s)

def audit_upstream_jeeves(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "jeeves":
        errs.append("name_mismatch")
    if upstream.health_path != "/health":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_cognition(*, timeout_s: float = 12.0) -> ProxyUpstream:
    return ProxyUpstream("cognition", "http://localhost:8005", "/ready", timeout_s)

def audit_upstream_cognition(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "cognition":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_lafs(*, timeout_s: float = 8.0) -> ProxyUpstream:
    return ProxyUpstream("lafs", "http://localhost:8006", "/ready", timeout_s)

def audit_upstream_lafs(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "lafs":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_studio(*, timeout_s: float = 30.0) -> ProxyUpstream:
    return ProxyUpstream("studio", "http://localhost:8007", "/health", timeout_s)

def audit_upstream_studio(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "studio":
        errs.append("name_mismatch")
    if upstream.health_path != "/health":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_court(*, timeout_s: float = 10.0) -> ProxyUpstream:
    return ProxyUpstream("court", "http://localhost:8008", "/ready", timeout_s)

def audit_upstream_court(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "court":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_treasury(*, timeout_s: float = 10.0) -> ProxyUpstream:
    return ProxyUpstream("treasury", "http://localhost:8009", "/ready", timeout_s)

def audit_upstream_treasury(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "treasury":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}

def plan_upstream_governance(*, timeout_s: float = 10.0) -> ProxyUpstream:
    return ProxyUpstream("governance", "http://localhost:8010", "/ready", timeout_s)

def audit_upstream_governance(upstream: ProxyUpstream) -> Dict[str, object]:
    errs = []
    if upstream.name != "governance":
        errs.append("name_mismatch")
    if upstream.health_path != "/ready":
        errs.append("health_mismatch")
    return {"name": upstream.name, "ok": not errs, "errors": errs, "plan": upstream.as_dict()}


ROUTE_UPSTREAM: Dict[str, str] = {
    "forge": "forge",
    "gameforge": "forge",
    "swarm": "swarm",
    "jeeves": "jeeves",
    "memory": "rust_spine",
    "cognition": "cognition",
    "lafs": "lafs",
    "studio": "studio",
    "court": "court",
    "treasury": "treasury",
    "governance": "governance",
    "legions": "swarm",
    "fabric": "rust_spine",
}

def resolve_forge_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["forge"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_forge_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_forge_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_forge_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["forge"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_forge_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_forge_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_gameforge_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["gameforge"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_gameforge_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_gameforge_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_gameforge_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["gameforge"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_gameforge_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_gameforge_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_swarm_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["swarm"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_swarm_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_swarm_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_swarm_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["swarm"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_swarm_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_swarm_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_jeeves_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["jeeves"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_jeeves_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_jeeves_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_jeeves_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["jeeves"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_jeeves_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_jeeves_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_memory_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["memory"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_memory_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_memory_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_memory_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["memory"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_memory_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_memory_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_cognition_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["cognition"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_cognition_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_cognition_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_cognition_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["cognition"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_cognition_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_cognition_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_lafs_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["lafs"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_lafs_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_lafs_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_lafs_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["lafs"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_lafs_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_lafs_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_studio_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["studio"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_studio_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_studio_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_studio_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["studio"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_studio_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_studio_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_court_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["court"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_court_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_court_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_court_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["court"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_court_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_court_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_treasury_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["treasury"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_treasury_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_treasury_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_treasury_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["treasury"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_treasury_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_treasury_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_governance_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["governance"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_governance_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_governance_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_governance_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["governance"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_governance_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_governance_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_legions_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["legions"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_legions_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_legions_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_legions_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["legions"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_legions_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_legions_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)

def resolve_fabric_get() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["fabric"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_fabric_get(*, has_idempotency_key: bool = False) -> bool:
    return resolve_fabric_get().retry.allows_retry("GET", has_idempotency_key=has_idempotency_key)

def resolve_fabric_post() -> ProxyUpstream:
    name = ROUTE_UPSTREAM["fabric"]
    for u in default_upstreams():
        if u.name == name:
            return u
    raise KeyError(name)

def retry_ok_fabric_post(*, has_idempotency_key: bool = False) -> bool:
    return resolve_fabric_post().retry.allows_retry("POST", has_idempotency_key=has_idempotency_key)
