"""Scope / role gates — authZ glue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Optional, Sequence, Set

from skeleton.request_pipeline.principal import Principal


@dataclass(frozen=True)
class ScopeGate:
    required: FrozenSet[str]
    mode: str = "all"  # all | any

    def allows(self, principal: Principal) -> bool:
        if self.mode == "any":
            return bool(self.required & principal.scopes)
        return self.required <= principal.scopes


@dataclass(frozen=True)
class RoleGate:
    required: FrozenSet[str]
    mode: str = "any"

    def allows(self, principal: Principal) -> bool:
        if self.mode == "all":
            return self.required <= principal.roles
        return bool(self.required & principal.roles)


def evaluate_scope(principal: Principal, required: Sequence[str], *, mode: str = "all") -> Dict[str, object]:
    gate = ScopeGate(frozenset(required), mode=mode)
    return {
        "ok": gate.allows(principal),
        "required": sorted(required),
        "have": sorted(principal.scopes),
        "mode": mode,
    }


def evaluate_role(principal: Principal, required: Sequence[str], *, mode: str = "any") -> Dict[str, object]:
    gate = RoleGate(frozenset(required), mode=mode)
    return {
        "ok": gate.allows(principal),
        "required": sorted(required),
        "have": sorted(principal.roles),
        "mode": mode,
    }

# --- generated scope evaluators ---

def scope_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_forge_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_forge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_gameforge_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_gameforge_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_swarm_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_swarm_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_jeeves_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_jeeves_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_memory_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_memory_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_retrieval_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_retrieval_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_pipeline_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_pipeline_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_intelligence_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_intelligence_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_resilience_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_resilience_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_context_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_context_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_ledger_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_ledger_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_scheduler_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_scheduler_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_genesis_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_genesis_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_capabilities_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_capabilities_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_interface_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_interface_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_auth_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_auth_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_cognition_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_cognition_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_fabric_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_fabric_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_legions_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_legions_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_governance_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_governance_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_lafs_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_lafs_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_studio_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_studio_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_court_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_court_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_treasury_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_treasury_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("read",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("write",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_admin(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("admin",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_forge_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:read",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_forge_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("forge:write",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_swarm_read(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:read",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_swarm_write(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("swarm:write",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

def scope_reputation_jeeves_ask(principal: Principal) -> Dict[str, object]:
    return evaluate_scope(principal, ("jeeves:ask",), mode="all")

def role_reputation_operator(principal: Principal) -> Dict[str, object]:
    return evaluate_role(principal, ("operator", "admin"), mode="any")

