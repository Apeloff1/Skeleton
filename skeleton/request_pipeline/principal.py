"""Principal binding — authN glue sibling of Zaibatsu PrincipalAuth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Sequence, Tuple
import hashlib
import hmac
import time


@dataclass(frozen=True)
class Principal:
    name: str
    roles: FrozenSet[str]
    scopes: FrozenSet[str]
    attester: Optional[str] = None
    expires_at: Optional[int] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "roles": sorted(self.roles),
            "scopes": sorted(self.scopes),
            "attester": self.attester,
            "expires_at": self.expires_at,
        }

    def alive(self, *, now: Optional[int] = None) -> bool:
        if self.expires_at is None:
            return True
        t = int(time.time() if now is None else now)
        return self.expires_at > t


def bind_principal(
    name: str,
    *,
    roles: Sequence[str] = (),
    scopes: Sequence[str] = (),
    attester: Optional[str] = None,
    ttl_secs: Optional[int] = None,
    now: Optional[int] = None,
) -> Principal:
    exp = None
    if ttl_secs is not None:
        t = int(time.time() if now is None else now)
        exp = t + int(ttl_secs)
    return Principal(
        name=name,
        roles=frozenset(roles),
        scopes=frozenset(scopes),
        attester=attester or name,
        expires_at=exp,
    )


def verify_principal_token(token: str, *, secret: str) -> Optional[Principal]:
    """Parse name.exp.sig style token (HMAC-SHA256). Fail closed."""
    if not secret or not token:
        return None
    parts = token.rsplit(".", 2)
    if len(parts) != 3:
        return None
    name, exp_s, sig = parts
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp <= int(time.time()):
        return None
    payload = f"{name}|{exp}".encode()
    expect = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    return bind_principal(name, attester=name, ttl_secs=max(0, exp - int(time.time())))


def mint_principal_token(name: str, *, secret: str, ttl_secs: int = 300) -> Optional[str]:
    if not secret or not name:
        return None
    exp = int(time.time()) + int(ttl_secs)
    payload = f"{name}|{exp}".encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"{name}.{exp}.{sig}"

# --- domain principal binders ---

def bind_forge_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("forge-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="forge-anon", ttl_secs=ttl_secs)

def audit_bind_forge_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("forge-") and "anon" in p.roles and p.alive()
    return {"domain": "forge", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_forge_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("forge-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="forge-operator", ttl_secs=ttl_secs)

def audit_bind_forge_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("forge-") and "operator" in p.roles and p.alive()
    return {"domain": "forge", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_forge_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("forge-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="forge-attester", ttl_secs=ttl_secs)

def audit_bind_forge_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("forge-") and "attester" in p.roles and p.alive()
    return {"domain": "forge", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_forge_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("forge-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="forge-admin", ttl_secs=ttl_secs)

def audit_bind_forge_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("forge-") and "admin" in p.roles and p.alive()
    return {"domain": "forge", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_gameforge_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("gameforge-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="gameforge-anon", ttl_secs=ttl_secs)

def audit_bind_gameforge_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("gameforge-") and "anon" in p.roles and p.alive()
    return {"domain": "gameforge", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_gameforge_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("gameforge-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="gameforge-operator", ttl_secs=ttl_secs)

def audit_bind_gameforge_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("gameforge-") and "operator" in p.roles and p.alive()
    return {"domain": "gameforge", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_gameforge_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("gameforge-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="gameforge-attester", ttl_secs=ttl_secs)

def audit_bind_gameforge_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("gameforge-") and "attester" in p.roles and p.alive()
    return {"domain": "gameforge", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_gameforge_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("gameforge-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="gameforge-admin", ttl_secs=ttl_secs)

def audit_bind_gameforge_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("gameforge-") and "admin" in p.roles and p.alive()
    return {"domain": "gameforge", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_swarm_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("swarm-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="swarm-anon", ttl_secs=ttl_secs)

def audit_bind_swarm_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("swarm-") and "anon" in p.roles and p.alive()
    return {"domain": "swarm", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_swarm_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("swarm-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="swarm-operator", ttl_secs=ttl_secs)

def audit_bind_swarm_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("swarm-") and "operator" in p.roles and p.alive()
    return {"domain": "swarm", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_swarm_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("swarm-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="swarm-attester", ttl_secs=ttl_secs)

def audit_bind_swarm_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("swarm-") and "attester" in p.roles and p.alive()
    return {"domain": "swarm", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_swarm_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("swarm-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="swarm-admin", ttl_secs=ttl_secs)

def audit_bind_swarm_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("swarm-") and "admin" in p.roles and p.alive()
    return {"domain": "swarm", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_jeeves_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("jeeves-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="jeeves-anon", ttl_secs=ttl_secs)

def audit_bind_jeeves_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("jeeves-") and "anon" in p.roles and p.alive()
    return {"domain": "jeeves", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_jeeves_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("jeeves-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="jeeves-operator", ttl_secs=ttl_secs)

def audit_bind_jeeves_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("jeeves-") and "operator" in p.roles and p.alive()
    return {"domain": "jeeves", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_jeeves_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("jeeves-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="jeeves-attester", ttl_secs=ttl_secs)

def audit_bind_jeeves_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("jeeves-") and "attester" in p.roles and p.alive()
    return {"domain": "jeeves", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_jeeves_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("jeeves-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="jeeves-admin", ttl_secs=ttl_secs)

def audit_bind_jeeves_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("jeeves-") and "admin" in p.roles and p.alive()
    return {"domain": "jeeves", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_memory_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("memory-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="memory-anon", ttl_secs=ttl_secs)

def audit_bind_memory_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("memory-") and "anon" in p.roles and p.alive()
    return {"domain": "memory", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_memory_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("memory-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="memory-operator", ttl_secs=ttl_secs)

def audit_bind_memory_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("memory-") and "operator" in p.roles and p.alive()
    return {"domain": "memory", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_memory_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("memory-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="memory-attester", ttl_secs=ttl_secs)

def audit_bind_memory_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("memory-") and "attester" in p.roles and p.alive()
    return {"domain": "memory", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_memory_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("memory-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="memory-admin", ttl_secs=ttl_secs)

def audit_bind_memory_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("memory-") and "admin" in p.roles and p.alive()
    return {"domain": "memory", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_retrieval_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("retrieval-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="retrieval-anon", ttl_secs=ttl_secs)

def audit_bind_retrieval_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("retrieval-") and "anon" in p.roles and p.alive()
    return {"domain": "retrieval", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_retrieval_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("retrieval-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="retrieval-operator", ttl_secs=ttl_secs)

def audit_bind_retrieval_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("retrieval-") and "operator" in p.roles and p.alive()
    return {"domain": "retrieval", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_retrieval_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("retrieval-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="retrieval-attester", ttl_secs=ttl_secs)

def audit_bind_retrieval_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("retrieval-") and "attester" in p.roles and p.alive()
    return {"domain": "retrieval", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_retrieval_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("retrieval-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="retrieval-admin", ttl_secs=ttl_secs)

def audit_bind_retrieval_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("retrieval-") and "admin" in p.roles and p.alive()
    return {"domain": "retrieval", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_pipeline_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("pipeline-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="pipeline-anon", ttl_secs=ttl_secs)

def audit_bind_pipeline_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("pipeline-") and "anon" in p.roles and p.alive()
    return {"domain": "pipeline", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_pipeline_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("pipeline-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="pipeline-operator", ttl_secs=ttl_secs)

def audit_bind_pipeline_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("pipeline-") and "operator" in p.roles and p.alive()
    return {"domain": "pipeline", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_pipeline_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("pipeline-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="pipeline-attester", ttl_secs=ttl_secs)

def audit_bind_pipeline_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("pipeline-") and "attester" in p.roles and p.alive()
    return {"domain": "pipeline", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_pipeline_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("pipeline-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="pipeline-admin", ttl_secs=ttl_secs)

def audit_bind_pipeline_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("pipeline-") and "admin" in p.roles and p.alive()
    return {"domain": "pipeline", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_intelligence_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("intelligence-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="intelligence-anon", ttl_secs=ttl_secs)

def audit_bind_intelligence_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("intelligence-") and "anon" in p.roles and p.alive()
    return {"domain": "intelligence", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_intelligence_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("intelligence-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="intelligence-operator", ttl_secs=ttl_secs)

def audit_bind_intelligence_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("intelligence-") and "operator" in p.roles and p.alive()
    return {"domain": "intelligence", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_intelligence_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("intelligence-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="intelligence-attester", ttl_secs=ttl_secs)

def audit_bind_intelligence_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("intelligence-") and "attester" in p.roles and p.alive()
    return {"domain": "intelligence", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_intelligence_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("intelligence-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="intelligence-admin", ttl_secs=ttl_secs)

def audit_bind_intelligence_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("intelligence-") and "admin" in p.roles and p.alive()
    return {"domain": "intelligence", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_resilience_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("resilience-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="resilience-anon", ttl_secs=ttl_secs)

def audit_bind_resilience_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("resilience-") and "anon" in p.roles and p.alive()
    return {"domain": "resilience", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_resilience_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("resilience-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="resilience-operator", ttl_secs=ttl_secs)

def audit_bind_resilience_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("resilience-") and "operator" in p.roles and p.alive()
    return {"domain": "resilience", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_resilience_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("resilience-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="resilience-attester", ttl_secs=ttl_secs)

def audit_bind_resilience_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("resilience-") and "attester" in p.roles and p.alive()
    return {"domain": "resilience", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_resilience_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("resilience-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="resilience-admin", ttl_secs=ttl_secs)

def audit_bind_resilience_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("resilience-") and "admin" in p.roles and p.alive()
    return {"domain": "resilience", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_context_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("context-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="context-anon", ttl_secs=ttl_secs)

def audit_bind_context_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("context-") and "anon" in p.roles and p.alive()
    return {"domain": "context", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_context_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("context-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="context-operator", ttl_secs=ttl_secs)

def audit_bind_context_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("context-") and "operator" in p.roles and p.alive()
    return {"domain": "context", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_context_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("context-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="context-attester", ttl_secs=ttl_secs)

def audit_bind_context_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("context-") and "attester" in p.roles and p.alive()
    return {"domain": "context", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_context_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("context-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="context-admin", ttl_secs=ttl_secs)

def audit_bind_context_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("context-") and "admin" in p.roles and p.alive()
    return {"domain": "context", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_ledger_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("ledger-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="ledger-anon", ttl_secs=ttl_secs)

def audit_bind_ledger_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("ledger-") and "anon" in p.roles and p.alive()
    return {"domain": "ledger", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_ledger_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("ledger-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="ledger-operator", ttl_secs=ttl_secs)

def audit_bind_ledger_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("ledger-") and "operator" in p.roles and p.alive()
    return {"domain": "ledger", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_ledger_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("ledger-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="ledger-attester", ttl_secs=ttl_secs)

def audit_bind_ledger_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("ledger-") and "attester" in p.roles and p.alive()
    return {"domain": "ledger", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_ledger_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("ledger-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="ledger-admin", ttl_secs=ttl_secs)

def audit_bind_ledger_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("ledger-") and "admin" in p.roles and p.alive()
    return {"domain": "ledger", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_scheduler_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("scheduler-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="scheduler-anon", ttl_secs=ttl_secs)

def audit_bind_scheduler_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("scheduler-") and "anon" in p.roles and p.alive()
    return {"domain": "scheduler", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_scheduler_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("scheduler-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="scheduler-operator", ttl_secs=ttl_secs)

def audit_bind_scheduler_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("scheduler-") and "operator" in p.roles and p.alive()
    return {"domain": "scheduler", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_scheduler_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("scheduler-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="scheduler-attester", ttl_secs=ttl_secs)

def audit_bind_scheduler_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("scheduler-") and "attester" in p.roles and p.alive()
    return {"domain": "scheduler", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_scheduler_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("scheduler-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="scheduler-admin", ttl_secs=ttl_secs)

def audit_bind_scheduler_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("scheduler-") and "admin" in p.roles and p.alive()
    return {"domain": "scheduler", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_genesis_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("genesis-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="genesis-anon", ttl_secs=ttl_secs)

def audit_bind_genesis_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("genesis-") and "anon" in p.roles and p.alive()
    return {"domain": "genesis", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_genesis_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("genesis-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="genesis-operator", ttl_secs=ttl_secs)

def audit_bind_genesis_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("genesis-") and "operator" in p.roles and p.alive()
    return {"domain": "genesis", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_genesis_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("genesis-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="genesis-attester", ttl_secs=ttl_secs)

def audit_bind_genesis_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("genesis-") and "attester" in p.roles and p.alive()
    return {"domain": "genesis", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_genesis_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("genesis-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="genesis-admin", ttl_secs=ttl_secs)

def audit_bind_genesis_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("genesis-") and "admin" in p.roles and p.alive()
    return {"domain": "genesis", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_capabilities_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("capabilities-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="capabilities-anon", ttl_secs=ttl_secs)

def audit_bind_capabilities_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("capabilities-") and "anon" in p.roles and p.alive()
    return {"domain": "capabilities", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_capabilities_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("capabilities-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="capabilities-operator", ttl_secs=ttl_secs)

def audit_bind_capabilities_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("capabilities-") and "operator" in p.roles and p.alive()
    return {"domain": "capabilities", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_capabilities_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("capabilities-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="capabilities-attester", ttl_secs=ttl_secs)

def audit_bind_capabilities_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("capabilities-") and "attester" in p.roles and p.alive()
    return {"domain": "capabilities", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_capabilities_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("capabilities-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="capabilities-admin", ttl_secs=ttl_secs)

def audit_bind_capabilities_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("capabilities-") and "admin" in p.roles and p.alive()
    return {"domain": "capabilities", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_interface_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("interface-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="interface-anon", ttl_secs=ttl_secs)

def audit_bind_interface_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("interface-") and "anon" in p.roles and p.alive()
    return {"domain": "interface", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_interface_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("interface-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="interface-operator", ttl_secs=ttl_secs)

def audit_bind_interface_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("interface-") and "operator" in p.roles and p.alive()
    return {"domain": "interface", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_interface_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("interface-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="interface-attester", ttl_secs=ttl_secs)

def audit_bind_interface_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("interface-") and "attester" in p.roles and p.alive()
    return {"domain": "interface", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_interface_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("interface-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="interface-admin", ttl_secs=ttl_secs)

def audit_bind_interface_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("interface-") and "admin" in p.roles and p.alive()
    return {"domain": "interface", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_auth_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("auth-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="auth-anon", ttl_secs=ttl_secs)

def audit_bind_auth_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("auth-") and "anon" in p.roles and p.alive()
    return {"domain": "auth", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_auth_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("auth-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="auth-operator", ttl_secs=ttl_secs)

def audit_bind_auth_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("auth-") and "operator" in p.roles and p.alive()
    return {"domain": "auth", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_auth_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("auth-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="auth-attester", ttl_secs=ttl_secs)

def audit_bind_auth_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("auth-") and "attester" in p.roles and p.alive()
    return {"domain": "auth", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_auth_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("auth-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="auth-admin", ttl_secs=ttl_secs)

def audit_bind_auth_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("auth-") and "admin" in p.roles and p.alive()
    return {"domain": "auth", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_cognition_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("cognition-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="cognition-anon", ttl_secs=ttl_secs)

def audit_bind_cognition_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("cognition-") and "anon" in p.roles and p.alive()
    return {"domain": "cognition", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_cognition_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("cognition-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="cognition-operator", ttl_secs=ttl_secs)

def audit_bind_cognition_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("cognition-") and "operator" in p.roles and p.alive()
    return {"domain": "cognition", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_cognition_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("cognition-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="cognition-attester", ttl_secs=ttl_secs)

def audit_bind_cognition_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("cognition-") and "attester" in p.roles and p.alive()
    return {"domain": "cognition", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_cognition_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("cognition-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="cognition-admin", ttl_secs=ttl_secs)

def audit_bind_cognition_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("cognition-") and "admin" in p.roles and p.alive()
    return {"domain": "cognition", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_fabric_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("fabric-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="fabric-anon", ttl_secs=ttl_secs)

def audit_bind_fabric_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("fabric-") and "anon" in p.roles and p.alive()
    return {"domain": "fabric", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_fabric_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("fabric-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="fabric-operator", ttl_secs=ttl_secs)

def audit_bind_fabric_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("fabric-") and "operator" in p.roles and p.alive()
    return {"domain": "fabric", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_fabric_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("fabric-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="fabric-attester", ttl_secs=ttl_secs)

def audit_bind_fabric_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("fabric-") and "attester" in p.roles and p.alive()
    return {"domain": "fabric", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_fabric_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("fabric-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="fabric-admin", ttl_secs=ttl_secs)

def audit_bind_fabric_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("fabric-") and "admin" in p.roles and p.alive()
    return {"domain": "fabric", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_legions_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("legions-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="legions-anon", ttl_secs=ttl_secs)

def audit_bind_legions_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("legions-") and "anon" in p.roles and p.alive()
    return {"domain": "legions", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_legions_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("legions-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="legions-operator", ttl_secs=ttl_secs)

def audit_bind_legions_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("legions-") and "operator" in p.roles and p.alive()
    return {"domain": "legions", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_legions_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("legions-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="legions-attester", ttl_secs=ttl_secs)

def audit_bind_legions_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("legions-") and "attester" in p.roles and p.alive()
    return {"domain": "legions", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_legions_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("legions-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="legions-admin", ttl_secs=ttl_secs)

def audit_bind_legions_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("legions-") and "admin" in p.roles and p.alive()
    return {"domain": "legions", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_governance_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("governance-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="governance-anon", ttl_secs=ttl_secs)

def audit_bind_governance_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("governance-") and "anon" in p.roles and p.alive()
    return {"domain": "governance", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_governance_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("governance-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="governance-operator", ttl_secs=ttl_secs)

def audit_bind_governance_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("governance-") and "operator" in p.roles and p.alive()
    return {"domain": "governance", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_governance_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("governance-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="governance-attester", ttl_secs=ttl_secs)

def audit_bind_governance_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("governance-") and "attester" in p.roles and p.alive()
    return {"domain": "governance", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_governance_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("governance-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="governance-admin", ttl_secs=ttl_secs)

def audit_bind_governance_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("governance-") and "admin" in p.roles and p.alive()
    return {"domain": "governance", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_lafs_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("lafs-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="lafs-anon", ttl_secs=ttl_secs)

def audit_bind_lafs_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("lafs-") and "anon" in p.roles and p.alive()
    return {"domain": "lafs", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_lafs_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("lafs-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="lafs-operator", ttl_secs=ttl_secs)

def audit_bind_lafs_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("lafs-") and "operator" in p.roles and p.alive()
    return {"domain": "lafs", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_lafs_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("lafs-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="lafs-attester", ttl_secs=ttl_secs)

def audit_bind_lafs_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("lafs-") and "attester" in p.roles and p.alive()
    return {"domain": "lafs", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_lafs_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("lafs-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="lafs-admin", ttl_secs=ttl_secs)

def audit_bind_lafs_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("lafs-") and "admin" in p.roles and p.alive()
    return {"domain": "lafs", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_studio_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("studio-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="studio-anon", ttl_secs=ttl_secs)

def audit_bind_studio_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("studio-") and "anon" in p.roles and p.alive()
    return {"domain": "studio", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_studio_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("studio-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="studio-operator", ttl_secs=ttl_secs)

def audit_bind_studio_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("studio-") and "operator" in p.roles and p.alive()
    return {"domain": "studio", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_studio_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("studio-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="studio-attester", ttl_secs=ttl_secs)

def audit_bind_studio_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("studio-") and "attester" in p.roles and p.alive()
    return {"domain": "studio", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_studio_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("studio-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="studio-admin", ttl_secs=ttl_secs)

def audit_bind_studio_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("studio-") and "admin" in p.roles and p.alive()
    return {"domain": "studio", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_court_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("court-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="court-anon", ttl_secs=ttl_secs)

def audit_bind_court_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("court-") and "anon" in p.roles and p.alive()
    return {"domain": "court", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_court_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("court-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="court-operator", ttl_secs=ttl_secs)

def audit_bind_court_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("court-") and "operator" in p.roles and p.alive()
    return {"domain": "court", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_court_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("court-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="court-attester", ttl_secs=ttl_secs)

def audit_bind_court_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("court-") and "attester" in p.roles and p.alive()
    return {"domain": "court", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_court_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("court-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="court-admin", ttl_secs=ttl_secs)

def audit_bind_court_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("court-") and "admin" in p.roles and p.alive()
    return {"domain": "court", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_treasury_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("treasury-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="treasury-anon", ttl_secs=ttl_secs)

def audit_bind_treasury_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("treasury-") and "anon" in p.roles and p.alive()
    return {"domain": "treasury", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_treasury_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("treasury-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="treasury-operator", ttl_secs=ttl_secs)

def audit_bind_treasury_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("treasury-") and "operator" in p.roles and p.alive()
    return {"domain": "treasury", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_treasury_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("treasury-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="treasury-attester", ttl_secs=ttl_secs)

def audit_bind_treasury_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("treasury-") and "attester" in p.roles and p.alive()
    return {"domain": "treasury", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_treasury_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("treasury-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="treasury-admin", ttl_secs=ttl_secs)

def audit_bind_treasury_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("treasury-") and "admin" in p.roles and p.alive()
    return {"domain": "treasury", "role": "admin", "ok": ok, "principal": p.as_dict()}

def bind_reputation_anon(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("reputation-anon", roles=("anon",), scopes=("read", "write") if "anon" != "anon" else ("read",), attester="reputation-anon", ttl_secs=ttl_secs)

def audit_bind_reputation_anon(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("reputation-") and "anon" in p.roles and p.alive()
    return {"domain": "reputation", "role": "anon", "ok": ok, "principal": p.as_dict()}

def bind_reputation_operator(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("reputation-operator", roles=("operator",), scopes=("read", "write") if "operator" != "anon" else ("read",), attester="reputation-operator", ttl_secs=ttl_secs)

def audit_bind_reputation_operator(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("reputation-") and "operator" in p.roles and p.alive()
    return {"domain": "reputation", "role": "operator", "ok": ok, "principal": p.as_dict()}

def bind_reputation_attester(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("reputation-attester", roles=("attester",), scopes=("read", "write") if "attester" != "anon" else ("read",), attester="reputation-attester", ttl_secs=ttl_secs)

def audit_bind_reputation_attester(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("reputation-") and "attester" in p.roles and p.alive()
    return {"domain": "reputation", "role": "attester", "ok": ok, "principal": p.as_dict()}

def bind_reputation_admin(*, ttl_secs: int = 600) -> Principal:
    return bind_principal("reputation-admin", roles=("admin",), scopes=("read", "write") if "admin" != "anon" else ("read",), attester="reputation-admin", ttl_secs=ttl_secs)

def audit_bind_reputation_admin(p: Principal) -> Dict[str, object]:
    ok = p.name.startswith("reputation-") and "admin" in p.roles and p.alive()
    return {"domain": "reputation", "role": "admin", "ok": ok, "principal": p.as_dict()}

