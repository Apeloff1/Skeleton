"""Identity, administration and operations projections for VOL-233..237.

Projection objects are deliberately non-authoritative. Privileged changes are
accepted only with explicit governed authorization receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from .contracts import sha256_json


def _text(v: object, name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be non-empty text")
    return v.strip()


def _unique(v: Iterable[str], name: str) -> tuple[str, ...]:
    out=tuple(_text(x,name) for x in v)
    if len(out)!=len(set(out)): raise ValueError(f"{name} must be unique")
    return out


@dataclass(frozen=True, slots=True)
class FederationConfig:
    issuer: str
    audiences: tuple[str, ...]
    signature_key_ids: tuple[str, ...]
    durable_subject_claim: str = "sub"

    def __post_init__(self) -> None:
        object.__setattr__(self,"issuer",_text(self.issuer,"issuer"))
        object.__setattr__(self,"audiences",_unique(self.audiences,"audience"))
        object.__setattr__(self,"signature_key_ids",_unique(self.signature_key_ids,"signature_key_id"))
        object.__setattr__(self,"durable_subject_claim",_text(self.durable_subject_claim,"durable_subject_claim"))
        if not self.audiences or not self.signature_key_ids: raise ValueError("federation requires audience and signature keys")
        if self.durable_subject_claim in {"email","name","preferred_username"}: raise ValueError("mutable display claim cannot be durable identity")


@dataclass(frozen=True, slots=True)
class IdentityClaim:
    issuer: str
    audience: str
    subject: str
    key_id: str
    groups: tuple[str, ...]
    session_id: str
    revoked: bool=False

    def __post_init__(self) -> None:
        for n in ("issuer","audience","subject","key_id","session_id"): object.__setattr__(self,n,_text(getattr(self,n),n))
        object.__setattr__(self,"groups",_unique(self.groups,"group"))


@dataclass(frozen=True, slots=True)
class FederatedIdentity:
    principal_id: str
    issuer: str
    subject: str
    groups: tuple[str, ...]
    session_id: str


def map_identity(config: FederationConfig, claim: IdentityClaim) -> FederatedIdentity:
    if claim.revoked: raise PermissionError("identity session revoked")
    if claim.issuer != config.issuer: raise PermissionError("issuer mismatch")
    if claim.audience not in config.audiences: raise PermissionError("audience mismatch")
    if claim.key_id not in config.signature_key_ids: raise PermissionError("untrusted signing key")
    return FederatedIdentity(sha256_json({"issuer":claim.issuer,"subject":claim.subject}),claim.issuer,claim.subject,claim.groups,claim.session_id)


@dataclass(frozen=True, slots=True)
class AdminPolicy:
    allowed_actions: tuple[str,...]
    break_glass_actions: tuple[str,...]
    def __post_init__(self)->None:
        object.__setattr__(self,"allowed_actions",_unique(self.allowed_actions,"allowed_action"))
        object.__setattr__(self,"break_glass_actions",_unique(self.break_glass_actions,"break_glass_action"))


@dataclass(frozen=True, slots=True)
class AdminAction:
    action_id: str
    principal_id: str
    capability: str
    payload_digest: str
    authorization_receipt: str
    model_generated: bool=False
    break_glass_approval: str|None=None
    def __post_init__(self)->None:
        for n in ("action_id","principal_id","capability","payload_digest","authorization_receipt"): object.__setattr__(self,n,_text(getattr(self,n),n))
        if self.break_glass_approval is not None: object.__setattr__(self,"break_glass_approval",_text(self.break_glass_approval,"break_glass_approval"))


@dataclass(frozen=True, slots=True)
class AdminReceipt:
    action_id: str
    principal_id: str
    capability: str
    authorization_receipt: str
    accepted: bool


def authorize_admin(policy: AdminPolicy, action: AdminAction) -> AdminReceipt:
    if action.model_generated: return AdminReceipt(action.action_id,action.principal_id,action.capability,action.authorization_receipt,False)
    allowed=action.capability in policy.allowed_actions
    if action.capability in policy.break_glass_actions: allowed=allowed and action.break_glass_approval is not None
    return AdminReceipt(action.action_id,action.principal_id,action.capability,action.authorization_receipt,allowed)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    entry_id: str
    tenant_id: str
    correlation_id: str
    receipt_id: str
    summary: str
    secret_fields: tuple[str,...]=()
    def __post_init__(self)->None:
        for n in ("entry_id","tenant_id","correlation_id","receipt_id","summary"): object.__setattr__(self,n,_text(getattr(self,n),n))
        object.__setattr__(self,"secret_fields",_unique(self.secret_fields,"secret_field"))


@dataclass(frozen=True, slots=True)
class AuditQuery:
    tenant_id: str
    correlation_id: str|None=None


@dataclass(frozen=True, slots=True)
class AuditView:
    entries: tuple[AuditEntry,...]


def project_audit(entries: Sequence[AuditEntry], query: AuditQuery) -> AuditView:
    tenant=_text(query.tenant_id,"tenant_id")
    visible=[]
    for e in entries:
        if e.tenant_id!=tenant or (query.correlation_id and e.correlation_id!=query.correlation_id): continue
        summary=e.summary
        for secret in e.secret_fields: summary=summary.replace(secret,"[REDACTED]")
        visible.append(AuditEntry(e.entry_id,e.tenant_id,e.correlation_id,e.receipt_id,summary,()))
    return AuditView(tuple(visible))


class TelemetryState(str, Enum):
    FRESH="fresh"; STALE="stale"; UNKNOWN="unknown"


@dataclass(frozen=True, slots=True)
class OpsMetric:
    name: str
    value: float
    telemetry_state: TelemetryState
    observed_at: str


@dataclass(frozen=True, slots=True)
class OpsAlert:
    alert_id: str
    severity: str
    blocker: bool
    runbook: str


@dataclass(frozen=True, slots=True)
class OperationsDashboard:
    metrics: tuple[OpsMetric,...]
    alerts: tuple[OpsAlert,...]
    @property
    def healthy(self)->bool:
        return bool(self.metrics) and all(m.telemetry_state is TelemetryState.FRESH for m in self.metrics) and not any(a.blocker for a in self.alerts)


@dataclass(frozen=True, slots=True)
class AgentOpsAlert:
    agent_id: str
    kind: str
    blocker: bool


@dataclass(frozen=True, slots=True)
class AgentOpsView:
    agent_id: str
    lease_expires_at: str
    budget_remaining: int
    alerts: tuple[AgentOpsAlert,...]


@dataclass(frozen=True, slots=True)
class AgentControlAction:
    agent_id: str
    action: str
    human_principal: str
    governed_api_receipt: str
    def __post_init__(self)->None:
        for n in ("agent_id","action","human_principal","governed_api_receipt"): object.__setattr__(self,n,_text(getattr(self,n),n))


def project_agent_ops(agent_id:str, lease_expires_at:str, budget_remaining:int, *, lease_stale:bool) -> AgentOpsView:
    if isinstance(budget_remaining,bool) or not isinstance(budget_remaining,int): raise TypeError("budget_remaining must be integer")
    alerts=[]
    if lease_stale: alerts.append(AgentOpsAlert(agent_id,"stale_or_orphan_lease",True))
    if budget_remaining<=0: alerts.append(AgentOpsAlert(agent_id,"budget_exhausted",True))
    return AgentOpsView(_text(agent_id,"agent_id"),_text(lease_expires_at,"lease_expires_at"),budget_remaining,tuple(alerts))
