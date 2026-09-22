"""Declarative Ubuntu cloud resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

@dataclass(frozen=True, slots=True)
class CloudCloudinitPlan:
    """Bounded declarative policy for cloud-cloudinit."""
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
        return "cloud-cloudinit:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","cloudinit",self.identifier,self.desired), "reconcile cloud-cloudinit")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_cloudinit(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-cloudinit action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-cloudinit:"+identifier, ("ubuntu","cloud","cloudinit",identifier,desired), "validated cloud-cloudinit")

def plan_cloud_cloudinit(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-cloudinit plan."""
    p=UbuntuPlan(tuple(validate_cloud_cloudinit(x) for x in identifiers), {"domain":"cloud","resource":"cloudinit"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_cloudinit(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-cloudinit without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-cloudinit:"))
    return {"resource":"cloud-cloudinit","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudMetadataPlan:
    """Bounded declarative policy for cloud-metadata."""
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
        return "cloud-metadata:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","metadata",self.identifier,self.desired), "reconcile cloud-metadata")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_metadata(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-metadata action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-metadata:"+identifier, ("ubuntu","cloud","metadata",identifier,desired), "validated cloud-metadata")

def plan_cloud_metadata(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-metadata plan."""
    p=UbuntuPlan(tuple(validate_cloud_metadata(x) for x in identifiers), {"domain":"cloud","resource":"metadata"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_metadata(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-metadata without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-metadata:"))
    return {"resource":"cloud-metadata","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudIdentityPlan:
    """Bounded declarative policy for cloud-identity."""
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
        return "cloud-identity:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","identity",self.identifier,self.desired), "reconcile cloud-identity")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_identity(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-identity action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-identity:"+identifier, ("ubuntu","cloud","identity",identifier,desired), "validated cloud-identity")

def plan_cloud_identity(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-identity plan."""
    p=UbuntuPlan(tuple(validate_cloud_identity(x) for x in identifiers), {"domain":"cloud","resource":"identity"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_identity(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-identity without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-identity:"))
    return {"resource":"cloud-identity","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudInstancePlan:
    """Bounded declarative policy for cloud-instance."""
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
        return "cloud-instance:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","instance",self.identifier,self.desired), "reconcile cloud-instance")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_instance(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-instance action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-instance:"+identifier, ("ubuntu","cloud","instance",identifier,desired), "validated cloud-instance")

def plan_cloud_instance(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-instance plan."""
    p=UbuntuPlan(tuple(validate_cloud_instance(x) for x in identifiers), {"domain":"cloud","resource":"instance"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_instance(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-instance without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-instance:"))
    return {"resource":"cloud-instance","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudUserdataPlan:
    """Bounded declarative policy for cloud-userdata."""
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
        return "cloud-userdata:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","userdata",self.identifier,self.desired), "reconcile cloud-userdata")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_userdata(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-userdata action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-userdata:"+identifier, ("ubuntu","cloud","userdata",identifier,desired), "validated cloud-userdata")

def plan_cloud_userdata(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-userdata plan."""
    p=UbuntuPlan(tuple(validate_cloud_userdata(x) for x in identifiers), {"domain":"cloud","resource":"userdata"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_userdata(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-userdata without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-userdata:"))
    return {"resource":"cloud-userdata","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudProvisionPlan:
    """Bounded declarative policy for cloud-provision."""
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
        return "cloud-provision:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","provision",self.identifier,self.desired), "reconcile cloud-provision")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_provision(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-provision action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-provision:"+identifier, ("ubuntu","cloud","provision",identifier,desired), "validated cloud-provision")

def plan_cloud_provision(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-provision plan."""
    p=UbuntuPlan(tuple(validate_cloud_provision(x) for x in identifiers), {"domain":"cloud","resource":"provision"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_provision(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-provision without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-provision:"))
    return {"resource":"cloud-provision","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudImagePlan:
    """Bounded declarative policy for cloud-image."""
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
        return "cloud-image:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","image",self.identifier,self.desired), "reconcile cloud-image")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_image(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-image action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-image:"+identifier, ("ubuntu","cloud","image",identifier,desired), "validated cloud-image")

def plan_cloud_image(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-image plan."""
    p=UbuntuPlan(tuple(validate_cloud_image(x) for x in identifiers), {"domain":"cloud","resource":"image"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_image(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-image without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-image:"))
    return {"resource":"cloud-image","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudAgentPlan:
    """Bounded declarative policy for cloud-agent."""
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
        return "cloud-agent:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","agent",self.identifier,self.desired), "reconcile cloud-agent")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_agent(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-agent action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-agent:"+identifier, ("ubuntu","cloud","agent",identifier,desired), "validated cloud-agent")

def plan_cloud_agent(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-agent plan."""
    p=UbuntuPlan(tuple(validate_cloud_agent(x) for x in identifiers), {"domain":"cloud","resource":"agent"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_agent(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-agent without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-agent:"))
    return {"resource":"cloud-agent","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudHealthPlan:
    """Bounded declarative policy for cloud-health."""
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
        return "cloud-health:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","health",self.identifier,self.desired), "reconcile cloud-health")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_health(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-health action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-health:"+identifier, ("ubuntu","cloud","health",identifier,desired), "validated cloud-health")

def plan_cloud_health(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-health plan."""
    p=UbuntuPlan(tuple(validate_cloud_health(x) for x in identifiers), {"domain":"cloud","resource":"health"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_health(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-health without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-health:"))
    return {"resource":"cloud-health","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CloudTagsPlan:
    """Bounded declarative policy for cloud-tags."""
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
        return "cloud-tags:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","cloud","tags",self.identifier,self.desired), "reconcile cloud-tags")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_cloud_tags(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated cloud-tags action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("cloud-tags:"+identifier, ("ubuntu","cloud","tags",identifier,desired), "validated cloud-tags")

def plan_cloud_tags(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic cloud-tags plan."""
    p=UbuntuPlan(tuple(validate_cloud_tags(x) for x in identifiers), {"domain":"cloud","resource":"tags"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_cloud_tags(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit cloud-tags without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("cloud-tags:"))
    return {"resource":"cloud-tags","ok":not e,"errors":e,"count":len(names),"names":names}

__all__ = [
    "CloudCloudinitPlan",
    "CloudMetadataPlan",
    "CloudIdentityPlan",
    "CloudInstancePlan",
    "CloudUserdataPlan",
    "CloudProvisionPlan",
    "CloudImagePlan",
    "CloudAgentPlan",
    "CloudHealthPlan",
    "CloudTagsPlan",
    "validate_cloud_cloudinit",
    "plan_cloud_cloudinit",
    "audit_cloud_cloudinit",
    "validate_cloud_metadata",
    "plan_cloud_metadata",
    "audit_cloud_metadata",
    "validate_cloud_identity",
    "plan_cloud_identity",
    "audit_cloud_identity",
    "validate_cloud_instance",
    "plan_cloud_instance",
    "audit_cloud_instance",
    "validate_cloud_userdata",
    "plan_cloud_userdata",
    "audit_cloud_userdata",
    "validate_cloud_provision",
    "plan_cloud_provision",
    "audit_cloud_provision",
    "validate_cloud_image",
    "plan_cloud_image",
    "audit_cloud_image",
    "validate_cloud_agent",
    "plan_cloud_agent",
    "audit_cloud_agent",
    "validate_cloud_health",
    "plan_cloud_health",
    "audit_cloud_health",
    "validate_cloud_tags",
    "plan_cloud_tags",
    "audit_cloud_tags",
]
