"""Declarative Ubuntu service resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

@dataclass(frozen=True, slots=True)
class ServiceSystemdPlan:
    """Bounded declarative policy for service-systemd."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-systemd:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","systemd",self.identifier,self.desired), "reconcile service-systemd")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_systemd(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-systemd action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-systemd:"+identifier, ("ubuntu","service","systemd",identifier,desired), "validated service-systemd")

def plan_service_systemd(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-systemd plan."""
    p=UbuntuPlan(tuple(validate_service_systemd(x) for x in identifiers), {"domain":"service","resource":"systemd"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_systemd(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-systemd without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-systemd:"))
    return {"resource":"service-systemd","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceSocketPlan:
    """Bounded declarative policy for service-socket."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-socket:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","socket",self.identifier,self.desired), "reconcile service-socket")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_socket(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-socket action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-socket:"+identifier, ("ubuntu","service","socket",identifier,desired), "validated service-socket")

def plan_service_socket(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-socket plan."""
    p=UbuntuPlan(tuple(validate_service_socket(x) for x in identifiers), {"domain":"service","resource":"socket"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_socket(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-socket without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-socket:"))
    return {"resource":"service-socket","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceTimerPlan:
    """Bounded declarative policy for service-timer."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-timer:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","timer",self.identifier,self.desired), "reconcile service-timer")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_timer(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-timer action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-timer:"+identifier, ("ubuntu","service","timer",identifier,desired), "validated service-timer")

def plan_service_timer(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-timer plan."""
    p=UbuntuPlan(tuple(validate_service_timer(x) for x in identifiers), {"domain":"service","resource":"timer"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_timer(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-timer without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-timer:"))
    return {"resource":"service-timer","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceTargetPlan:
    """Bounded declarative policy for service-target."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-target:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","target",self.identifier,self.desired), "reconcile service-target")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_target(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-target action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-target:"+identifier, ("ubuntu","service","target",identifier,desired), "validated service-target")

def plan_service_target(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-target plan."""
    p=UbuntuPlan(tuple(validate_service_target(x) for x in identifiers), {"domain":"service","resource":"target"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_target(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-target without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-target:"))
    return {"resource":"service-target","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceUnitPlan:
    """Bounded declarative policy for service-unit."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-unit:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","unit",self.identifier,self.desired), "reconcile service-unit")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_unit(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-unit action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-unit:"+identifier, ("ubuntu","service","unit",identifier,desired), "validated service-unit")

def plan_service_unit(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-unit plan."""
    p=UbuntuPlan(tuple(validate_service_unit(x) for x in identifiers), {"domain":"service","resource":"unit"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_unit(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-unit without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-unit:"))
    return {"resource":"service-unit","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceJournalPlan:
    """Bounded declarative policy for service-journal."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-journal:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","journal",self.identifier,self.desired), "reconcile service-journal")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_journal(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-journal action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-journal:"+identifier, ("ubuntu","service","journal",identifier,desired), "validated service-journal")

def plan_service_journal(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-journal plan."""
    p=UbuntuPlan(tuple(validate_service_journal(x) for x in identifiers), {"domain":"service","resource":"journal"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_journal(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-journal without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-journal:"))
    return {"resource":"service-journal","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceRestartPlan:
    """Bounded declarative policy for service-restart."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-restart:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","restart",self.identifier,self.desired), "reconcile service-restart")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_restart(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-restart action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-restart:"+identifier, ("ubuntu","service","restart",identifier,desired), "validated service-restart")

def plan_service_restart(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-restart plan."""
    p=UbuntuPlan(tuple(validate_service_restart(x) for x in identifiers), {"domain":"service","resource":"restart"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_restart(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-restart without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-restart:"))
    return {"resource":"service-restart","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceEnablePlan:
    """Bounded declarative policy for service-enable."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-enable:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","enable",self.identifier,self.desired), "reconcile service-enable")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_enable(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-enable action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-enable:"+identifier, ("ubuntu","service","enable",identifier,desired), "validated service-enable")

def plan_service_enable(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-enable plan."""
    p=UbuntuPlan(tuple(validate_service_enable(x) for x in identifiers), {"domain":"service","resource":"enable"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_enable(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-enable without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-enable:"))
    return {"resource":"service-enable","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceMaskPlan:
    """Bounded declarative policy for service-mask."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-mask:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","mask",self.identifier,self.desired), "reconcile service-mask")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_mask(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-mask action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-mask:"+identifier, ("ubuntu","service","mask",identifier,desired), "validated service-mask")

def plan_service_mask(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-mask plan."""
    p=UbuntuPlan(tuple(validate_service_mask(x) for x in identifiers), {"domain":"service","resource":"mask"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_mask(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-mask without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-mask:"))
    return {"resource":"service-mask","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class ServiceHealthPlan:
    """Bounded declarative policy for service-health."""
    identifier: str
    desired: str = "present"
    version: str = ""
    owner: str = "root"
    mode: str = "0644"
    enabled: bool = True
    restart: bool = False
    tags: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        _clean(self.identifier); _clean(self.desired); _clean(self.version); _clean(self.owner); _clean(self.mode)
        if len(self.tags)>32: raise ValueError("too many tags")
    @property
    def key(self) -> str:
        return "service-health:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","service","health",self.identifier,self.desired), "reconcile service-health")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_service_health(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated service-health action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("service-health:"+identifier, ("ubuntu","service","health",identifier,desired), "validated service-health")

def plan_service_health(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic service-health plan."""
    p=UbuntuPlan(tuple(validate_service_health(x) for x in identifiers), {"domain":"service","resource":"health"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_service_health(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit service-health without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("service-health:"))
    return {"resource":"service-health","ok":not e,"errors":e,"count":len(names),"names":names}

__all__ = [
    "ServiceSystemdPlan",
    "ServiceSocketPlan",
    "ServiceTimerPlan",
    "ServiceTargetPlan",
    "ServiceUnitPlan",
    "ServiceJournalPlan",
    "ServiceRestartPlan",
    "ServiceEnablePlan",
    "ServiceMaskPlan",
    "ServiceHealthPlan",
    "validate_service_systemd",
    "plan_service_systemd",
    "audit_service_systemd",
    "validate_service_socket",
    "plan_service_socket",
    "audit_service_socket",
    "validate_service_timer",
    "plan_service_timer",
    "audit_service_timer",
    "validate_service_target",
    "plan_service_target",
    "audit_service_target",
    "validate_service_unit",
    "plan_service_unit",
    "audit_service_unit",
    "validate_service_journal",
    "plan_service_journal",
    "audit_service_journal",
    "validate_service_restart",
    "plan_service_restart",
    "audit_service_restart",
    "validate_service_enable",
    "plan_service_enable",
    "audit_service_enable",
    "validate_service_mask",
    "plan_service_mask",
    "audit_service_mask",
    "validate_service_health",
    "plan_service_health",
    "audit_service_health",
]
