"""Deployment, administration, dashboard, and model-operations assurance.

Implements the governance seams for VOL-231..VOL-240 on top of existing
deferred operations primitives.  All outputs are evidence-only; activation,
merge, deployment, and production authority remain external.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json
from .operations_experience import (
    AdminOperation,
    AuditEvent,
    DashboardMetric,
    DashboardProjection,
    ModelOperations,
    ModelRevision,
)
from .research_evaluation import DeploymentProfile


class DeploymentOperationsAssuranceError(ValueError):
    pass


_HEX=frozenset("0123456789abcdef")


def _text(name:str,value:object,*,limit:int=512)->str:
    if (
        not isinstance(value,str) or not value or value!=value.strip()
        or len(value)>limit or any(ord(ch)<32 for ch in value)
    ):
        raise DeploymentOperationsAssuranceError(
            f"{name} must be normalized non-empty text"
        )
    return value


def _texts(name:str,values:Iterable[str],*,allow_empty:bool=False)->tuple[str,...]:
    if isinstance(values,(str,bytes)):
        raise DeploymentOperationsAssuranceError(f"{name} must be a collection")
    result=tuple(sorted({_text(name,value) for value in values}))
    if not result and not allow_empty:
        raise DeploymentOperationsAssuranceError(f"{name} must be non-empty")
    return result


def _integer(name:str,value:object,*,minimum:int=0)->int:
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
        raise DeploymentOperationsAssuranceError(
            f"{name} must be integer >= {minimum}"
        )
    return value


def _sha(name:str,value:object,*,length:int=64)->str:
    text=_text(name,value,limit=length)
    if len(text)!=length or any(ch not in _HEX for ch in text):
        raise DeploymentOperationsAssuranceError(
            f"{name} must be lowercase {length}-character hexadecimal"
        )
    return text


# VOL-231 Edge Deployment -------------------------------------------------


@dataclass(frozen=True,slots=True)
class EdgeResourceTier:
    tier_id:str
    max_model_bytes:int
    max_memory_bytes:int
    max_context_tokens:int
    router_classes:tuple[str,...]
    local_storage_required:bool=True

    def __post_init__(self)->None:
        object.__setattr__(self,"tier_id",_text("tier_id",self.tier_id))
        for name in ("max_model_bytes","max_memory_bytes","max_context_tokens"):
            object.__setattr__(self,name,_integer(name,getattr(self,name),minimum=1))
        object.__setattr__(
            self,"router_classes",_texts("router_class",self.router_classes)
        )
        if not isinstance(self.local_storage_required,bool):
            raise DeploymentOperationsAssuranceError(
                "local_storage_required must be boolean"
            )


@dataclass(frozen=True,slots=True)
class EdgeDeploymentEvidence:
    profile_id:str
    tier_id:str
    model_digest:str
    model_bytes:int
    memory_bytes:int
    context_tokens:int
    router_class:str
    eligible:bool
    blockers:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        for name in ("profile_id","tier_id","router_class"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(self,"model_digest",_sha("model_digest",self.model_digest))
        for name in ("model_bytes","memory_bytes","context_tokens"):
            object.__setattr__(self,name,_integer(name,getattr(self,name),minimum=1))
        if not isinstance(self.eligible,bool):
            raise DeploymentOperationsAssuranceError("eligible must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if self.eligible!=(not self.blockers):
            raise DeploymentOperationsAssuranceError(
                "edge eligibility must match blockers"
            )
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "edge evidence cannot grant production authority"
            )


def qualify_edge_deployment(
    profile:DeploymentProfile,
    tier:EdgeResourceTier,
    *,
    model_digest:str,
    model_bytes:int,
    memory_bytes:int,
    context_tokens:int,
    router_class:str,
    local_storage_present:bool,
)->EdgeDeploymentEvidence:
    if profile.network_mode=="air_gapped":
        raise DeploymentOperationsAssuranceError(
            "edge deployment uses offline profile, not air-gap qualification"
        )
    blockers=[]
    mb=_integer("model_bytes",model_bytes,minimum=1)
    memory=_integer("memory_bytes",memory_bytes,minimum=1)
    context=_integer("context_tokens",context_tokens,minimum=1)
    router=_text("router_class",router_class)
    if mb>tier.max_model_bytes: blockers.append("model-size-exceeded")
    if memory>tier.max_memory_bytes: blockers.append("memory-exceeded")
    if context>tier.max_context_tokens: blockers.append("context-exceeded")
    if router not in set(tier.router_classes): blockers.append("router-class-unsupported")
    if tier.local_storage_required and not local_storage_present:
        blockers.append("local-storage-missing")
    return EdgeDeploymentEvidence(
        profile.profile_id,tier.tier_id,_sha("model_digest",model_digest),
        mb,memory,context,router,not blockers,tuple(sorted(blockers)),
    )


# VOL-232 Enterprise Deployment ------------------------------------------


@dataclass(frozen=True,slots=True)
class EnterpriseTopology:
    topology_id:str
    region_ids:tuple[str,...]
    minimum_replicas:int
    sso_required:bool=True
    audit_required:bool=True
    backup_required:bool=True

    def __post_init__(self)->None:
        object.__setattr__(self,"topology_id",_text("topology_id",self.topology_id))
        object.__setattr__(self,"region_ids",_texts("region_id",self.region_ids))
        object.__setattr__(
            self,"minimum_replicas",_integer("minimum_replicas",self.minimum_replicas,minimum=1)
        )
        for name in ("sso_required","audit_required","backup_required"):
            if getattr(self,name) is not True:
                raise DeploymentOperationsAssuranceError(
                    f"enterprise topology requires {name}"
                )


@dataclass(frozen=True,slots=True)
class EnterpriseAcceptanceEvidence:
    topology_id:str
    replica_count:int
    sso_verified:bool
    audit_verified:bool
    backup_verified:bool
    residency_verified:bool
    accepted:bool
    blockers:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"topology_id",_text("topology_id",self.topology_id))
        object.__setattr__(self,"replica_count",_integer("replica_count",self.replica_count))
        for name in ("sso_verified","audit_verified","backup_verified","residency_verified","accepted"):
            if not isinstance(getattr(self,name),bool):
                raise DeploymentOperationsAssuranceError(f"{name} must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if self.accepted!=(not self.blockers):
            raise DeploymentOperationsAssuranceError(
                "enterprise acceptance must match blockers"
            )
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "enterprise evidence cannot grant production authority"
            )


def assess_enterprise_topology(
    topology:EnterpriseTopology,
    *,
    replica_count:int,
    sso_verified:bool,
    audit_verified:bool,
    backup_verified:bool,
    residency_verified:bool,
)->EnterpriseAcceptanceEvidence:
    replicas=_integer("replica_count",replica_count)
    blockers=[]
    if replicas<topology.minimum_replicas: blockers.append("replica-count-below-topology")
    if not sso_verified: blockers.append("sso-unverified")
    if not audit_verified: blockers.append("audit-unverified")
    if not backup_verified: blockers.append("backup-unverified")
    if not residency_verified: blockers.append("residency-unverified")
    return EnterpriseAcceptanceEvidence(
        topology.topology_id,replicas,bool(sso_verified),bool(audit_verified),
        bool(backup_verified),bool(residency_verified),not blockers,tuple(sorted(blockers)),
    )


# VOL-233 Identity Federation --------------------------------------------


@dataclass(frozen=True,slots=True)
class FederatedPrincipal:
    issuer_id:str
    external_subject:str
    principal_id:str
    tenant_id:str
    group_ids:tuple[str,...]
    mapping_digest:str

    def __post_init__(self)->None:
        for name in ("issuer_id","external_subject","principal_id","tenant_id"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(self,"group_ids",_texts("group_id",self.group_ids,allow_empty=True))
        object.__setattr__(self,"mapping_digest",_sha("mapping_digest",self.mapping_digest))


@dataclass(frozen=True,slots=True)
class FederationSession:
    session_id:str
    principal_id:str
    issued_at_ms:int
    expires_at_ms:int
    revocation_epoch:int
    observed_revocation_epoch:int
    active:bool

    def __post_init__(self)->None:
        for name in ("session_id","principal_id"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        for name in ("issued_at_ms","expires_at_ms","revocation_epoch","observed_revocation_epoch"):
            object.__setattr__(self,name,_integer(name,getattr(self,name)))
        if self.expires_at_ms<=self.issued_at_ms:
            raise DeploymentOperationsAssuranceError("federation session expiry must advance")
        if not isinstance(self.active,bool):
            raise DeploymentOperationsAssuranceError("active must be boolean")


def evaluate_federated_session(
    principal:FederatedPrincipal,
    *,
    session_id:str,
    issued_at_ms:int,
    expires_at_ms:int,
    now_ms:int,
    revocation_epoch:int,
    observed_revocation_epoch:int,
)->FederationSession:
    now=_integer("now_ms",now_ms)
    issued=_integer("issued_at_ms",issued_at_ms)
    expires=_integer("expires_at_ms",expires_at_ms)
    revoked=_integer("revocation_epoch",revocation_epoch)
    observed=_integer("observed_revocation_epoch",observed_revocation_epoch)
    active=(
        issued<=now<expires
        and observed==revoked
    )
    return FederationSession(
        _text("session_id",session_id),principal.principal_id,
        issued,expires,revoked,observed,active,
    )


# VOL-234 Administration Plane -------------------------------------------


@dataclass(frozen=True,slots=True)
class AdminCapability:
    capability_id:str
    action:str
    impact:str
    required_approvals:int
    break_glass_allowed:bool=False

    def __post_init__(self)->None:
        for name in ("capability_id","action"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        if self.impact not in {"low","medium","high","critical"}:
            raise DeploymentOperationsAssuranceError("unsupported admin impact")
        object.__setattr__(
            self,"required_approvals",_integer("required_approvals",self.required_approvals,minimum=1)
        )
        if self.impact in {"high","critical"} and self.required_approvals<2:
            raise DeploymentOperationsAssuranceError(
                "high-impact admin capability requires two-person approval"
            )
        if not isinstance(self.break_glass_allowed,bool):
            raise DeploymentOperationsAssuranceError(
                "break_glass_allowed must be boolean"
            )


@dataclass(frozen=True,slots=True)
class AdminDecisionEvidence:
    operation_digest:str
    capability_id:str
    approver_ids:tuple[str,...]
    break_glass:bool
    allowed:bool
    blockers:tuple[str,...]
    mutating_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"operation_digest",_sha("operation_digest",self.operation_digest))
        object.__setattr__(self,"capability_id",_text("capability_id",self.capability_id))
        object.__setattr__(self,"approver_ids",_texts("approver_id",self.approver_ids,allow_empty=True))
        if not isinstance(self.break_glass,bool) or not isinstance(self.allowed,bool):
            raise DeploymentOperationsAssuranceError("admin decision booleans required")
        object.__setattr__(self,"blockers",_texts("blocker",self.blockers,allow_empty=True))
        if self.allowed!=(not self.blockers):
            raise DeploymentOperationsAssuranceError(
                "admin allowed state must match blockers"
            )
        if self.mutating_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "admin decision evidence cannot self-grant mutation authority"
            )


def decide_admin_operation(
    operation:AdminOperation,
    capability:AdminCapability,
    *,
    approver_ids:Iterable[str],
    break_glass:bool=False,
)->AdminDecisionEvidence:
    approvers=_texts("approver_id",approver_ids,allow_empty=True)
    blockers=[]
    if operation.action!=capability.action: blockers.append("capability-action-mismatch")
    if not operation.approved: blockers.append("operation-not-preapproved")
    if len(approvers)<capability.required_approvals: blockers.append("insufficient-approvals")
    if break_glass and not capability.break_glass_allowed:
        blockers.append("break-glass-not-allowed")
    digest=sha256_json({
        "operation_id":operation.operation_id,
        "principal_id":operation.principal_id,
        "action":operation.action,
        "preflight_digest":operation.preflight_digest,
        "approved":operation.approved,
    })
    return AdminDecisionEvidence(
        digest,capability.capability_id,approvers,bool(break_glass),
        not blockers,tuple(sorted(blockers)),
    )


# VOL-235 Audit UI --------------------------------------------------------


@dataclass(frozen=True,slots=True)
class AuditProjectionRecord:
    sequence:int
    event_id:str
    actor_id:str
    action:str
    subject_id:str
    payload_digest:str
    provenance_digest:str
    trace_id:str

    def __post_init__(self)->None:
        object.__setattr__(self,"sequence",_integer("sequence",self.sequence,minimum=1))
        for name in ("event_id","actor_id","action","subject_id","trace_id"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        for name in ("payload_digest","provenance_digest"):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))


def project_audit_event(
    event:AuditEvent,
    *,
    provenance_digest:str,
    trace_id:str,
)->AuditProjectionRecord:
    return AuditProjectionRecord(
        event.sequence,event.event_id,event.actor_id,event.action,event.subject_id,
        event.payload_digest,_sha("provenance_digest",provenance_digest),
        _text("trace_id",trace_id),
    )


# VOL-236 Operations Dashboard -------------------------------------------


@dataclass(frozen=True,slots=True)
class OperationsDashboardEvidence:
    metric_ids:tuple[str,...]
    runbook_refs:tuple[str,...]
    snapshot_digest:str
    stale_metric_ids:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"metric_ids",_texts("metric_id",self.metric_ids))
        object.__setattr__(self,"runbook_refs",_texts("runbook_ref",self.runbook_refs))
        object.__setattr__(self,"snapshot_digest",_sha("snapshot_digest",self.snapshot_digest))
        object.__setattr__(
            self,"stale_metric_ids",_texts("stale_metric_id",self.stale_metric_ids,allow_empty=True)
        )
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "dashboard evidence cannot grant production authority"
            )


def build_operations_dashboard(
    projection:DashboardProjection,
    metrics:Sequence[DashboardMetric],
    *,
    now:int,
    runbook_refs:Iterable[str],
)->OperationsDashboardEvidence:
    for metric in metrics:
        projection.update(metric)
    snapshot=projection.snapshot(_integer("now",now))
    stale=tuple(sorted({item.metric_id for item in metrics}-set(snapshot)))
    digest=sha256_json({
        "metrics":{
            key:{
                "value":value.value,"unit":value.unit,"updated_at":value.updated_at
            }
            for key,value in sorted(snapshot.items())
        }
    })
    return OperationsDashboardEvidence(
        tuple(sorted(snapshot)),tuple(runbook_refs),digest,stale,
    )


# VOL-237 Agent Operations Dashboard -------------------------------------


@dataclass(frozen=True,slots=True)
class AgentOpsRecord:
    agent_id:str
    task_id:str
    state:str
    authority_digest:str
    human_control_receipt_digest:str|None

    def __post_init__(self)->None:
        for name in ("agent_id","task_id","state"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(self,"authority_digest",_sha("authority_digest",self.authority_digest))
        if self.human_control_receipt_digest is not None:
            object.__setattr__(
                self,"human_control_receipt_digest",
                _sha("human_control_receipt_digest",self.human_control_receipt_digest),
            )
        if self.state in {"paused","stopped","overridden"} and self.human_control_receipt_digest is None:
            raise DeploymentOperationsAssuranceError(
                "human-controlled agent state requires control receipt"
            )


@dataclass(frozen=True,slots=True)
class AgentOpsProjection:
    records:tuple[AgentOpsRecord,...]
    projection_digest:str

    def __post_init__(self)->None:
        if not self.records:
            raise DeploymentOperationsAssuranceError("agent ops projection cannot be empty")
        ids=[(item.agent_id,item.task_id) for item in self.records]
        if len(ids)!=len(set(ids)):
            raise DeploymentOperationsAssuranceError("duplicate agent/task projection")
        object.__setattr__(
            self,"records",tuple(sorted(self.records,key=lambda item:(item.agent_id,item.task_id)))
        )
        object.__setattr__(self,"projection_digest",_sha("projection_digest",self.projection_digest))


def build_agent_ops_projection(records:Sequence[AgentOpsRecord])->AgentOpsProjection:
    canonical=[
        {
            "agent_id":item.agent_id,"task_id":item.task_id,"state":item.state,
            "authority_digest":item.authority_digest,
            "human_control_receipt_digest":item.human_control_receipt_digest,
        }
        for item in sorted(records,key=lambda item:(item.agent_id,item.task_id))
    ]
    return AgentOpsProjection(tuple(records),sha256_json(canonical))


# VOL-238 Research Dashboard ---------------------------------------------


@dataclass(frozen=True,slots=True)
class ResearchDashboardEvidence:
    research_backlog_digest:str
    citation_graph_digest:str
    experiment_graph_digest:str
    freshness_epoch:int
    production_authority:bool=False

    def __post_init__(self)->None:
        for name in (
            "research_backlog_digest","citation_graph_digest","experiment_graph_digest"
        ):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))
        object.__setattr__(
            self,"freshness_epoch",_integer("freshness_epoch",self.freshness_epoch)
        )
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "research dashboard cannot grant production authority"
            )

    @property
    def digest(self)->str:
        return sha256_json({
            "research_backlog_digest":self.research_backlog_digest,
            "citation_graph_digest":self.citation_graph_digest,
            "experiment_graph_digest":self.experiment_graph_digest,
            "freshness_epoch":self.freshness_epoch,
            "production_authority":False,
        })


# VOL-239 Model Operations ------------------------------------------------


@dataclass(frozen=True,slots=True)
class ModelOperationEvidence:
    model_id:str
    version:int
    artifact_digest:str
    eval_digest:str
    router_gate_digest:str
    release_gate_digest:str
    eligible_for_activation:bool
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"model_id",_text("model_id",self.model_id))
        object.__setattr__(self,"version",_integer("version",self.version,minimum=1))
        for name in (
            "artifact_digest","eval_digest","router_gate_digest","release_gate_digest"
        ):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))
        if not isinstance(self.eligible_for_activation,bool):
            raise DeploymentOperationsAssuranceError(
                "eligible_for_activation must be boolean"
            )
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "model ops evidence cannot grant production authority"
            )


def register_model_operation(
    registry:ModelOperations,
    revision:ModelRevision,
    *,
    router_gate_digest:str,
    release_gate_digest:str,
)->ModelOperationEvidence:
    registry.register(revision)
    eligible=revision.status in {"qualified","active"}
    return ModelOperationEvidence(
        revision.model_id,revision.version,revision.artifact_digest,revision.eval_digest,
        _sha("router_gate_digest",router_gate_digest),
        _sha("release_gate_digest",release_gate_digest),
        eligible,
    )


# VOL-240 Model Rollback --------------------------------------------------


@dataclass(frozen=True,slots=True)
class ModelRollbackFence:
    model_id:str
    from_version:int
    target_version:int
    deployment_registry_digest:str
    expected_active_artifact_digest:str
    rollback_plan_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"model_id",_text("model_id",self.model_id))
        object.__setattr__(self,"from_version",_integer("from_version",self.from_version,minimum=1))
        object.__setattr__(self,"target_version",_integer("target_version",self.target_version,minimum=1))
        if self.target_version>=self.from_version:
            raise DeploymentOperationsAssuranceError(
                "rollback target must precede active version"
            )
        for name in (
            "deployment_registry_digest","expected_active_artifact_digest","rollback_plan_digest"
        ):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))


@dataclass(frozen=True,slots=True)
class ModelRollbackEvidence:
    fence_digest:str
    target_artifact_digest:str
    target_eval_digest:str
    eligible:bool
    reason_code:str
    production_authority:bool=False

    def __post_init__(self)->None:
        for name in ("fence_digest","target_artifact_digest","target_eval_digest"):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))
        if not isinstance(self.eligible,bool):
            raise DeploymentOperationsAssuranceError("eligible must be boolean")
        object.__setattr__(self,"reason_code",_text("reason_code",self.reason_code))
        if self.production_authority is not False:
            raise DeploymentOperationsAssuranceError(
                "rollback evidence cannot grant production authority"
            )


def qualify_model_rollback(
    registry:ModelOperations,
    fence:ModelRollbackFence,
    *,
    active_revision:ModelRevision,
    target_revision:ModelRevision,
)->ModelRollbackEvidence:
    if active_revision.model_id!=fence.model_id or target_revision.model_id!=fence.model_id:
        raise DeploymentOperationsAssuranceError("rollback model identity mismatch")
    if active_revision.version!=fence.from_version:
        raise DeploymentOperationsAssuranceError("rollback active version fence mismatch")
    if active_revision.artifact_digest!=fence.expected_active_artifact_digest:
        raise DeploymentOperationsAssuranceError("rollback active artifact fence mismatch")
    if target_revision.version!=fence.target_version:
        raise DeploymentOperationsAssuranceError("rollback target version fence mismatch")
    # Qualification is evidence-only. Do not mutate registry activation/history here.
    # The deployment-registry digest on the fence is the external membership proof.
    del registry
    eligible=target_revision.status in {"qualified","active"}
    return ModelRollbackEvidence(
        sha256_json({
            "model_id":fence.model_id,"from_version":fence.from_version,
            "target_version":fence.target_version,
            "deployment_registry_digest":fence.deployment_registry_digest,
            "expected_active_artifact_digest":fence.expected_active_artifact_digest,
            "rollback_plan_digest":fence.rollback_plan_digest,
        }),
        target_revision.artifact_digest,target_revision.eval_digest,eligible,
        "qualified-target" if eligible else "target-not-qualified",
    )


__all__=[
    "AdminCapability","AdminDecisionEvidence","AgentOpsProjection","AgentOpsRecord",
    "AuditProjectionRecord","DeploymentOperationsAssuranceError","EdgeDeploymentEvidence",
    "EdgeResourceTier","EnterpriseAcceptanceEvidence","EnterpriseTopology",
    "FederatedPrincipal","FederationSession","ModelOperationEvidence","ModelRollbackEvidence",
    "ModelRollbackFence","OperationsDashboardEvidence","ResearchDashboardEvidence",
    "assess_enterprise_topology","build_agent_ops_projection","build_operations_dashboard",
    "decide_admin_operation","evaluate_federated_session","project_audit_event",
    "qualify_edge_deployment","qualify_model_rollback","register_model_operation",
]
