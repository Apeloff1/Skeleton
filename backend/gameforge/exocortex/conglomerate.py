from __future__ import annotations
"""
Conglomerate-grade control plane for GameForge Exocortex.

Hierarchy:
  Conglomerate -> Division -> Business Unit -> Workspace -> Subject (user)

Cross-cutting:
  Policy federation, quotas, compliance packs, audit spine,
  isolation boundaries, SLA envelopes, cross-unit handoffs.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class UnitType(str, Enum):
    CONGLOMERATE = "conglomerate"
    DIVISION = "division"
    BUSINESS_UNIT = "business_unit"
    WORKSPACE = "workspace"
    SUBJECT = "subject"


class IsolationLevel(str, Enum):
    SHARED = "shared"
    TENANT = "tenant"
    STRICT = "strict"
    AIRGAP = "airgap"


@dataclass
class Quota:
    max_ingest_per_day: int = 50000
    max_math_jobs_per_day: int = 5000
    max_twin_writes_per_day: int = 100000
    max_judgements_per_day: int = 10000
    max_handoffs_open: int = 500
    storage_mb: int = 10240

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UsageCounter:
    day: str
    ingest: int = 0
    math_jobs: int = 0
    twin_writes: int = 0
    judgements: int = 0
    handoffs_open: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompliancePack:
    pack_id: str
    name: str
    retention_days_min: int = 30
    twin_required: bool = True
    judgement_required_actions: List[str] = field(
        default_factory=lambda: ["schedule_heavy", "math_large", "export", "policy_change"]
    )
    encryption_at_rest: bool = True
    air_gap_default: bool = True
    certainty_mode_default: bool = True
    audit_immutable: bool = True
    pii_surfaces: List[str] = field(
        default_factory=lambda: ["transcript", "patient", "psychology", "diary_memory"]
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PolicyPack:
    pack_id: str
    name: str
    rules: List[str] = field(default_factory=list)
    isolation: str = IsolationLevel.STRICT.value
    quota: Dict[str, Any] = field(default_factory=lambda: Quota().to_dict())
    compliance_pack_id: Optional[str] = None
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrgUnit:
    unit_id: str
    name: str
    unit_type: str
    parent_id: Optional[str] = None
    policy_pack_id: Optional[str] = None
    isolation: str = IsolationLevel.STRICT.value
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Grant:
    grant_id: str
    from_unit: str
    to_unit: str
    surfaces: List[str]
    expires_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SLATarget:
    name: str
    max_latency_ms: float
    max_error_rate: float
    availability: float


class ConglomerateControlPlane:
    def __init__(self, root_name: str = "GameForge Conglomerate"):
        self.root = OrgUnit(
            unit_id="root",
            name=root_name,
            unit_type=UnitType.CONGLOMERATE.value,
            isolation=IsolationLevel.STRICT.value,
            metadata={"level": "conglomerate"},
        )
        self.units: Dict[str, OrgUnit] = {"root": self.root}
        self.policies: Dict[str, PolicyPack] = {}
        self.compliance: Dict[str, CompliancePack] = {}
        self.usage: Dict[str, UsageCounter] = {}
        self.grants: Dict[str, Grant] = {}
        self.audit: List[dict] = []
        self.sla = [
            SLATarget("ingest", 200, 0.01, 0.999),
            SLATarget("judgement", 500, 0.005, 0.999),
            SLATarget("handoff_ack", 100, 0.01, 0.995),
            SLATarget("twin_write", 150, 0.001, 0.9999),
        ]
        self._bootstrap_defaults()

    def _audit(self, event: str, **kw):
        self.audit.append({"ts": datetime.utcnow().isoformat(), "event": event, **kw})
        if len(self.audit) > 20000:
            self.audit = self.audit[-20000:]

    def _bootstrap_defaults(self):
        comp = CompliancePack(pack_id="cmp_default", name="conglomerate_default")
        self.compliance[comp.pack_id] = comp
        pol = PolicyPack(
            pack_id="pol_default",
            name="conglomerate_default",
            rules=[
                "All memory writes twin-unfiltered",
                "PFC+Jeeves dual judgement for heavy actions",
                "Enterprise handoff ack required",
                "Air-gap default on",
                "Certainty mode default on",
                "Cross-unit data requires explicit Grant",
                "Quota breach soft-blocks then hard-blocks",
                "Immutable audit spine",
                "PII surfaces extra retention lock",
            ],
            isolation=IsolationLevel.STRICT.value,
            quota=Quota().to_dict(),
            compliance_pack_id=comp.pack_id,
        )
        self.policies[pol.pack_id] = pol
        self.root.policy_pack_id = pol.pack_id
        eng = self.add_unit("Engineering", UnitType.DIVISION, parent_id="root")
        life = self.add_unit("Personal Life OS", UnitType.DIVISION, parent_id="root")
        self.add_unit("Math Exocortex BU", UnitType.BUSINESS_UNIT, parent_id=eng.unit_id)
        self.add_unit("Agent Runtime BU", UnitType.BUSINESS_UNIT, parent_id=eng.unit_id)
        self.add_unit("Affect & Journals BU", UnitType.BUSINESS_UNIT, parent_id=life.unit_id)
        self.add_unit("Calendar & Era BU", UnitType.BUSINESS_UNIT, parent_id=life.unit_id)
        self._audit("bootstrap", units=len(self.units))

    def add_unit(
        self,
        name: str,
        unit_type,
        parent_id: str = "root",
        isolation: Optional[str] = None,
        policy_pack_id: Optional[str] = None,
    ) -> OrgUnit:
        if parent_id not in self.units:
            raise KeyError(f"parent {parent_id} missing")
        parent = self.units[parent_id]
        ut = unit_type.value if isinstance(unit_type, UnitType) else unit_type
        u = OrgUnit(
            unit_id=str(uuid.uuid4())[:10],
            name=name,
            unit_type=ut,
            parent_id=parent_id,
            policy_pack_id=policy_pack_id or parent.policy_pack_id,
            isolation=isolation or parent.isolation,
        )
        self.units[u.unit_id] = u
        self._audit("add_unit", unit=u.to_dict())
        return u

    def attach_subject(self, user_id: str, parent_id: str = "root") -> OrgUnit:
        existing = [
            u
            for u in self.units.values()
            if u.unit_type == UnitType.SUBJECT.value and u.metadata.get("user_id") == user_id
        ]
        if existing:
            return existing[0]
        u = self.add_unit(f"subject:{user_id}", UnitType.SUBJECT, parent_id=parent_id)
        u.metadata["user_id"] = user_id
        return u

    def path_to_root(self, unit_id: str) -> List[str]:
        path = []
        cur = unit_id
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            path.append(cur)
            parent = self.units.get(cur)
            cur = parent.parent_id if parent else None
        return path

    def effective_policy(self, unit_id: str) -> PolicyPack:
        for uid in self.path_to_root(unit_id):
            u = self.units.get(uid)
            if u and u.policy_pack_id and u.policy_pack_id in self.policies:
                return self.policies[u.policy_pack_id]
        return self.policies["pol_default"]

    def effective_compliance(self, unit_id: str) -> CompliancePack:
        pol = self.effective_policy(unit_id)
        cid = pol.compliance_pack_id or "cmp_default"
        return self.compliance.get(cid) or list(self.compliance.values())[0]

    def set_policy(self, unit_id: str, policy_pack_id: str) -> Dict[str, Any]:
        if unit_id not in self.units or policy_pack_id not in self.policies:
            return {"ok": False, "error": "missing_unit_or_policy"}
        self.units[unit_id].policy_pack_id = policy_pack_id
        self._audit("set_policy", unit_id=unit_id, policy_pack_id=policy_pack_id)
        return {"ok": True}

    def grant_access(
        self,
        from_unit: str,
        to_unit: str,
        surfaces: List[str],
        expires_at: Optional[str] = None,
    ) -> Grant:
        g = Grant(
            grant_id=str(uuid.uuid4())[:10],
            from_unit=from_unit,
            to_unit=to_unit,
            surfaces=surfaces,
            expires_at=expires_at,
        )
        self.grants[g.grant_id] = g
        self._audit("grant", grant=asdict(g))
        return g

    def can_access(self, reader_unit: str, owner_unit: str, surface: str) -> bool:
        if reader_unit == owner_unit:
            return True
        owner = self.units.get(owner_unit)
        if owner and owner.isolation == IsolationLevel.SHARED.value:
            return True
        for g in self.grants.values():
            if g.from_unit == owner_unit and g.to_unit == reader_unit:
                if surface in g.surfaces or "*" in g.surfaces:
                    return True
        return False

    def _today(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _counter(self, unit_id: str) -> UsageCounter:
        key = f"{unit_id}:{self._today()}"
        if key not in self.usage:
            self.usage[key] = UsageCounter(day=self._today())
        return self.usage[key]

    def check_quota(self, unit_id: str, metric: str, amount: int = 1) -> Dict[str, Any]:
        pol = self.effective_policy(unit_id)
        q = pol.quota or Quota().to_dict()
        c = self._counter(unit_id)
        limits = {
            "ingest": q.get("max_ingest_per_day", 50000),
            "math_jobs": q.get("max_math_jobs_per_day", 5000),
            "twin_writes": q.get("max_twin_writes_per_day", 100000),
            "judgements": q.get("max_judgements_per_day", 10000),
            "handoffs_open": q.get("max_handoffs_open", 500),
        }
        current = {
            "ingest": c.ingest,
            "math_jobs": c.math_jobs,
            "twin_writes": c.twin_writes,
            "judgements": c.judgements,
            "handoffs_open": c.handoffs_open,
        }.get(metric, 0)
        limit = limits.get(metric, 10**9)
        allowed = (current + amount) <= limit
        soft = current >= int(limit * 0.9)
        return {
            "allowed": allowed,
            "soft_limit": soft and allowed,
            "metric": metric,
            "current": current,
            "limit": limit,
            "unit_id": unit_id,
        }

    def consume_quota(self, unit_id: str, metric: str, amount: int = 1) -> Dict[str, Any]:
        chk = self.check_quota(unit_id, metric, amount)
        if not chk["allowed"]:
            self._audit("quota_block", **chk)
            return chk
        c = self._counter(unit_id)
        if metric == "ingest":
            c.ingest += amount
        elif metric == "math_jobs":
            c.math_jobs += amount
        elif metric == "twin_writes":
            c.twin_writes += amount
        elif metric == "judgements":
            c.judgements += amount
        elif metric == "handoffs_open":
            c.handoffs_open += amount
        self._audit("quota_consume", metric=metric, amount=amount, unit_id=unit_id)
        return {**chk, "consumed": True}

    def executive_dashboard(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for u in self.units.values():
            by_type[u.unit_type] = by_type.get(u.unit_type, 0) + 1
        return {
            "conglomerate": self.root.name,
            "units_total": len(self.units),
            "by_type": by_type,
            "policies": len(self.policies),
            "compliance_packs": len(self.compliance),
            "active_grants": len(self.grants),
            "sla": [asdict(s) for s in self.sla],
            "default_policy": self.policies.get("pol_default", PolicyPack("x", "x")).to_dict(),
            "default_compliance": self.compliance.get("cmp_default", CompliancePack("x", "x")).to_dict(),
            "audit_tail": self.audit[-15:],
            "usage_keys": len(self.usage),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "root": self.root.to_dict(),
            "units": [u.to_dict() for u in self.units.values()],
            "policy": self.policies.get("pol_default").to_dict() if "pol_default" in self.policies else {},
            "compliance": self.compliance.get("cmp_default").to_dict() if "cmp_default" in self.compliance else {},
            "dashboard": self.executive_dashboard(),
            "audit_tail": self.audit[-10:],
        }

    def enforce_action(self, unit_id: str, action: str) -> Dict[str, Any]:
        pol = self.effective_policy(unit_id)
        cmp_ = self.effective_compliance(unit_id)
        requires_judgement = action in (cmp_.judgement_required_actions or [])
        metric = {
            "ingest": "ingest",
            "math_large": "math_jobs",
            "schedule_heavy": "judgements",
            "export": "judgements",
            "twin": "twin_writes",
        }.get(action, "judgements")
        quota = self.check_quota(unit_id, metric)
        return {
            "allowed": quota["allowed"],
            "requires_judgement": requires_judgement,
            "requires_twin": cmp_.twin_required,
            "isolation": pol.isolation,
            "certainty_mode": cmp_.certainty_mode_default,
            "air_gap": cmp_.air_gap_default,
            "quota": quota,
            "policy_pack": pol.pack_id,
            "compliance_pack": cmp_.pack_id,
        }
