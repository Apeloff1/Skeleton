"""Request pipeline stages — ordered glue (no lifespan edits)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from skeleton.request_pipeline.principal import Principal, bind_principal
from skeleton.request_pipeline.scopes import evaluate_role, evaluate_scope


@dataclass(frozen=True)
class PipelineStage:
    name: str
    purpose: str
    required: bool = True

    def as_dict(self) -> Dict[str, object]:
        return {"name": self.name, "purpose": self.purpose, "required": self.required}


@dataclass
class RequestPipeline:
    stages: Tuple[PipelineStage, ...] = ()
    label: str = "default"

    def as_dict(self) -> Dict[str, object]:
        return {"label": self.label, "stages": [s.as_dict() for s in self.stages]}

    def names(self) -> List[str]:
        return [s.name for s in self.stages]


def default_pipeline() -> RequestPipeline:
    return RequestPipeline(
        stages=(
            PipelineStage("correlate", "Attach / mint X-Request-Id"),
            PipelineStage("authenticate", "Bind principal from seal/token"),
            PipelineStage("authorize", "Scope + role gates"),
            PipelineStage("admit_write", "AdaptiveGate + Chaos on mutate"),
            PipelineStage("body_bound", "Reject oversized bodies"),
            PipelineStage("audit", "WORM append before service"),
            PipelineStage("route", "Dispatch to domain handler"),
            PipelineStage("respond", "Normalize response + headers"),
        ),
        label="default",
    )


def run_pipeline_dry(
    *,
    path: str,
    method: str,
    principal: Optional[Principal] = None,
    required_scopes: Sequence[str] = (),
    required_roles: Sequence[str] = (),
) -> Dict[str, object]:
    """Pure dry-run of authN/Z stages — no I/O."""
    pipe = default_pipeline()
    log: List[Dict[str, object]] = []
    p = principal
    for stage in pipe.stages:
        if stage.name == "authenticate":
            ok = p is not None and p.alive()
            log.append({"stage": stage.name, "ok": ok})
            if not ok:
                return {"ok": False, "failed_at": stage.name, "log": log}
        elif stage.name == "authorize":
            assert p is not None
            sc = evaluate_scope(p, required_scopes) if required_scopes else {"ok": True}
            rl = evaluate_role(p, required_roles) if required_roles else {"ok": True}
            ok = bool(sc.get("ok")) and bool(rl.get("ok"))
            log.append({"stage": stage.name, "ok": ok, "scope": sc, "role": rl})
            if not ok:
                return {"ok": False, "failed_at": stage.name, "log": log}
        elif stage.name == "admit_write":
            mutating = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            log.append({"stage": stage.name, "ok": True, "mutating": mutating})
        else:
            log.append({"stage": stage.name, "ok": True})
    return {"ok": True, "failed_at": None, "log": log, "path": path, "method": method}

def pipeline_for_forge() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="forge")

def dry_run_forge_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("forge-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/forge/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_forge_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("forge-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/forge/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_gameforge() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="gameforge")

def dry_run_gameforge_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("gameforge-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/gameforge/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_gameforge_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("gameforge-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/gameforge/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_swarm() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="swarm")

def dry_run_swarm_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("swarm-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/swarm/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_swarm_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("swarm-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/swarm/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_jeeves() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="jeeves")

def dry_run_jeeves_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("jeeves-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/jeeves/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_jeeves_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("jeeves-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/jeeves/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_memory() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="memory")

def dry_run_memory_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("memory-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/memory/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_memory_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("memory-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/memory/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_retrieval() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="retrieval")

def dry_run_retrieval_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("retrieval-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/retrieval/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_retrieval_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("retrieval-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/retrieval/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_pipeline() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="pipeline")

def dry_run_pipeline_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("pipeline-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/pipeline/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_pipeline_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("pipeline-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/pipeline/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_intelligence() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="intelligence")

def dry_run_intelligence_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("intelligence-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/intelligence/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_intelligence_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("intelligence-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/intelligence/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_resilience() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="resilience")

def dry_run_resilience_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("resilience-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/resilience/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_resilience_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("resilience-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/resilience/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_context() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="context")

def dry_run_context_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("context-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/context/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_context_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("context-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/context/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_ledger() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="ledger")

def dry_run_ledger_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("ledger-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/ledger/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_ledger_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("ledger-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/ledger/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_scheduler() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="scheduler")

def dry_run_scheduler_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("scheduler-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/scheduler/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_scheduler_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("scheduler-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/scheduler/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_genesis() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="genesis")

def dry_run_genesis_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("genesis-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/genesis/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_genesis_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("genesis-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/genesis/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_capabilities() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="capabilities")

def dry_run_capabilities_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("capabilities-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/capabilities/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_capabilities_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("capabilities-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/capabilities/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_interface() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="interface")

def dry_run_interface_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("interface-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/interface/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_interface_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("interface-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/interface/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_auth() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="auth")

def dry_run_auth_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("auth-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/auth/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_auth_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("auth-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/auth/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_cognition() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="cognition")

def dry_run_cognition_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("cognition-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/cognition/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_cognition_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("cognition-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/cognition/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_fabric() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="fabric")

def dry_run_fabric_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("fabric-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/fabric/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_fabric_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("fabric-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/fabric/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_legions() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="legions")

def dry_run_legions_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("legions-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/legions/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_legions_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("legions-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/legions/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_governance() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="governance")

def dry_run_governance_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("governance-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/governance/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_governance_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("governance-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/governance/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_lafs() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="lafs")

def dry_run_lafs_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("lafs-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/lafs/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_lafs_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("lafs-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/lafs/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_studio() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="studio")

def dry_run_studio_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("studio-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/studio/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_studio_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("studio-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/studio/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_court() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="court")

def dry_run_court_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("court-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/court/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_court_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("court-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/court/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_treasury() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="treasury")

def dry_run_treasury_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("treasury-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/treasury/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_treasury_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("treasury-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/treasury/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

def pipeline_for_reputation() -> RequestPipeline:
    base = default_pipeline()
    return RequestPipeline(stages=base.stages, label="reputation")

def dry_run_reputation_get(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("reputation-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/reputation/x", method="GET", principal=p, required_scopes=("read",))

def dry_run_reputation_post(principal: Optional[Principal] = None) -> Dict[str, object]:
    p = principal or bind_principal("reputation-op", roles=("operator",), scopes=("read", "write"))
    return run_pipeline_dry(path="/api/v1/reputation/x", method="POST", principal=p, required_scopes=("write",), required_roles=("operator", "admin"))

