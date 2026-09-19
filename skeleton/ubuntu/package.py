"""Declarative Ubuntu package resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

@dataclass(frozen=True, slots=True)
class PackageAptPlan:
    """Bounded declarative policy for package-apt."""
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
        return "package-apt:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","apt",self.identifier,self.desired), "reconcile package-apt")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_apt(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-apt action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-apt:"+identifier, ("ubuntu","package","apt",identifier,desired), "validated package-apt")

def plan_package_apt(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-apt plan."""
    p=UbuntuPlan(tuple(validate_package_apt(x) for x in identifiers), {"domain":"package","resource":"apt"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_apt(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-apt without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-apt:"))
    return {"resource":"package-apt","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageSnapPlan:
    """Bounded declarative policy for package-snap."""
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
        return "package-snap:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","snap",self.identifier,self.desired), "reconcile package-snap")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_snap(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-snap action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-snap:"+identifier, ("ubuntu","package","snap",identifier,desired), "validated package-snap")

def plan_package_snap(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-snap plan."""
    p=UbuntuPlan(tuple(validate_package_snap(x) for x in identifiers), {"domain":"package","resource":"snap"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_snap(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-snap without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-snap:"))
    return {"resource":"package-snap","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageDebPlan:
    """Bounded declarative policy for package-deb."""
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
        return "package-deb:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","deb",self.identifier,self.desired), "reconcile package-deb")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_deb(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-deb action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-deb:"+identifier, ("ubuntu","package","deb",identifier,desired), "validated package-deb")

def plan_package_deb(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-deb plan."""
    p=UbuntuPlan(tuple(validate_package_deb(x) for x in identifiers), {"domain":"package","resource":"deb"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_deb(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-deb without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-deb:"))
    return {"resource":"package-deb","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageRepoPlan:
    """Bounded declarative policy for package-repo."""
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
        return "package-repo:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","repo",self.identifier,self.desired), "reconcile package-repo")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_repo(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-repo action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-repo:"+identifier, ("ubuntu","package","repo",identifier,desired), "validated package-repo")

def plan_package_repo(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-repo plan."""
    p=UbuntuPlan(tuple(validate_package_repo(x) for x in identifiers), {"domain":"package","resource":"repo"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_repo(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-repo without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-repo:"))
    return {"resource":"package-repo","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackagePinPlan:
    """Bounded declarative policy for package-pin."""
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
        return "package-pin:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","pin",self.identifier,self.desired), "reconcile package-pin")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_pin(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-pin action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-pin:"+identifier, ("ubuntu","package","pin",identifier,desired), "validated package-pin")

def plan_package_pin(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-pin plan."""
    p=UbuntuPlan(tuple(validate_package_pin(x) for x in identifiers), {"domain":"package","resource":"pin"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_pin(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-pin without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-pin:"))
    return {"resource":"package-pin","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageHoldPlan:
    """Bounded declarative policy for package-hold."""
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
        return "package-hold:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","hold",self.identifier,self.desired), "reconcile package-hold")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_hold(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-hold action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-hold:"+identifier, ("ubuntu","package","hold",identifier,desired), "validated package-hold")

def plan_package_hold(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-hold plan."""
    p=UbuntuPlan(tuple(validate_package_hold(x) for x in identifiers), {"domain":"package","resource":"hold"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_hold(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-hold without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-hold:"))
    return {"resource":"package-hold","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageCachePlan:
    """Bounded declarative policy for package-cache."""
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
        return "package-cache:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","cache",self.identifier,self.desired), "reconcile package-cache")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_cache(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-cache action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-cache:"+identifier, ("ubuntu","package","cache",identifier,desired), "validated package-cache")

def plan_package_cache(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-cache plan."""
    p=UbuntuPlan(tuple(validate_package_cache(x) for x in identifiers), {"domain":"package","resource":"cache"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_cache(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-cache without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-cache:"))
    return {"resource":"package-cache","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageMirrorPlan:
    """Bounded declarative policy for package-mirror."""
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
        return "package-mirror:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","mirror",self.identifier,self.desired), "reconcile package-mirror")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_mirror(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-mirror action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-mirror:"+identifier, ("ubuntu","package","mirror",identifier,desired), "validated package-mirror")

def plan_package_mirror(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-mirror plan."""
    p=UbuntuPlan(tuple(validate_package_mirror(x) for x in identifiers), {"domain":"package","resource":"mirror"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_mirror(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-mirror without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-mirror:"))
    return {"resource":"package-mirror","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackageKeyringPlan:
    """Bounded declarative policy for package-keyring."""
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
        return "package-keyring:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","keyring",self.identifier,self.desired), "reconcile package-keyring")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_keyring(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-keyring action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-keyring:"+identifier, ("ubuntu","package","keyring",identifier,desired), "validated package-keyring")

def plan_package_keyring(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-keyring plan."""
    p=UbuntuPlan(tuple(validate_package_keyring(x) for x in identifiers), {"domain":"package","resource":"keyring"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_keyring(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-keyring without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-keyring:"))
    return {"resource":"package-keyring","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class PackagePolicyPlan:
    """Bounded declarative policy for package-policy."""
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
        return "package-policy:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","package","policy",self.identifier,self.desired), "reconcile package-policy")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_package_policy(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated package-policy action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("package-policy:"+identifier, ("ubuntu","package","policy",identifier,desired), "validated package-policy")

def plan_package_policy(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic package-policy plan."""
    p=UbuntuPlan(tuple(validate_package_policy(x) for x in identifiers), {"domain":"package","resource":"policy"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_package_policy(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit package-policy without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("package-policy:"))
    return {"resource":"package-policy","ok":not e,"errors":e,"count":len(names),"names":names}

__all__ = [
    "PackageAptPlan",
    "PackageSnapPlan",
    "PackageDebPlan",
    "PackageRepoPlan",
    "PackagePinPlan",
    "PackageHoldPlan",
    "PackageCachePlan",
    "PackageMirrorPlan",
    "PackageKeyringPlan",
    "PackagePolicyPlan",
    "validate_package_apt",
    "plan_package_apt",
    "audit_package_apt",
    "validate_package_snap",
    "plan_package_snap",
    "audit_package_snap",
    "validate_package_deb",
    "plan_package_deb",
    "audit_package_deb",
    "validate_package_repo",
    "plan_package_repo",
    "audit_package_repo",
    "validate_package_pin",
    "plan_package_pin",
    "audit_package_pin",
    "validate_package_hold",
    "plan_package_hold",
    "audit_package_hold",
    "validate_package_cache",
    "plan_package_cache",
    "audit_package_cache",
    "validate_package_mirror",
    "plan_package_mirror",
    "audit_package_mirror",
    "validate_package_keyring",
    "plan_package_keyring",
    "audit_package_keyring",
    "validate_package_policy",
    "plan_package_policy",
    "audit_package_policy",
]
