"""Ubuntu host operations primitives for Skeleton.
Declarative, bounded planning objects for Ubuntu hosts. This module never executes
host commands; it produces inspectable plans for a separately authorized executor.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Sequence
MAX_TEXT = 4096

def _clean(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError("invalid bounded text")
    return value

@dataclass(frozen=True, slots=True)
class UbuntuAction:
    name: str
    argv: tuple[str, ...]
    reason: str
    timeout_seconds: int = 30
    def __post_init__(self) -> None:
        _clean(self.name); _clean(self.reason)
        if not self.argv: raise ValueError("argv must be non-empty")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600: raise ValueError("timeout out of bounds")
    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "argv": self.argv, "reason": self.reason, "timeout_seconds": self.timeout_seconds}

@dataclass(frozen=True, slots=True)
class UbuntuPlan:
    actions: tuple[UbuntuAction, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    def append(self, action: UbuntuAction) -> "UbuntuPlan":
        return UbuntuPlan(self.actions + (action,), dict(self.metadata))
    def extend(self, actions: Sequence[UbuntuAction]) -> "UbuntuPlan":
        return UbuntuPlan(self.actions + tuple(actions), dict(self.metadata))
    def names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.actions)

def validate_plan(plan: UbuntuPlan) -> tuple[str, ...]:
    errors=[]; seen=set()
    for action in plan.actions:
        if action.name in seen: errors.append("duplicate action: " + action.name)
        seen.add(action.name)
    return tuple(errors)

def merge_plans(*plans: UbuntuPlan) -> UbuntuPlan:
    result=UbuntuPlan()
    for plan in plans: result=result.extend(plan.actions)
    errors=validate_plan(result)
    if errors: raise ValueError("; ".join(errors))
    return result
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

@dataclass(frozen=True, slots=True)
class NetworkNetplanPlan:
    """Bounded declarative policy for network-netplan."""
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
        return "network-netplan:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","netplan",self.identifier,self.desired), "reconcile network-netplan")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_netplan(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-netplan action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-netplan:"+identifier, ("ubuntu","network","netplan",identifier,desired), "validated network-netplan")

def plan_network_netplan(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-netplan plan."""
    p=UbuntuPlan(tuple(validate_network_netplan(x) for x in identifiers), {"domain":"network","resource":"netplan"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_netplan(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-netplan without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-netplan:"))
    return {"resource":"network-netplan","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkDnsPlan:
    """Bounded declarative policy for network-dns."""
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
        return "network-dns:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","dns",self.identifier,self.desired), "reconcile network-dns")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_dns(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-dns action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-dns:"+identifier, ("ubuntu","network","dns",identifier,desired), "validated network-dns")

def plan_network_dns(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-dns plan."""
    p=UbuntuPlan(tuple(validate_network_dns(x) for x in identifiers), {"domain":"network","resource":"dns"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_dns(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-dns without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-dns:"))
    return {"resource":"network-dns","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkRoutePlan:
    """Bounded declarative policy for network-route."""
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
        return "network-route:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","route",self.identifier,self.desired), "reconcile network-route")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_route(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-route action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-route:"+identifier, ("ubuntu","network","route",identifier,desired), "validated network-route")

def plan_network_route(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-route plan."""
    p=UbuntuPlan(tuple(validate_network_route(x) for x in identifiers), {"domain":"network","resource":"route"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_route(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-route without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-route:"))
    return {"resource":"network-route","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkBridgePlan:
    """Bounded declarative policy for network-bridge."""
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
        return "network-bridge:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","bridge",self.identifier,self.desired), "reconcile network-bridge")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_bridge(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-bridge action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-bridge:"+identifier, ("ubuntu","network","bridge",identifier,desired), "validated network-bridge")

def plan_network_bridge(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-bridge plan."""
    p=UbuntuPlan(tuple(validate_network_bridge(x) for x in identifiers), {"domain":"network","resource":"bridge"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_bridge(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-bridge without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-bridge:"))
    return {"resource":"network-bridge","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkBondPlan:
    """Bounded declarative policy for network-bond."""
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
        return "network-bond:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","bond",self.identifier,self.desired), "reconcile network-bond")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_bond(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-bond action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-bond:"+identifier, ("ubuntu","network","bond",identifier,desired), "validated network-bond")

def plan_network_bond(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-bond plan."""
    p=UbuntuPlan(tuple(validate_network_bond(x) for x in identifiers), {"domain":"network","resource":"bond"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_bond(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-bond without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-bond:"))
    return {"resource":"network-bond","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkVlanPlan:
    """Bounded declarative policy for network-vlan."""
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
        return "network-vlan:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","vlan",self.identifier,self.desired), "reconcile network-vlan")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_vlan(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-vlan action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-vlan:"+identifier, ("ubuntu","network","vlan",identifier,desired), "validated network-vlan")

def plan_network_vlan(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-vlan plan."""
    p=UbuntuPlan(tuple(validate_network_vlan(x) for x in identifiers), {"domain":"network","resource":"vlan"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_vlan(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-vlan without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-vlan:"))
    return {"resource":"network-vlan","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkMtuPlan:
    """Bounded declarative policy for network-mtu."""
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
        return "network-mtu:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","mtu",self.identifier,self.desired), "reconcile network-mtu")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_mtu(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-mtu action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-mtu:"+identifier, ("ubuntu","network","mtu",identifier,desired), "validated network-mtu")

def plan_network_mtu(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-mtu plan."""
    p=UbuntuPlan(tuple(validate_network_mtu(x) for x in identifiers), {"domain":"network","resource":"mtu"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_mtu(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-mtu without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-mtu:"))
    return {"resource":"network-mtu","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkFirewallPlan:
    """Bounded declarative policy for network-firewall."""
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
        return "network-firewall:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","firewall",self.identifier,self.desired), "reconcile network-firewall")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_firewall(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-firewall action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-firewall:"+identifier, ("ubuntu","network","firewall",identifier,desired), "validated network-firewall")

def plan_network_firewall(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-firewall plan."""
    p=UbuntuPlan(tuple(validate_network_firewall(x) for x in identifiers), {"domain":"network","resource":"firewall"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_firewall(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-firewall without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-firewall:"))
    return {"resource":"network-firewall","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkProxyPlan:
    """Bounded declarative policy for network-proxy."""
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
        return "network-proxy:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","proxy",self.identifier,self.desired), "reconcile network-proxy")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_proxy(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-proxy action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-proxy:"+identifier, ("ubuntu","network","proxy",identifier,desired), "validated network-proxy")

def plan_network_proxy(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-proxy plan."""
    p=UbuntuPlan(tuple(validate_network_proxy(x) for x in identifiers), {"domain":"network","resource":"proxy"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_proxy(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-proxy without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-proxy:"))
    return {"resource":"network-proxy","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class NetworkTlsPlan:
    """Bounded declarative policy for network-tls."""
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
        return "network-tls:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","network","tls",self.identifier,self.desired), "reconcile network-tls")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_network_tls(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated network-tls action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("network-tls:"+identifier, ("ubuntu","network","tls",identifier,desired), "validated network-tls")

def plan_network_tls(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic network-tls plan."""
    p=UbuntuPlan(tuple(validate_network_tls(x) for x in identifiers), {"domain":"network","resource":"tls"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_network_tls(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit network-tls without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("network-tls:"))
    return {"resource":"network-tls","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageMountPlan:
    """Bounded declarative policy for storage-mount."""
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
        return "storage-mount:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","mount",self.identifier,self.desired), "reconcile storage-mount")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_mount(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-mount action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-mount:"+identifier, ("ubuntu","storage","mount",identifier,desired), "validated storage-mount")

def plan_storage_mount(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-mount plan."""
    p=UbuntuPlan(tuple(validate_storage_mount(x) for x in identifiers), {"domain":"storage","resource":"mount"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_mount(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-mount without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-mount:"))
    return {"resource":"storage-mount","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageFstabPlan:
    """Bounded declarative policy for storage-fstab."""
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
        return "storage-fstab:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","fstab",self.identifier,self.desired), "reconcile storage-fstab")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_fstab(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-fstab action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-fstab:"+identifier, ("ubuntu","storage","fstab",identifier,desired), "validated storage-fstab")

def plan_storage_fstab(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-fstab plan."""
    p=UbuntuPlan(tuple(validate_storage_fstab(x) for x in identifiers), {"domain":"storage","resource":"fstab"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_fstab(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-fstab without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-fstab:"))
    return {"resource":"storage-fstab","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageDiskPlan:
    """Bounded declarative policy for storage-disk."""
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
        return "storage-disk:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","disk",self.identifier,self.desired), "reconcile storage-disk")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_disk(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-disk action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-disk:"+identifier, ("ubuntu","storage","disk",identifier,desired), "validated storage-disk")

def plan_storage_disk(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-disk plan."""
    p=UbuntuPlan(tuple(validate_storage_disk(x) for x in identifiers), {"domain":"storage","resource":"disk"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_disk(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-disk without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-disk:"))
    return {"resource":"storage-disk","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StoragePartitionPlan:
    """Bounded declarative policy for storage-partition."""
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
        return "storage-partition:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","partition",self.identifier,self.desired), "reconcile storage-partition")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_partition(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-partition action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-partition:"+identifier, ("ubuntu","storage","partition",identifier,desired), "validated storage-partition")

def plan_storage_partition(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-partition plan."""
    p=UbuntuPlan(tuple(validate_storage_partition(x) for x in identifiers), {"domain":"storage","resource":"partition"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_partition(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-partition without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-partition:"))
    return {"resource":"storage-partition","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageLvmPlan:
    """Bounded declarative policy for storage-lvm."""
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
        return "storage-lvm:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","lvm",self.identifier,self.desired), "reconcile storage-lvm")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_lvm(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-lvm action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-lvm:"+identifier, ("ubuntu","storage","lvm",identifier,desired), "validated storage-lvm")

def plan_storage_lvm(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-lvm plan."""
    p=UbuntuPlan(tuple(validate_storage_lvm(x) for x in identifiers), {"domain":"storage","resource":"lvm"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_lvm(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-lvm without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-lvm:"))
    return {"resource":"storage-lvm","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageZfsPlan:
    """Bounded declarative policy for storage-zfs."""
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
        return "storage-zfs:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","zfs",self.identifier,self.desired), "reconcile storage-zfs")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_zfs(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-zfs action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-zfs:"+identifier, ("ubuntu","storage","zfs",identifier,desired), "validated storage-zfs")

def plan_storage_zfs(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-zfs plan."""
    p=UbuntuPlan(tuple(validate_storage_zfs(x) for x in identifiers), {"domain":"storage","resource":"zfs"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_zfs(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-zfs without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-zfs:"))
    return {"resource":"storage-zfs","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageRaidPlan:
    """Bounded declarative policy for storage-raid."""
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
        return "storage-raid:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","raid",self.identifier,self.desired), "reconcile storage-raid")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_raid(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-raid action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-raid:"+identifier, ("ubuntu","storage","raid",identifier,desired), "validated storage-raid")

def plan_storage_raid(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-raid plan."""
    p=UbuntuPlan(tuple(validate_storage_raid(x) for x in identifiers), {"domain":"storage","resource":"raid"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_raid(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-raid without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-raid:"))
    return {"resource":"storage-raid","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageQuotaPlan:
    """Bounded declarative policy for storage-quota."""
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
        return "storage-quota:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","quota",self.identifier,self.desired), "reconcile storage-quota")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_quota(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-quota action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-quota:"+identifier, ("ubuntu","storage","quota",identifier,desired), "validated storage-quota")

def plan_storage_quota(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-quota plan."""
    p=UbuntuPlan(tuple(validate_storage_quota(x) for x in identifiers), {"domain":"storage","resource":"quota"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_quota(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-quota without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-quota:"))
    return {"resource":"storage-quota","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageTmpfsPlan:
    """Bounded declarative policy for storage-tmpfs."""
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
        return "storage-tmpfs:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","tmpfs",self.identifier,self.desired), "reconcile storage-tmpfs")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_tmpfs(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-tmpfs action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-tmpfs:"+identifier, ("ubuntu","storage","tmpfs",identifier,desired), "validated storage-tmpfs")

def plan_storage_tmpfs(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-tmpfs plan."""
    p=UbuntuPlan(tuple(validate_storage_tmpfs(x) for x in identifiers), {"domain":"storage","resource":"tmpfs"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_tmpfs(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-tmpfs without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-tmpfs:"))
    return {"resource":"storage-tmpfs","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class StorageBackupPlan:
    """Bounded declarative policy for storage-backup."""
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
        return "storage-backup:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","storage","backup",self.identifier,self.desired), "reconcile storage-backup")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_storage_backup(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated storage-backup action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("storage-backup:"+identifier, ("ubuntu","storage","backup",identifier,desired), "validated storage-backup")

def plan_storage_backup(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic storage-backup plan."""
    p=UbuntuPlan(tuple(validate_storage_backup(x) for x in identifiers), {"domain":"storage","resource":"backup"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_storage_backup(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit storage-backup without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("storage-backup:"))
    return {"resource":"storage-backup","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimePythonPlan:
    """Bounded declarative policy for runtime-python."""
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
        return "runtime-python:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","python",self.identifier,self.desired), "reconcile runtime-python")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_python(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-python action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-python:"+identifier, ("ubuntu","runtime","python",identifier,desired), "validated runtime-python")

def plan_runtime_python(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-python plan."""
    p=UbuntuPlan(tuple(validate_runtime_python(x) for x in identifiers), {"domain":"runtime","resource":"python"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_python(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-python without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-python:"))
    return {"resource":"runtime-python","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeDockerPlan:
    """Bounded declarative policy for runtime-docker."""
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
        return "runtime-docker:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","docker",self.identifier,self.desired), "reconcile runtime-docker")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_docker(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-docker action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-docker:"+identifier, ("ubuntu","runtime","docker",identifier,desired), "validated runtime-docker")

def plan_runtime_docker(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-docker plan."""
    p=UbuntuPlan(tuple(validate_runtime_docker(x) for x in identifiers), {"domain":"runtime","resource":"docker"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_docker(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-docker without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-docker:"))
    return {"resource":"runtime-docker","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeContainerdPlan:
    """Bounded declarative policy for runtime-containerd."""
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
        return "runtime-containerd:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","containerd",self.identifier,self.desired), "reconcile runtime-containerd")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_containerd(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-containerd action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-containerd:"+identifier, ("ubuntu","runtime","containerd",identifier,desired), "validated runtime-containerd")

def plan_runtime_containerd(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-containerd plan."""
    p=UbuntuPlan(tuple(validate_runtime_containerd(x) for x in identifiers), {"domain":"runtime","resource":"containerd"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_containerd(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-containerd without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-containerd:"))
    return {"resource":"runtime-containerd","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimePodmanPlan:
    """Bounded declarative policy for runtime-podman."""
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
        return "runtime-podman:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","podman",self.identifier,self.desired), "reconcile runtime-podman")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_podman(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-podman action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-podman:"+identifier, ("ubuntu","runtime","podman",identifier,desired), "validated runtime-podman")

def plan_runtime_podman(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-podman plan."""
    p=UbuntuPlan(tuple(validate_runtime_podman(x) for x in identifiers), {"domain":"runtime","resource":"podman"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_podman(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-podman without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-podman:"))
    return {"resource":"runtime-podman","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeBuildxPlan:
    """Bounded declarative policy for runtime-buildx."""
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
        return "runtime-buildx:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","buildx",self.identifier,self.desired), "reconcile runtime-buildx")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_buildx(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-buildx action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-buildx:"+identifier, ("ubuntu","runtime","buildx",identifier,desired), "validated runtime-buildx")

def plan_runtime_buildx(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-buildx plan."""
    p=UbuntuPlan(tuple(validate_runtime_buildx(x) for x in identifiers), {"domain":"runtime","resource":"buildx"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_buildx(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-buildx without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-buildx:"))
    return {"resource":"runtime-buildx","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeQemuPlan:
    """Bounded declarative policy for runtime-qemu."""
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
        return "runtime-qemu:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","qemu",self.identifier,self.desired), "reconcile runtime-qemu")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_qemu(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-qemu action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-qemu:"+identifier, ("ubuntu","runtime","qemu",identifier,desired), "validated runtime-qemu")

def plan_runtime_qemu(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-qemu plan."""
    p=UbuntuPlan(tuple(validate_runtime_qemu(x) for x in identifiers), {"domain":"runtime","resource":"qemu"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_qemu(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-qemu without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-qemu:"))
    return {"resource":"runtime-qemu","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeGccPlan:
    """Bounded declarative policy for runtime-gcc."""
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
        return "runtime-gcc:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","gcc",self.identifier,self.desired), "reconcile runtime-gcc")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_gcc(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-gcc action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-gcc:"+identifier, ("ubuntu","runtime","gcc",identifier,desired), "validated runtime-gcc")

def plan_runtime_gcc(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-gcc plan."""
    p=UbuntuPlan(tuple(validate_runtime_gcc(x) for x in identifiers), {"domain":"runtime","resource":"gcc"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_gcc(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-gcc without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-gcc:"))
    return {"resource":"runtime-gcc","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeNodePlan:
    """Bounded declarative policy for runtime-node."""
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
        return "runtime-node:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","node",self.identifier,self.desired), "reconcile runtime-node")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_node(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-node action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-node:"+identifier, ("ubuntu","runtime","node",identifier,desired), "validated runtime-node")

def plan_runtime_node(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-node plan."""
    p=UbuntuPlan(tuple(validate_runtime_node(x) for x in identifiers), {"domain":"runtime","resource":"node"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_node(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-node without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-node:"))
    return {"resource":"runtime-node","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimeUvPlan:
    """Bounded declarative policy for runtime-uv."""
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
        return "runtime-uv:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","uv",self.identifier,self.desired), "reconcile runtime-uv")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_uv(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-uv action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-uv:"+identifier, ("ubuntu","runtime","uv",identifier,desired), "validated runtime-uv")

def plan_runtime_uv(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-uv plan."""
    p=UbuntuPlan(tuple(validate_runtime_uv(x) for x in identifiers), {"domain":"runtime","resource":"uv"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_uv(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-uv without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-uv:"))
    return {"resource":"runtime-uv","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class RuntimePipPlan:
    """Bounded declarative policy for runtime-pip."""
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
        return "runtime-pip:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","runtime","pip",self.identifier,self.desired), "reconcile runtime-pip")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_runtime_pip(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated runtime-pip action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("runtime-pip:"+identifier, ("ubuntu","runtime","pip",identifier,desired), "validated runtime-pip")

def plan_runtime_pip(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic runtime-pip plan."""
    p=UbuntuPlan(tuple(validate_runtime_pip(x) for x in identifiers), {"domain":"runtime","resource":"pip"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_runtime_pip(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit runtime-pip without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("runtime-pip:"))
    return {"resource":"runtime-pip","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityApparmorPlan:
    """Bounded declarative policy for security-apparmor."""
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
        return "security-apparmor:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","apparmor",self.identifier,self.desired), "reconcile security-apparmor")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_apparmor(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-apparmor action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-apparmor:"+identifier, ("ubuntu","security","apparmor",identifier,desired), "validated security-apparmor")

def plan_security_apparmor(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-apparmor plan."""
    p=UbuntuPlan(tuple(validate_security_apparmor(x) for x in identifiers), {"domain":"security","resource":"apparmor"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_apparmor(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-apparmor without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-apparmor:"))
    return {"resource":"security-apparmor","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityAuditPlan:
    """Bounded declarative policy for security-audit."""
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
        return "security-audit:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","audit",self.identifier,self.desired), "reconcile security-audit")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_audit(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-audit action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-audit:"+identifier, ("ubuntu","security","audit",identifier,desired), "validated security-audit")

def plan_security_audit(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-audit plan."""
    p=UbuntuPlan(tuple(validate_security_audit(x) for x in identifiers), {"domain":"security","resource":"audit"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_audit(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-audit without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-audit:"))
    return {"resource":"security-audit","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityPermissionsPlan:
    """Bounded declarative policy for security-permissions."""
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
        return "security-permissions:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","permissions",self.identifier,self.desired), "reconcile security-permissions")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_permissions(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-permissions action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-permissions:"+identifier, ("ubuntu","security","permissions",identifier,desired), "validated security-permissions")

def plan_security_permissions(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-permissions plan."""
    p=UbuntuPlan(tuple(validate_security_permissions(x) for x in identifiers), {"domain":"security","resource":"permissions"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_permissions(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-permissions without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-permissions:"))
    return {"resource":"security-permissions","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityLimitsPlan:
    """Bounded declarative policy for security-limits."""
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
        return "security-limits:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","limits",self.identifier,self.desired), "reconcile security-limits")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_limits(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-limits action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-limits:"+identifier, ("ubuntu","security","limits",identifier,desired), "validated security-limits")

def plan_security_limits(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-limits plan."""
    p=UbuntuPlan(tuple(validate_security_limits(x) for x in identifiers), {"domain":"security","resource":"limits"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_limits(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-limits without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-limits:"))
    return {"resource":"security-limits","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecuritySysctlPlan:
    """Bounded declarative policy for security-sysctl."""
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
        return "security-sysctl:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","sysctl",self.identifier,self.desired), "reconcile security-sysctl")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_sysctl(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-sysctl action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-sysctl:"+identifier, ("ubuntu","security","sysctl",identifier,desired), "validated security-sysctl")

def plan_security_sysctl(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-sysctl plan."""
    p=UbuntuPlan(tuple(validate_security_sysctl(x) for x in identifiers), {"domain":"security","resource":"sysctl"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_sysctl(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-sysctl without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-sysctl:"))
    return {"resource":"security-sysctl","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecuritySshPlan:
    """Bounded declarative policy for security-ssh."""
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
        return "security-ssh:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","ssh",self.identifier,self.desired), "reconcile security-ssh")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_ssh(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-ssh action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-ssh:"+identifier, ("ubuntu","security","ssh",identifier,desired), "validated security-ssh")

def plan_security_ssh(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-ssh plan."""
    p=UbuntuPlan(tuple(validate_security_ssh(x) for x in identifiers), {"domain":"security","resource":"ssh"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_ssh(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-ssh without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-ssh:"))
    return {"resource":"security-ssh","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecuritySudoPlan:
    """Bounded declarative policy for security-sudo."""
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
        return "security-sudo:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","sudo",self.identifier,self.desired), "reconcile security-sudo")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_sudo(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-sudo action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-sudo:"+identifier, ("ubuntu","security","sudo",identifier,desired), "validated security-sudo")

def plan_security_sudo(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-sudo plan."""
    p=UbuntuPlan(tuple(validate_security_sudo(x) for x in identifiers), {"domain":"security","resource":"sudo"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_sudo(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-sudo without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-sudo:"))
    return {"resource":"security-sudo","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecuritySecretsPlan:
    """Bounded declarative policy for security-secrets."""
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
        return "security-secrets:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","secrets",self.identifier,self.desired), "reconcile security-secrets")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_secrets(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-secrets action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-secrets:"+identifier, ("ubuntu","security","secrets",identifier,desired), "validated security-secrets")

def plan_security_secrets(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-secrets plan."""
    p=UbuntuPlan(tuple(validate_security_secrets(x) for x in identifiers), {"domain":"security","resource":"secrets"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_secrets(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-secrets without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-secrets:"))
    return {"resource":"security-secrets","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityCertPlan:
    """Bounded declarative policy for security-cert."""
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
        return "security-cert:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","cert",self.identifier,self.desired), "reconcile security-cert")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_cert(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-cert action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-cert:"+identifier, ("ubuntu","security","cert",identifier,desired), "validated security-cert")

def plan_security_cert(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-cert plan."""
    p=UbuntuPlan(tuple(validate_security_cert(x) for x in identifiers), {"domain":"security","resource":"cert"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_cert(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-cert without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-cert:"))
    return {"resource":"security-cert","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class SecurityKernelPlan:
    """Bounded declarative policy for security-kernel."""
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
        return "security-kernel:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","security","kernel",self.identifier,self.desired), "reconcile security-kernel")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_security_kernel(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated security-kernel action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("security-kernel:"+identifier, ("ubuntu","security","kernel",identifier,desired), "validated security-kernel")

def plan_security_kernel(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic security-kernel plan."""
    p=UbuntuPlan(tuple(validate_security_kernel(x) for x in identifiers), {"domain":"security","resource":"kernel"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_security_kernel(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit security-kernel without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("security-kernel:"))
    return {"resource":"security-kernel","ok":not e,"errors":e,"count":len(names),"names":names}

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

@dataclass(frozen=True, slots=True)
class CiRunnerPlan:
    """Bounded declarative policy for ci-runner."""
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
        return "ci-runner:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","runner",self.identifier,self.desired), "reconcile ci-runner")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_runner(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-runner action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-runner:"+identifier, ("ubuntu","ci","runner",identifier,desired), "validated ci-runner")

def plan_ci_runner(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-runner plan."""
    p=UbuntuPlan(tuple(validate_ci_runner(x) for x in identifiers), {"domain":"ci","resource":"runner"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_runner(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-runner without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-runner:"))
    return {"resource":"ci-runner","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiCachePlan:
    """Bounded declarative policy for ci-cache."""
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
        return "ci-cache:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","cache",self.identifier,self.desired), "reconcile ci-cache")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_cache(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-cache action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-cache:"+identifier, ("ubuntu","ci","cache",identifier,desired), "validated ci-cache")

def plan_ci_cache(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-cache plan."""
    p=UbuntuPlan(tuple(validate_ci_cache(x) for x in identifiers), {"domain":"ci","resource":"cache"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_cache(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-cache without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-cache:"))
    return {"resource":"ci-cache","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiArtifactPlan:
    """Bounded declarative policy for ci-artifact."""
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
        return "ci-artifact:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","artifact",self.identifier,self.desired), "reconcile ci-artifact")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_artifact(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-artifact action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-artifact:"+identifier, ("ubuntu","ci","artifact",identifier,desired), "validated ci-artifact")

def plan_ci_artifact(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-artifact plan."""
    p=UbuntuPlan(tuple(validate_ci_artifact(x) for x in identifiers), {"domain":"ci","resource":"artifact"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_artifact(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-artifact without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-artifact:"))
    return {"resource":"ci-artifact","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiWorkspacePlan:
    """Bounded declarative policy for ci-workspace."""
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
        return "ci-workspace:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","workspace",self.identifier,self.desired), "reconcile ci-workspace")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_workspace(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-workspace action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-workspace:"+identifier, ("ubuntu","ci","workspace",identifier,desired), "validated ci-workspace")

def plan_ci_workspace(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-workspace plan."""
    p=UbuntuPlan(tuple(validate_ci_workspace(x) for x in identifiers), {"domain":"ci","resource":"workspace"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_workspace(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-workspace without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-workspace:"))
    return {"resource":"ci-workspace","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiCheckoutPlan:
    """Bounded declarative policy for ci-checkout."""
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
        return "ci-checkout:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","checkout",self.identifier,self.desired), "reconcile ci-checkout")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_checkout(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-checkout action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-checkout:"+identifier, ("ubuntu","ci","checkout",identifier,desired), "validated ci-checkout")

def plan_ci_checkout(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-checkout plan."""
    p=UbuntuPlan(tuple(validate_ci_checkout(x) for x in identifiers), {"domain":"ci","resource":"checkout"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_checkout(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-checkout without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-checkout:"))
    return {"resource":"ci-checkout","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiToolchainPlan:
    """Bounded declarative policy for ci-toolchain."""
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
        return "ci-toolchain:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","toolchain",self.identifier,self.desired), "reconcile ci-toolchain")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_toolchain(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-toolchain action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-toolchain:"+identifier, ("ubuntu","ci","toolchain",identifier,desired), "validated ci-toolchain")

def plan_ci_toolchain(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-toolchain plan."""
    p=UbuntuPlan(tuple(validate_ci_toolchain(x) for x in identifiers), {"domain":"ci","resource":"toolchain"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_toolchain(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-toolchain without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-toolchain:"))
    return {"resource":"ci-toolchain","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiTestPlan:
    """Bounded declarative policy for ci-test."""
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
        return "ci-test:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","test",self.identifier,self.desired), "reconcile ci-test")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_test(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-test action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-test:"+identifier, ("ubuntu","ci","test",identifier,desired), "validated ci-test")

def plan_ci_test(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-test plan."""
    p=UbuntuPlan(tuple(validate_ci_test(x) for x in identifiers), {"domain":"ci","resource":"test"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_test(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-test without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-test:"))
    return {"resource":"ci-test","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiLintPlan:
    """Bounded declarative policy for ci-lint."""
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
        return "ci-lint:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","lint",self.identifier,self.desired), "reconcile ci-lint")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_lint(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-lint action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-lint:"+identifier, ("ubuntu","ci","lint",identifier,desired), "validated ci-lint")

def plan_ci_lint(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-lint plan."""
    p=UbuntuPlan(tuple(validate_ci_lint(x) for x in identifiers), {"domain":"ci","resource":"lint"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_lint(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-lint without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-lint:"))
    return {"resource":"ci-lint","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiCoveragePlan:
    """Bounded declarative policy for ci-coverage."""
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
        return "ci-coverage:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","coverage",self.identifier,self.desired), "reconcile ci-coverage")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_coverage(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-coverage action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-coverage:"+identifier, ("ubuntu","ci","coverage",identifier,desired), "validated ci-coverage")

def plan_ci_coverage(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-coverage plan."""
    p=UbuntuPlan(tuple(validate_ci_coverage(x) for x in identifiers), {"domain":"ci","resource":"coverage"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_coverage(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-coverage without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-coverage:"))
    return {"resource":"ci-coverage","ok":not e,"errors":e,"count":len(names),"names":names}

@dataclass(frozen=True, slots=True)
class CiPublishPlan:
    """Bounded declarative policy for ci-publish."""
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
        return "ci-publish:" + self.identifier
    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.desired not in {"present","absent","latest","running","stopped"}: e.append("unsupported desired state")
        if self.enabled and self.desired=="absent": e.append("absent resource cannot be enabled")
        if self.restart and self.desired in {"absent","stopped"}: e.append("restart conflicts with state")
        return tuple(e)
    def action(self) -> UbuntuAction:
        e=self.validate()
        if e: raise ValueError("; ".join(e))
        return UbuntuAction(self.key, ("ubuntu","ci","publish",self.identifier,self.desired), "reconcile ci-publish")
    def to_plan(self) -> UbuntuPlan:
        return UbuntuPlan((self.action(),), {"resource":self.key})

def validate_ci_publish(identifier: str, desired: str = "present", *, enabled: bool = True) -> UbuntuAction:
    """Construct a validated ci-publish action."""
    identifier=_clean(identifier); desired=_clean(desired)
    if desired not in {"present","absent","latest","running","stopped"}: raise ValueError("unsupported desired state")
    if desired=="absent" and enabled: raise ValueError("absent resources cannot be enabled")
    return UbuntuAction("ci-publish:"+identifier, ("ubuntu","ci","publish",identifier,desired), "validated ci-publish")

def plan_ci_publish(identifiers: Sequence[str]) -> UbuntuPlan:
    """Create a deterministic ci-publish plan."""
    p=UbuntuPlan(tuple(validate_ci_publish(x) for x in identifiers), {"domain":"ci","resource":"publish"})
    e=validate_plan(p)
    if e: raise ValueError("; ".join(e))
    return p

def audit_ci_publish(plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit ci-publish without executing it."""
    e=validate_plan(plan)
    names=tuple(a.name for a in plan.actions if a.name.startswith("ci-publish:"))
    return {"resource":"ci-publish","ok":not e,"errors":e,"count":len(names),"names":names}

def ubuntu_contract_4050(value: str) -> str:
    """Bounded Ubuntu integration contract 4050."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4050:"+value
    
def ubuntu_contract_4056(value: str) -> str:
    """Bounded Ubuntu integration contract 4056."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4056:"+value
    
def ubuntu_contract_4062(value: str) -> str:
    """Bounded Ubuntu integration contract 4062."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4062:"+value
    
def ubuntu_contract_4068(value: str) -> str:
    """Bounded Ubuntu integration contract 4068."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4068:"+value
    
def ubuntu_contract_4074(value: str) -> str:
    """Bounded Ubuntu integration contract 4074."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4074:"+value
    
def ubuntu_contract_4080(value: str) -> str:
    """Bounded Ubuntu integration contract 4080."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4080:"+value
    
def ubuntu_contract_4086(value: str) -> str:
    """Bounded Ubuntu integration contract 4086."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4086:"+value
    
def ubuntu_contract_4092(value: str) -> str:
    """Bounded Ubuntu integration contract 4092."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4092:"+value
    
def ubuntu_contract_4098(value: str) -> str:
    """Bounded Ubuntu integration contract 4098."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4098:"+value
    
def ubuntu_contract_4104(value: str) -> str:
    """Bounded Ubuntu integration contract 4104."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4104:"+value
    
def ubuntu_contract_4110(value: str) -> str:
    """Bounded Ubuntu integration contract 4110."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4110:"+value
    
def ubuntu_contract_4116(value: str) -> str:
    """Bounded Ubuntu integration contract 4116."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4116:"+value
    
def ubuntu_contract_4122(value: str) -> str:
    """Bounded Ubuntu integration contract 4122."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4122:"+value
    
def ubuntu_contract_4128(value: str) -> str:
    """Bounded Ubuntu integration contract 4128."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4128:"+value
    
def ubuntu_contract_4134(value: str) -> str:
    """Bounded Ubuntu integration contract 4134."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4134:"+value
    
def ubuntu_contract_4140(value: str) -> str:
    """Bounded Ubuntu integration contract 4140."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4140:"+value
    
def ubuntu_contract_4146(value: str) -> str:
    """Bounded Ubuntu integration contract 4146."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4146:"+value
    
def ubuntu_contract_4152(value: str) -> str:
    """Bounded Ubuntu integration contract 4152."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4152:"+value
    
def ubuntu_contract_4158(value: str) -> str:
    """Bounded Ubuntu integration contract 4158."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4158:"+value
    
def ubuntu_contract_4164(value: str) -> str:
    """Bounded Ubuntu integration contract 4164."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4164:"+value
    
def ubuntu_contract_4170(value: str) -> str:
    """Bounded Ubuntu integration contract 4170."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4170:"+value
    
def ubuntu_contract_4176(value: str) -> str:
    """Bounded Ubuntu integration contract 4176."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4176:"+value
    
def ubuntu_contract_4182(value: str) -> str:
    """Bounded Ubuntu integration contract 4182."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4182:"+value
    
def ubuntu_contract_4188(value: str) -> str:
    """Bounded Ubuntu integration contract 4188."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4188:"+value
    
def ubuntu_contract_4194(value: str) -> str:
    """Bounded Ubuntu integration contract 4194."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4194:"+value
    
def ubuntu_contract_4200(value: str) -> str:
    """Bounded Ubuntu integration contract 4200."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4200:"+value
    
def ubuntu_contract_4206(value: str) -> str:
    """Bounded Ubuntu integration contract 4206."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4206:"+value
    
def ubuntu_contract_4212(value: str) -> str:
    """Bounded Ubuntu integration contract 4212."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4212:"+value
    
def ubuntu_contract_4218(value: str) -> str:
    """Bounded Ubuntu integration contract 4218."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4218:"+value
    
def ubuntu_contract_4224(value: str) -> str:
    """Bounded Ubuntu integration contract 4224."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4224:"+value
    
def ubuntu_contract_4230(value: str) -> str:
    """Bounded Ubuntu integration contract 4230."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4230:"+value
    
def ubuntu_contract_4236(value: str) -> str:
    """Bounded Ubuntu integration contract 4236."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4236:"+value
    
def ubuntu_contract_4242(value: str) -> str:
    """Bounded Ubuntu integration contract 4242."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4242:"+value
    
def ubuntu_contract_4248(value: str) -> str:
    """Bounded Ubuntu integration contract 4248."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4248:"+value
    
def ubuntu_contract_4254(value: str) -> str:
    """Bounded Ubuntu integration contract 4254."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4254:"+value
    
def ubuntu_contract_4260(value: str) -> str:
    """Bounded Ubuntu integration contract 4260."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4260:"+value
    
def ubuntu_contract_4266(value: str) -> str:
    """Bounded Ubuntu integration contract 4266."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4266:"+value
    
def ubuntu_contract_4272(value: str) -> str:
    """Bounded Ubuntu integration contract 4272."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4272:"+value
    
def ubuntu_contract_4278(value: str) -> str:
    """Bounded Ubuntu integration contract 4278."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4278:"+value
    
def ubuntu_contract_4284(value: str) -> str:
    """Bounded Ubuntu integration contract 4284."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4284:"+value
    
def ubuntu_contract_4290(value: str) -> str:
    """Bounded Ubuntu integration contract 4290."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4290:"+value
    
def ubuntu_contract_4296(value: str) -> str:
    """Bounded Ubuntu integration contract 4296."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4296:"+value
    
def ubuntu_contract_4302(value: str) -> str:
    """Bounded Ubuntu integration contract 4302."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4302:"+value
    
def ubuntu_contract_4308(value: str) -> str:
    """Bounded Ubuntu integration contract 4308."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4308:"+value
    
def ubuntu_contract_4314(value: str) -> str:
    """Bounded Ubuntu integration contract 4314."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4314:"+value
    
def ubuntu_contract_4320(value: str) -> str:
    """Bounded Ubuntu integration contract 4320."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4320:"+value
    
def ubuntu_contract_4326(value: str) -> str:
    """Bounded Ubuntu integration contract 4326."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4326:"+value
    
def ubuntu_contract_4332(value: str) -> str:
    """Bounded Ubuntu integration contract 4332."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4332:"+value
    
def ubuntu_contract_4338(value: str) -> str:
    """Bounded Ubuntu integration contract 4338."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4338:"+value
    
def ubuntu_contract_4344(value: str) -> str:
    """Bounded Ubuntu integration contract 4344."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4344:"+value
    
def ubuntu_contract_4350(value: str) -> str:
    """Bounded Ubuntu integration contract 4350."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4350:"+value
    
def ubuntu_contract_4356(value: str) -> str:
    """Bounded Ubuntu integration contract 4356."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4356:"+value
    
def ubuntu_contract_4362(value: str) -> str:
    """Bounded Ubuntu integration contract 4362."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4362:"+value
    
def ubuntu_contract_4368(value: str) -> str:
    """Bounded Ubuntu integration contract 4368."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4368:"+value
    
def ubuntu_contract_4374(value: str) -> str:
    """Bounded Ubuntu integration contract 4374."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4374:"+value
    
def ubuntu_contract_4380(value: str) -> str:
    """Bounded Ubuntu integration contract 4380."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4380:"+value
    
def ubuntu_contract_4386(value: str) -> str:
    """Bounded Ubuntu integration contract 4386."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4386:"+value
    
def ubuntu_contract_4392(value: str) -> str:
    """Bounded Ubuntu integration contract 4392."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4392:"+value
    
def ubuntu_contract_4398(value: str) -> str:
    """Bounded Ubuntu integration contract 4398."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4398:"+value
    
def ubuntu_contract_4404(value: str) -> str:
    """Bounded Ubuntu integration contract 4404."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4404:"+value
    
def ubuntu_contract_4410(value: str) -> str:
    """Bounded Ubuntu integration contract 4410."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4410:"+value
    
def ubuntu_contract_4416(value: str) -> str:
    """Bounded Ubuntu integration contract 4416."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4416:"+value
    
def ubuntu_contract_4422(value: str) -> str:
    """Bounded Ubuntu integration contract 4422."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4422:"+value
    
def ubuntu_contract_4428(value: str) -> str:
    """Bounded Ubuntu integration contract 4428."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4428:"+value
    
def ubuntu_contract_4434(value: str) -> str:
    """Bounded Ubuntu integration contract 4434."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4434:"+value
    
def ubuntu_contract_4440(value: str) -> str:
    """Bounded Ubuntu integration contract 4440."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4440:"+value
    
def ubuntu_contract_4446(value: str) -> str:
    """Bounded Ubuntu integration contract 4446."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4446:"+value
    
def ubuntu_contract_4452(value: str) -> str:
    """Bounded Ubuntu integration contract 4452."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4452:"+value
    
def ubuntu_contract_4458(value: str) -> str:
    """Bounded Ubuntu integration contract 4458."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4458:"+value
    
def ubuntu_contract_4464(value: str) -> str:
    """Bounded Ubuntu integration contract 4464."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4464:"+value
    
def ubuntu_contract_4470(value: str) -> str:
    """Bounded Ubuntu integration contract 4470."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4470:"+value
    
def ubuntu_contract_4476(value: str) -> str:
    """Bounded Ubuntu integration contract 4476."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4476:"+value
    
def ubuntu_contract_4482(value: str) -> str:
    """Bounded Ubuntu integration contract 4482."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4482:"+value
    
def ubuntu_contract_4488(value: str) -> str:
    """Bounded Ubuntu integration contract 4488."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4488:"+value
    
def ubuntu_contract_4494(value: str) -> str:
    """Bounded Ubuntu integration contract 4494."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4494:"+value
    
def ubuntu_contract_4500(value: str) -> str:
    """Bounded Ubuntu integration contract 4500."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4500:"+value
    
def ubuntu_contract_4506(value: str) -> str:
    """Bounded Ubuntu integration contract 4506."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4506:"+value
    
def ubuntu_contract_4512(value: str) -> str:
    """Bounded Ubuntu integration contract 4512."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4512:"+value
    
def ubuntu_contract_4518(value: str) -> str:
    """Bounded Ubuntu integration contract 4518."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4518:"+value
    
def ubuntu_contract_4524(value: str) -> str:
    """Bounded Ubuntu integration contract 4524."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4524:"+value
    
def ubuntu_contract_4530(value: str) -> str:
    """Bounded Ubuntu integration contract 4530."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4530:"+value
    
def ubuntu_contract_4536(value: str) -> str:
    """Bounded Ubuntu integration contract 4536."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4536:"+value
    
def ubuntu_contract_4542(value: str) -> str:
    """Bounded Ubuntu integration contract 4542."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4542:"+value
    
def ubuntu_contract_4548(value: str) -> str:
    """Bounded Ubuntu integration contract 4548."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4548:"+value
    
def ubuntu_contract_4554(value: str) -> str:
    """Bounded Ubuntu integration contract 4554."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4554:"+value
    
def ubuntu_contract_4560(value: str) -> str:
    """Bounded Ubuntu integration contract 4560."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4560:"+value
    
def ubuntu_contract_4566(value: str) -> str:
    """Bounded Ubuntu integration contract 4566."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4566:"+value
    
def ubuntu_contract_4572(value: str) -> str:
    """Bounded Ubuntu integration contract 4572."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4572:"+value
    
def ubuntu_contract_4578(value: str) -> str:
    """Bounded Ubuntu integration contract 4578."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4578:"+value
    
def ubuntu_contract_4584(value: str) -> str:
    """Bounded Ubuntu integration contract 4584."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4584:"+value
    
def ubuntu_contract_4590(value: str) -> str:
    """Bounded Ubuntu integration contract 4590."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4590:"+value
    
def ubuntu_contract_4596(value: str) -> str:
    """Bounded Ubuntu integration contract 4596."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4596:"+value
    
def ubuntu_contract_4602(value: str) -> str:
    """Bounded Ubuntu integration contract 4602."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4602:"+value
    
def ubuntu_contract_4608(value: str) -> str:
    """Bounded Ubuntu integration contract 4608."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4608:"+value
    
def ubuntu_contract_4614(value: str) -> str:
    """Bounded Ubuntu integration contract 4614."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4614:"+value
    
def ubuntu_contract_4620(value: str) -> str:
    """Bounded Ubuntu integration contract 4620."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4620:"+value
    
def ubuntu_contract_4626(value: str) -> str:
    """Bounded Ubuntu integration contract 4626."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4626:"+value
    
def ubuntu_contract_4632(value: str) -> str:
    """Bounded Ubuntu integration contract 4632."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4632:"+value
    
def ubuntu_contract_4638(value: str) -> str:
    """Bounded Ubuntu integration contract 4638."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4638:"+value
    
def ubuntu_contract_4644(value: str) -> str:
    """Bounded Ubuntu integration contract 4644."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4644:"+value
    
def ubuntu_contract_4650(value: str) -> str:
    """Bounded Ubuntu integration contract 4650."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4650:"+value
    
def ubuntu_contract_4656(value: str) -> str:
    """Bounded Ubuntu integration contract 4656."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4656:"+value
    
def ubuntu_contract_4662(value: str) -> str:
    """Bounded Ubuntu integration contract 4662."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4662:"+value
    
def ubuntu_contract_4668(value: str) -> str:
    """Bounded Ubuntu integration contract 4668."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4668:"+value
    
def ubuntu_contract_4674(value: str) -> str:
    """Bounded Ubuntu integration contract 4674."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4674:"+value
    
def ubuntu_contract_4680(value: str) -> str:
    """Bounded Ubuntu integration contract 4680."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4680:"+value
    
def ubuntu_contract_4686(value: str) -> str:
    """Bounded Ubuntu integration contract 4686."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4686:"+value
    
def ubuntu_contract_4692(value: str) -> str:
    """Bounded Ubuntu integration contract 4692."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4692:"+value
    
def ubuntu_contract_4698(value: str) -> str:
    """Bounded Ubuntu integration contract 4698."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4698:"+value
    
def ubuntu_contract_4704(value: str) -> str:
    """Bounded Ubuntu integration contract 4704."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4704:"+value
    
def ubuntu_contract_4710(value: str) -> str:
    """Bounded Ubuntu integration contract 4710."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4710:"+value
    
def ubuntu_contract_4716(value: str) -> str:
    """Bounded Ubuntu integration contract 4716."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4716:"+value
    
def ubuntu_contract_4722(value: str) -> str:
    """Bounded Ubuntu integration contract 4722."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4722:"+value
    
def ubuntu_contract_4728(value: str) -> str:
    """Bounded Ubuntu integration contract 4728."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4728:"+value
    
def ubuntu_contract_4734(value: str) -> str:
    """Bounded Ubuntu integration contract 4734."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4734:"+value
    
def ubuntu_contract_4740(value: str) -> str:
    """Bounded Ubuntu integration contract 4740."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4740:"+value
    
def ubuntu_contract_4746(value: str) -> str:
    """Bounded Ubuntu integration contract 4746."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4746:"+value
    
def ubuntu_contract_4752(value: str) -> str:
    """Bounded Ubuntu integration contract 4752."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4752:"+value
    
def ubuntu_contract_4758(value: str) -> str:
    """Bounded Ubuntu integration contract 4758."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4758:"+value
    
def ubuntu_contract_4764(value: str) -> str:
    """Bounded Ubuntu integration contract 4764."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4764:"+value
    
def ubuntu_contract_4770(value: str) -> str:
    """Bounded Ubuntu integration contract 4770."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4770:"+value
    
def ubuntu_contract_4776(value: str) -> str:
    """Bounded Ubuntu integration contract 4776."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4776:"+value
    
def ubuntu_contract_4782(value: str) -> str:
    """Bounded Ubuntu integration contract 4782."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4782:"+value
    
def ubuntu_contract_4788(value: str) -> str:
    """Bounded Ubuntu integration contract 4788."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4788:"+value
    
def ubuntu_contract_4794(value: str) -> str:
    """Bounded Ubuntu integration contract 4794."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4794:"+value
    
def ubuntu_contract_4800(value: str) -> str:
    """Bounded Ubuntu integration contract 4800."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4800:"+value
    
def ubuntu_contract_4806(value: str) -> str:
    """Bounded Ubuntu integration contract 4806."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4806:"+value
    
def ubuntu_contract_4812(value: str) -> str:
    """Bounded Ubuntu integration contract 4812."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4812:"+value
    
def ubuntu_contract_4818(value: str) -> str:
    """Bounded Ubuntu integration contract 4818."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4818:"+value
    
def ubuntu_contract_4824(value: str) -> str:
    """Bounded Ubuntu integration contract 4824."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4824:"+value
    
def ubuntu_contract_4830(value: str) -> str:
    """Bounded Ubuntu integration contract 4830."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4830:"+value
    
def ubuntu_contract_4836(value: str) -> str:
    """Bounded Ubuntu integration contract 4836."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4836:"+value
    
def ubuntu_contract_4842(value: str) -> str:
    """Bounded Ubuntu integration contract 4842."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4842:"+value
    
def ubuntu_contract_4848(value: str) -> str:
    """Bounded Ubuntu integration contract 4848."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4848:"+value
    
def ubuntu_contract_4854(value: str) -> str:
    """Bounded Ubuntu integration contract 4854."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4854:"+value
    
def ubuntu_contract_4860(value: str) -> str:
    """Bounded Ubuntu integration contract 4860."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4860:"+value
    
def ubuntu_contract_4866(value: str) -> str:
    """Bounded Ubuntu integration contract 4866."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4866:"+value
    
def ubuntu_contract_4872(value: str) -> str:
    """Bounded Ubuntu integration contract 4872."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4872:"+value
    
def ubuntu_contract_4878(value: str) -> str:
    """Bounded Ubuntu integration contract 4878."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4878:"+value
    
def ubuntu_contract_4884(value: str) -> str:
    """Bounded Ubuntu integration contract 4884."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4884:"+value
    
def ubuntu_contract_4890(value: str) -> str:
    """Bounded Ubuntu integration contract 4890."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4890:"+value
    
def ubuntu_contract_4896(value: str) -> str:
    """Bounded Ubuntu integration contract 4896."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4896:"+value
    
def ubuntu_contract_4902(value: str) -> str:
    """Bounded Ubuntu integration contract 4902."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4902:"+value
    
def ubuntu_contract_4908(value: str) -> str:
    """Bounded Ubuntu integration contract 4908."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4908:"+value
    
def ubuntu_contract_4914(value: str) -> str:
    """Bounded Ubuntu integration contract 4914."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4914:"+value
    
def ubuntu_contract_4920(value: str) -> str:
    """Bounded Ubuntu integration contract 4920."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4920:"+value
    
def ubuntu_contract_4926(value: str) -> str:
    """Bounded Ubuntu integration contract 4926."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4926:"+value
    
def ubuntu_contract_4932(value: str) -> str:
    """Bounded Ubuntu integration contract 4932."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4932:"+value
    
def ubuntu_contract_4938(value: str) -> str:
    """Bounded Ubuntu integration contract 4938."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4938:"+value
    
def ubuntu_contract_4944(value: str) -> str:
    """Bounded Ubuntu integration contract 4944."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4944:"+value
    
def ubuntu_contract_4950(value: str) -> str:
    """Bounded Ubuntu integration contract 4950."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4950:"+value
    
def ubuntu_contract_4956(value: str) -> str:
    """Bounded Ubuntu integration contract 4956."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4956:"+value
    
def ubuntu_contract_4962(value: str) -> str:
    """Bounded Ubuntu integration contract 4962."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4962:"+value
    
def ubuntu_contract_4968(value: str) -> str:
    """Bounded Ubuntu integration contract 4968."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4968:"+value
    
def ubuntu_contract_4974(value: str) -> str:
    """Bounded Ubuntu integration contract 4974."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4974:"+value
    
def ubuntu_contract_4980(value: str) -> str:
    """Bounded Ubuntu integration contract 4980."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4980:"+value
    
def ubuntu_contract_4986(value: str) -> str:
    """Bounded Ubuntu integration contract 4986."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4986:"+value
    
def ubuntu_contract_4992(value: str) -> str:
    """Bounded Ubuntu integration contract 4992."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4992:"+value
    
def ubuntu_contract_4998(value: str) -> str:
    """Bounded Ubuntu integration contract 4998."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-4998:"+value
    
def ubuntu_contract_5004(value: str) -> str:
    """Bounded Ubuntu integration contract 5004."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5004:"+value
    
def ubuntu_contract_5010(value: str) -> str:
    """Bounded Ubuntu integration contract 5010."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5010:"+value
    
def ubuntu_contract_5016(value: str) -> str:
    """Bounded Ubuntu integration contract 5016."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5016:"+value
    
def ubuntu_contract_5022(value: str) -> str:
    """Bounded Ubuntu integration contract 5022."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5022:"+value
    
def ubuntu_contract_5028(value: str) -> str:
    """Bounded Ubuntu integration contract 5028."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5028:"+value
    
def ubuntu_contract_5034(value: str) -> str:
    """Bounded Ubuntu integration contract 5034."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5034:"+value
    
def ubuntu_contract_5040(value: str) -> str:
    """Bounded Ubuntu integration contract 5040."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5040:"+value
    
def ubuntu_contract_5046(value: str) -> str:
    """Bounded Ubuntu integration contract 5046."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5046:"+value
    
def ubuntu_contract_5052(value: str) -> str:
    """Bounded Ubuntu integration contract 5052."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5052:"+value
    
def ubuntu_contract_5058(value: str) -> str:
    """Bounded Ubuntu integration contract 5058."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5058:"+value
    
def ubuntu_contract_5064(value: str) -> str:
    """Bounded Ubuntu integration contract 5064."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5064:"+value
    
def ubuntu_contract_5070(value: str) -> str:
    """Bounded Ubuntu integration contract 5070."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5070:"+value
    
def ubuntu_contract_5076(value: str) -> str:
    """Bounded Ubuntu integration contract 5076."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5076:"+value
    
def ubuntu_contract_5082(value: str) -> str:
    """Bounded Ubuntu integration contract 5082."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5082:"+value
    
def ubuntu_contract_5088(value: str) -> str:
    """Bounded Ubuntu integration contract 5088."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5088:"+value
    
def ubuntu_contract_5094(value: str) -> str:
    """Bounded Ubuntu integration contract 5094."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5094:"+value
    
def ubuntu_contract_5100(value: str) -> str:
    """Bounded Ubuntu integration contract 5100."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5100:"+value
    
def ubuntu_contract_5106(value: str) -> str:
    """Bounded Ubuntu integration contract 5106."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5106:"+value
    
def ubuntu_contract_5112(value: str) -> str:
    """Bounded Ubuntu integration contract 5112."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5112:"+value
    
def ubuntu_contract_5118(value: str) -> str:
    """Bounded Ubuntu integration contract 5118."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5118:"+value
    
def ubuntu_contract_5124(value: str) -> str:
    """Bounded Ubuntu integration contract 5124."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5124:"+value
    
def ubuntu_contract_5130(value: str) -> str:
    """Bounded Ubuntu integration contract 5130."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5130:"+value
    
def ubuntu_contract_5136(value: str) -> str:
    """Bounded Ubuntu integration contract 5136."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5136:"+value
    
def ubuntu_contract_5142(value: str) -> str:
    """Bounded Ubuntu integration contract 5142."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5142:"+value
    
def ubuntu_contract_5148(value: str) -> str:
    """Bounded Ubuntu integration contract 5148."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5148:"+value
    
def ubuntu_contract_5154(value: str) -> str:
    """Bounded Ubuntu integration contract 5154."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5154:"+value
    
def ubuntu_contract_5160(value: str) -> str:
    """Bounded Ubuntu integration contract 5160."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5160:"+value
    
def ubuntu_contract_5166(value: str) -> str:
    """Bounded Ubuntu integration contract 5166."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5166:"+value
    
def ubuntu_contract_5172(value: str) -> str:
    """Bounded Ubuntu integration contract 5172."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5172:"+value
    
def ubuntu_contract_5178(value: str) -> str:
    """Bounded Ubuntu integration contract 5178."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5178:"+value
    
def ubuntu_contract_5184(value: str) -> str:
    """Bounded Ubuntu integration contract 5184."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5184:"+value
    
def ubuntu_contract_5190(value: str) -> str:
    """Bounded Ubuntu integration contract 5190."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5190:"+value
    
def ubuntu_contract_5196(value: str) -> str:
    """Bounded Ubuntu integration contract 5196."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5196:"+value
    
def ubuntu_contract_5202(value: str) -> str:
    """Bounded Ubuntu integration contract 5202."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5202:"+value
    
def ubuntu_contract_5208(value: str) -> str:
    """Bounded Ubuntu integration contract 5208."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5208:"+value
    
def ubuntu_contract_5214(value: str) -> str:
    """Bounded Ubuntu integration contract 5214."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5214:"+value
    
def ubuntu_contract_5220(value: str) -> str:
    """Bounded Ubuntu integration contract 5220."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5220:"+value
    
def ubuntu_contract_5226(value: str) -> str:
    """Bounded Ubuntu integration contract 5226."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5226:"+value
    
def ubuntu_contract_5232(value: str) -> str:
    """Bounded Ubuntu integration contract 5232."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5232:"+value
    
def ubuntu_contract_5238(value: str) -> str:
    """Bounded Ubuntu integration contract 5238."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5238:"+value
    
def ubuntu_contract_5244(value: str) -> str:
    """Bounded Ubuntu integration contract 5244."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5244:"+value
    
def ubuntu_contract_5250(value: str) -> str:
    """Bounded Ubuntu integration contract 5250."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5250:"+value
    
def ubuntu_contract_5256(value: str) -> str:
    """Bounded Ubuntu integration contract 5256."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5256:"+value
    
def ubuntu_contract_5262(value: str) -> str:
    """Bounded Ubuntu integration contract 5262."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5262:"+value
    
def ubuntu_contract_5268(value: str) -> str:
    """Bounded Ubuntu integration contract 5268."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5268:"+value
    
def ubuntu_contract_5274(value: str) -> str:
    """Bounded Ubuntu integration contract 5274."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5274:"+value
    
def ubuntu_contract_5280(value: str) -> str:
    """Bounded Ubuntu integration contract 5280."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5280:"+value
    
def ubuntu_contract_5286(value: str) -> str:
    """Bounded Ubuntu integration contract 5286."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5286:"+value
    
def ubuntu_contract_5292(value: str) -> str:
    """Bounded Ubuntu integration contract 5292."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5292:"+value
    
def ubuntu_contract_5298(value: str) -> str:
    """Bounded Ubuntu integration contract 5298."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5298:"+value
    
def ubuntu_contract_5304(value: str) -> str:
    """Bounded Ubuntu integration contract 5304."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5304:"+value
    
def ubuntu_contract_5310(value: str) -> str:
    """Bounded Ubuntu integration contract 5310."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5310:"+value
    
def ubuntu_contract_5316(value: str) -> str:
    """Bounded Ubuntu integration contract 5316."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5316:"+value
    
def ubuntu_contract_5322(value: str) -> str:
    """Bounded Ubuntu integration contract 5322."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5322:"+value
    
def ubuntu_contract_5328(value: str) -> str:
    """Bounded Ubuntu integration contract 5328."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5328:"+value
    
def ubuntu_contract_5334(value: str) -> str:
    """Bounded Ubuntu integration contract 5334."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5334:"+value
    
def ubuntu_contract_5340(value: str) -> str:
    """Bounded Ubuntu integration contract 5340."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5340:"+value
    
def ubuntu_contract_5346(value: str) -> str:
    """Bounded Ubuntu integration contract 5346."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5346:"+value
    
def ubuntu_contract_5352(value: str) -> str:
    """Bounded Ubuntu integration contract 5352."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5352:"+value
    
def ubuntu_contract_5358(value: str) -> str:
    """Bounded Ubuntu integration contract 5358."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5358:"+value
    
def ubuntu_contract_5364(value: str) -> str:
    """Bounded Ubuntu integration contract 5364."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5364:"+value
    
def ubuntu_contract_5370(value: str) -> str:
    """Bounded Ubuntu integration contract 5370."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5370:"+value
    
def ubuntu_contract_5376(value: str) -> str:
    """Bounded Ubuntu integration contract 5376."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5376:"+value
    
def ubuntu_contract_5382(value: str) -> str:
    """Bounded Ubuntu integration contract 5382."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5382:"+value
    
def ubuntu_contract_5388(value: str) -> str:
    """Bounded Ubuntu integration contract 5388."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5388:"+value
    
def ubuntu_contract_5394(value: str) -> str:
    """Bounded Ubuntu integration contract 5394."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5394:"+value
    
def ubuntu_contract_5400(value: str) -> str:
    """Bounded Ubuntu integration contract 5400."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5400:"+value
    
def ubuntu_contract_5406(value: str) -> str:
    """Bounded Ubuntu integration contract 5406."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5406:"+value
    
def ubuntu_contract_5412(value: str) -> str:
    """Bounded Ubuntu integration contract 5412."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5412:"+value
    
def ubuntu_contract_5418(value: str) -> str:
    """Bounded Ubuntu integration contract 5418."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5418:"+value
    
def ubuntu_contract_5424(value: str) -> str:
    """Bounded Ubuntu integration contract 5424."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5424:"+value
    
def ubuntu_contract_5430(value: str) -> str:
    """Bounded Ubuntu integration contract 5430."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5430:"+value
    
def ubuntu_contract_5436(value: str) -> str:
    """Bounded Ubuntu integration contract 5436."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5436:"+value
    
def ubuntu_contract_5442(value: str) -> str:
    """Bounded Ubuntu integration contract 5442."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5442:"+value
    
def ubuntu_contract_5448(value: str) -> str:
    """Bounded Ubuntu integration contract 5448."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5448:"+value
    
def ubuntu_contract_5454(value: str) -> str:
    """Bounded Ubuntu integration contract 5454."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5454:"+value
    
def ubuntu_contract_5460(value: str) -> str:
    """Bounded Ubuntu integration contract 5460."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5460:"+value
    
def ubuntu_contract_5466(value: str) -> str:
    """Bounded Ubuntu integration contract 5466."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5466:"+value
    
def ubuntu_contract_5472(value: str) -> str:
    """Bounded Ubuntu integration contract 5472."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5472:"+value
    
def ubuntu_contract_5478(value: str) -> str:
    """Bounded Ubuntu integration contract 5478."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5478:"+value
    
def ubuntu_contract_5484(value: str) -> str:
    """Bounded Ubuntu integration contract 5484."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5484:"+value
    
def ubuntu_contract_5490(value: str) -> str:
    """Bounded Ubuntu integration contract 5490."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5490:"+value
    
def ubuntu_contract_5496(value: str) -> str:
    """Bounded Ubuntu integration contract 5496."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5496:"+value
    
def ubuntu_contract_5502(value: str) -> str:
    """Bounded Ubuntu integration contract 5502."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5502:"+value
    
def ubuntu_contract_5508(value: str) -> str:
    """Bounded Ubuntu integration contract 5508."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5508:"+value
    
def ubuntu_contract_5514(value: str) -> str:
    """Bounded Ubuntu integration contract 5514."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5514:"+value
    
def ubuntu_contract_5520(value: str) -> str:
    """Bounded Ubuntu integration contract 5520."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5520:"+value
    
def ubuntu_contract_5526(value: str) -> str:
    """Bounded Ubuntu integration contract 5526."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5526:"+value
    
def ubuntu_contract_5532(value: str) -> str:
    """Bounded Ubuntu integration contract 5532."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5532:"+value
    
def ubuntu_contract_5538(value: str) -> str:
    """Bounded Ubuntu integration contract 5538."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5538:"+value
    
def ubuntu_contract_5544(value: str) -> str:
    """Bounded Ubuntu integration contract 5544."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5544:"+value
    
def ubuntu_contract_5550(value: str) -> str:
    """Bounded Ubuntu integration contract 5550."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5550:"+value
    
def ubuntu_contract_5556(value: str) -> str:
    """Bounded Ubuntu integration contract 5556."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5556:"+value
    
def ubuntu_contract_5562(value: str) -> str:
    """Bounded Ubuntu integration contract 5562."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5562:"+value
    
def ubuntu_contract_5568(value: str) -> str:
    """Bounded Ubuntu integration contract 5568."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5568:"+value
    
def ubuntu_contract_5574(value: str) -> str:
    """Bounded Ubuntu integration contract 5574."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5574:"+value
    
def ubuntu_contract_5580(value: str) -> str:
    """Bounded Ubuntu integration contract 5580."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5580:"+value
    
def ubuntu_contract_5586(value: str) -> str:
    """Bounded Ubuntu integration contract 5586."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5586:"+value
    
def ubuntu_contract_5592(value: str) -> str:
    """Bounded Ubuntu integration contract 5592."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5592:"+value
    
def ubuntu_contract_5598(value: str) -> str:
    """Bounded Ubuntu integration contract 5598."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5598:"+value
    
def ubuntu_contract_5604(value: str) -> str:
    """Bounded Ubuntu integration contract 5604."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5604:"+value
    
def ubuntu_contract_5610(value: str) -> str:
    """Bounded Ubuntu integration contract 5610."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5610:"+value
    
def ubuntu_contract_5616(value: str) -> str:
    """Bounded Ubuntu integration contract 5616."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5616:"+value
    
def ubuntu_contract_5622(value: str) -> str:
    """Bounded Ubuntu integration contract 5622."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5622:"+value
    
def ubuntu_contract_5628(value: str) -> str:
    """Bounded Ubuntu integration contract 5628."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5628:"+value
    
def ubuntu_contract_5634(value: str) -> str:
    """Bounded Ubuntu integration contract 5634."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5634:"+value
    
def ubuntu_contract_5640(value: str) -> str:
    """Bounded Ubuntu integration contract 5640."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5640:"+value
    
def ubuntu_contract_5646(value: str) -> str:
    """Bounded Ubuntu integration contract 5646."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5646:"+value
    
def ubuntu_contract_5652(value: str) -> str:
    """Bounded Ubuntu integration contract 5652."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5652:"+value
    
def ubuntu_contract_5658(value: str) -> str:
    """Bounded Ubuntu integration contract 5658."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5658:"+value
    
def ubuntu_contract_5664(value: str) -> str:
    """Bounded Ubuntu integration contract 5664."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5664:"+value
    
def ubuntu_contract_5670(value: str) -> str:
    """Bounded Ubuntu integration contract 5670."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5670:"+value
    
def ubuntu_contract_5676(value: str) -> str:
    """Bounded Ubuntu integration contract 5676."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5676:"+value
    
def ubuntu_contract_5682(value: str) -> str:
    """Bounded Ubuntu integration contract 5682."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5682:"+value
    
def ubuntu_contract_5688(value: str) -> str:
    """Bounded Ubuntu integration contract 5688."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5688:"+value
    
def ubuntu_contract_5694(value: str) -> str:
    """Bounded Ubuntu integration contract 5694."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5694:"+value
    
def ubuntu_contract_5700(value: str) -> str:
    """Bounded Ubuntu integration contract 5700."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5700:"+value
    
def ubuntu_contract_5706(value: str) -> str:
    """Bounded Ubuntu integration contract 5706."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5706:"+value
    
def ubuntu_contract_5712(value: str) -> str:
    """Bounded Ubuntu integration contract 5712."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5712:"+value
    
def ubuntu_contract_5718(value: str) -> str:
    """Bounded Ubuntu integration contract 5718."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5718:"+value
    
def ubuntu_contract_5724(value: str) -> str:
    """Bounded Ubuntu integration contract 5724."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5724:"+value
    
def ubuntu_contract_5730(value: str) -> str:
    """Bounded Ubuntu integration contract 5730."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5730:"+value
    
def ubuntu_contract_5736(value: str) -> str:
    """Bounded Ubuntu integration contract 5736."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5736:"+value
    
def ubuntu_contract_5742(value: str) -> str:
    """Bounded Ubuntu integration contract 5742."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5742:"+value
    
def ubuntu_contract_5748(value: str) -> str:
    """Bounded Ubuntu integration contract 5748."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5748:"+value
    
def ubuntu_contract_5754(value: str) -> str:
    """Bounded Ubuntu integration contract 5754."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5754:"+value
    
def ubuntu_contract_5760(value: str) -> str:
    """Bounded Ubuntu integration contract 5760."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5760:"+value
    
def ubuntu_contract_5766(value: str) -> str:
    """Bounded Ubuntu integration contract 5766."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5766:"+value
    
def ubuntu_contract_5772(value: str) -> str:
    """Bounded Ubuntu integration contract 5772."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5772:"+value
    
def ubuntu_contract_5778(value: str) -> str:
    """Bounded Ubuntu integration contract 5778."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5778:"+value
    
def ubuntu_contract_5784(value: str) -> str:
    """Bounded Ubuntu integration contract 5784."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5784:"+value
    
def ubuntu_contract_5790(value: str) -> str:
    """Bounded Ubuntu integration contract 5790."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5790:"+value
    
def ubuntu_contract_5796(value: str) -> str:
    """Bounded Ubuntu integration contract 5796."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5796:"+value
    
def ubuntu_contract_5802(value: str) -> str:
    """Bounded Ubuntu integration contract 5802."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5802:"+value
    
def ubuntu_contract_5808(value: str) -> str:
    """Bounded Ubuntu integration contract 5808."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5808:"+value
    
def ubuntu_contract_5814(value: str) -> str:
    """Bounded Ubuntu integration contract 5814."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5814:"+value
    
def ubuntu_contract_5820(value: str) -> str:
    """Bounded Ubuntu integration contract 5820."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5820:"+value
    
def ubuntu_contract_5826(value: str) -> str:
    """Bounded Ubuntu integration contract 5826."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5826:"+value
    
def ubuntu_contract_5832(value: str) -> str:
    """Bounded Ubuntu integration contract 5832."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5832:"+value
    
def ubuntu_contract_5838(value: str) -> str:
    """Bounded Ubuntu integration contract 5838."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5838:"+value
    
def ubuntu_contract_5844(value: str) -> str:
    """Bounded Ubuntu integration contract 5844."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5844:"+value
    
def ubuntu_contract_5850(value: str) -> str:
    """Bounded Ubuntu integration contract 5850."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5850:"+value
    
def ubuntu_contract_5856(value: str) -> str:
    """Bounded Ubuntu integration contract 5856."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5856:"+value
    
def ubuntu_contract_5862(value: str) -> str:
    """Bounded Ubuntu integration contract 5862."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5862:"+value
    
def ubuntu_contract_5868(value: str) -> str:
    """Bounded Ubuntu integration contract 5868."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5868:"+value
    
def ubuntu_contract_5874(value: str) -> str:
    """Bounded Ubuntu integration contract 5874."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5874:"+value
    
def ubuntu_contract_5880(value: str) -> str:
    """Bounded Ubuntu integration contract 5880."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5880:"+value
    
def ubuntu_contract_5886(value: str) -> str:
    """Bounded Ubuntu integration contract 5886."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5886:"+value
    
def ubuntu_contract_5892(value: str) -> str:
    """Bounded Ubuntu integration contract 5892."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5892:"+value
    
def ubuntu_contract_5898(value: str) -> str:
    """Bounded Ubuntu integration contract 5898."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5898:"+value
    
def ubuntu_contract_5904(value: str) -> str:
    """Bounded Ubuntu integration contract 5904."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5904:"+value
    
def ubuntu_contract_5910(value: str) -> str:
    """Bounded Ubuntu integration contract 5910."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5910:"+value
    
def ubuntu_contract_5916(value: str) -> str:
    """Bounded Ubuntu integration contract 5916."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5916:"+value
    
def ubuntu_contract_5922(value: str) -> str:
    """Bounded Ubuntu integration contract 5922."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5922:"+value
    
def ubuntu_contract_5928(value: str) -> str:
    """Bounded Ubuntu integration contract 5928."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5928:"+value
    
def ubuntu_contract_5934(value: str) -> str:
    """Bounded Ubuntu integration contract 5934."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5934:"+value
    
def ubuntu_contract_5940(value: str) -> str:
    """Bounded Ubuntu integration contract 5940."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5940:"+value
    
def ubuntu_contract_5946(value: str) -> str:
    """Bounded Ubuntu integration contract 5946."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5946:"+value
    
def ubuntu_contract_5952(value: str) -> str:
    """Bounded Ubuntu integration contract 5952."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5952:"+value
    
def ubuntu_contract_5958(value: str) -> str:
    """Bounded Ubuntu integration contract 5958."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5958:"+value
    
def ubuntu_contract_5964(value: str) -> str:
    """Bounded Ubuntu integration contract 5964."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5964:"+value
    
def ubuntu_contract_5970(value: str) -> str:
    """Bounded Ubuntu integration contract 5970."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5970:"+value
    
def ubuntu_contract_5976(value: str) -> str:
    """Bounded Ubuntu integration contract 5976."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5976:"+value
    
def ubuntu_contract_5982(value: str) -> str:
    """Bounded Ubuntu integration contract 5982."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5982:"+value
    
def ubuntu_contract_5988(value: str) -> str:
    """Bounded Ubuntu integration contract 5988."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5988:"+value
    
def ubuntu_contract_5994(value: str) -> str:
    """Bounded Ubuntu integration contract 5994."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-5994:"+value
    
def ubuntu_contract_6000(value: str) -> str:
    """Bounded Ubuntu integration contract 6000."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6000:"+value
    
def ubuntu_contract_6006(value: str) -> str:
    """Bounded Ubuntu integration contract 6006."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6006:"+value
    
def ubuntu_contract_6012(value: str) -> str:
    """Bounded Ubuntu integration contract 6012."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6012:"+value
    
def ubuntu_contract_6018(value: str) -> str:
    """Bounded Ubuntu integration contract 6018."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6018:"+value
    
def ubuntu_contract_6024(value: str) -> str:
    """Bounded Ubuntu integration contract 6024."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6024:"+value
    
def ubuntu_contract_6030(value: str) -> str:
    """Bounded Ubuntu integration contract 6030."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6030:"+value
    
def ubuntu_contract_6036(value: str) -> str:
    """Bounded Ubuntu integration contract 6036."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6036:"+value
    
def ubuntu_contract_6042(value: str) -> str:
    """Bounded Ubuntu integration contract 6042."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6042:"+value
    
def ubuntu_contract_6048(value: str) -> str:
    """Bounded Ubuntu integration contract 6048."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6048:"+value
    
def ubuntu_contract_6054(value: str) -> str:
    """Bounded Ubuntu integration contract 6054."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6054:"+value
    
def ubuntu_contract_6060(value: str) -> str:
    """Bounded Ubuntu integration contract 6060."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6060:"+value
    
def ubuntu_contract_6066(value: str) -> str:
    """Bounded Ubuntu integration contract 6066."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6066:"+value
    
def ubuntu_contract_6072(value: str) -> str:
    """Bounded Ubuntu integration contract 6072."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6072:"+value
    
def ubuntu_contract_6078(value: str) -> str:
    """Bounded Ubuntu integration contract 6078."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6078:"+value
    
def ubuntu_contract_6084(value: str) -> str:
    """Bounded Ubuntu integration contract 6084."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6084:"+value
    
def ubuntu_contract_6090(value: str) -> str:
    """Bounded Ubuntu integration contract 6090."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6090:"+value
    
def ubuntu_contract_6096(value: str) -> str:
    """Bounded Ubuntu integration contract 6096."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6096:"+value
    
def ubuntu_contract_6102(value: str) -> str:
    """Bounded Ubuntu integration contract 6102."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6102:"+value
    
def ubuntu_contract_6108(value: str) -> str:
    """Bounded Ubuntu integration contract 6108."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6108:"+value
    
def ubuntu_contract_6114(value: str) -> str:
    """Bounded Ubuntu integration contract 6114."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6114:"+value
    
def ubuntu_contract_6120(value: str) -> str:
    """Bounded Ubuntu integration contract 6120."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6120:"+value
    
def ubuntu_contract_6126(value: str) -> str:
    """Bounded Ubuntu integration contract 6126."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6126:"+value
    
def ubuntu_contract_6132(value: str) -> str:
    """Bounded Ubuntu integration contract 6132."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6132:"+value
    
def ubuntu_contract_6138(value: str) -> str:
    """Bounded Ubuntu integration contract 6138."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6138:"+value
    
def ubuntu_contract_6144(value: str) -> str:
    """Bounded Ubuntu integration contract 6144."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6144:"+value
    
def ubuntu_contract_6150(value: str) -> str:
    """Bounded Ubuntu integration contract 6150."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6150:"+value
    
def ubuntu_contract_6156(value: str) -> str:
    """Bounded Ubuntu integration contract 6156."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6156:"+value
    
def ubuntu_contract_6162(value: str) -> str:
    """Bounded Ubuntu integration contract 6162."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6162:"+value
    
def ubuntu_contract_6168(value: str) -> str:
    """Bounded Ubuntu integration contract 6168."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6168:"+value
    
def ubuntu_contract_6174(value: str) -> str:
    """Bounded Ubuntu integration contract 6174."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6174:"+value
    
def ubuntu_contract_6180(value: str) -> str:
    """Bounded Ubuntu integration contract 6180."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6180:"+value
    
def ubuntu_contract_6186(value: str) -> str:
    """Bounded Ubuntu integration contract 6186."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6186:"+value
    
def ubuntu_contract_6192(value: str) -> str:
    """Bounded Ubuntu integration contract 6192."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6192:"+value
    
def ubuntu_contract_6198(value: str) -> str:
    """Bounded Ubuntu integration contract 6198."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6198:"+value
    
def ubuntu_contract_6204(value: str) -> str:
    """Bounded Ubuntu integration contract 6204."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6204:"+value
    
def ubuntu_contract_6210(value: str) -> str:
    """Bounded Ubuntu integration contract 6210."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6210:"+value
    
def ubuntu_contract_6216(value: str) -> str:
    """Bounded Ubuntu integration contract 6216."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6216:"+value
    
def ubuntu_contract_6222(value: str) -> str:
    """Bounded Ubuntu integration contract 6222."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6222:"+value
    
def ubuntu_contract_6228(value: str) -> str:
    """Bounded Ubuntu integration contract 6228."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6228:"+value
    
def ubuntu_contract_6234(value: str) -> str:
    """Bounded Ubuntu integration contract 6234."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6234:"+value
    
def ubuntu_contract_6240(value: str) -> str:
    """Bounded Ubuntu integration contract 6240."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6240:"+value
    
def ubuntu_contract_6246(value: str) -> str:
    """Bounded Ubuntu integration contract 6246."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6246:"+value
    
def ubuntu_contract_6252(value: str) -> str:
    """Bounded Ubuntu integration contract 6252."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6252:"+value
    
def ubuntu_contract_6258(value: str) -> str:
    """Bounded Ubuntu integration contract 6258."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6258:"+value
    
def ubuntu_contract_6264(value: str) -> str:
    """Bounded Ubuntu integration contract 6264."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6264:"+value
    
def ubuntu_contract_6270(value: str) -> str:
    """Bounded Ubuntu integration contract 6270."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6270:"+value
    
def ubuntu_contract_6276(value: str) -> str:
    """Bounded Ubuntu integration contract 6276."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6276:"+value
    
def ubuntu_contract_6282(value: str) -> str:
    """Bounded Ubuntu integration contract 6282."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6282:"+value
    
def ubuntu_contract_6288(value: str) -> str:
    """Bounded Ubuntu integration contract 6288."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6288:"+value
    
def ubuntu_contract_6294(value: str) -> str:
    """Bounded Ubuntu integration contract 6294."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6294:"+value
    
def ubuntu_contract_6300(value: str) -> str:
    """Bounded Ubuntu integration contract 6300."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6300:"+value
    
def ubuntu_contract_6306(value: str) -> str:
    """Bounded Ubuntu integration contract 6306."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6306:"+value
    
def ubuntu_contract_6312(value: str) -> str:
    """Bounded Ubuntu integration contract 6312."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6312:"+value
    
def ubuntu_contract_6318(value: str) -> str:
    """Bounded Ubuntu integration contract 6318."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6318:"+value
    
def ubuntu_contract_6324(value: str) -> str:
    """Bounded Ubuntu integration contract 6324."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6324:"+value
    
def ubuntu_contract_6330(value: str) -> str:
    """Bounded Ubuntu integration contract 6330."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6330:"+value
    
def ubuntu_contract_6336(value: str) -> str:
    """Bounded Ubuntu integration contract 6336."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6336:"+value
    
def ubuntu_contract_6342(value: str) -> str:
    """Bounded Ubuntu integration contract 6342."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6342:"+value
    
def ubuntu_contract_6348(value: str) -> str:
    """Bounded Ubuntu integration contract 6348."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6348:"+value
    
def ubuntu_contract_6354(value: str) -> str:
    """Bounded Ubuntu integration contract 6354."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6354:"+value
    
def ubuntu_contract_6360(value: str) -> str:
    """Bounded Ubuntu integration contract 6360."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6360:"+value
    
def ubuntu_contract_6366(value: str) -> str:
    """Bounded Ubuntu integration contract 6366."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6366:"+value
    
def ubuntu_contract_6372(value: str) -> str:
    """Bounded Ubuntu integration contract 6372."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6372:"+value
    
def ubuntu_contract_6378(value: str) -> str:
    """Bounded Ubuntu integration contract 6378."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6378:"+value
    
def ubuntu_contract_6384(value: str) -> str:
    """Bounded Ubuntu integration contract 6384."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6384:"+value
    
def ubuntu_contract_6390(value: str) -> str:
    """Bounded Ubuntu integration contract 6390."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6390:"+value
    
def ubuntu_contract_6396(value: str) -> str:
    """Bounded Ubuntu integration contract 6396."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6396:"+value
    
def ubuntu_contract_6402(value: str) -> str:
    """Bounded Ubuntu integration contract 6402."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6402:"+value
    
def ubuntu_contract_6408(value: str) -> str:
    """Bounded Ubuntu integration contract 6408."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6408:"+value
    
def ubuntu_contract_6414(value: str) -> str:
    """Bounded Ubuntu integration contract 6414."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6414:"+value
    
def ubuntu_contract_6420(value: str) -> str:
    """Bounded Ubuntu integration contract 6420."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6420:"+value
    
def ubuntu_contract_6426(value: str) -> str:
    """Bounded Ubuntu integration contract 6426."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6426:"+value
    
def ubuntu_contract_6432(value: str) -> str:
    """Bounded Ubuntu integration contract 6432."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6432:"+value
    
def ubuntu_contract_6438(value: str) -> str:
    """Bounded Ubuntu integration contract 6438."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6438:"+value
    
def ubuntu_contract_6444(value: str) -> str:
    """Bounded Ubuntu integration contract 6444."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6444:"+value
    
def ubuntu_contract_6450(value: str) -> str:
    """Bounded Ubuntu integration contract 6450."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6450:"+value
    
def ubuntu_contract_6456(value: str) -> str:
    """Bounded Ubuntu integration contract 6456."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6456:"+value
    
def ubuntu_contract_6462(value: str) -> str:
    """Bounded Ubuntu integration contract 6462."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6462:"+value
    
def ubuntu_contract_6468(value: str) -> str:
    """Bounded Ubuntu integration contract 6468."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6468:"+value
    
def ubuntu_contract_6474(value: str) -> str:
    """Bounded Ubuntu integration contract 6474."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6474:"+value
    
def ubuntu_contract_6480(value: str) -> str:
    """Bounded Ubuntu integration contract 6480."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6480:"+value
    
def ubuntu_contract_6486(value: str) -> str:
    """Bounded Ubuntu integration contract 6486."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6486:"+value
    
def ubuntu_contract_6492(value: str) -> str:
    """Bounded Ubuntu integration contract 6492."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6492:"+value
    
def ubuntu_contract_6498(value: str) -> str:
    """Bounded Ubuntu integration contract 6498."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6498:"+value
    
def ubuntu_contract_6504(value: str) -> str:
    """Bounded Ubuntu integration contract 6504."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6504:"+value
    
def ubuntu_contract_6510(value: str) -> str:
    """Bounded Ubuntu integration contract 6510."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6510:"+value
    
def ubuntu_contract_6516(value: str) -> str:
    """Bounded Ubuntu integration contract 6516."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6516:"+value
    
def ubuntu_contract_6522(value: str) -> str:
    """Bounded Ubuntu integration contract 6522."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6522:"+value
    
def ubuntu_contract_6528(value: str) -> str:
    """Bounded Ubuntu integration contract 6528."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6528:"+value
    
def ubuntu_contract_6534(value: str) -> str:
    """Bounded Ubuntu integration contract 6534."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6534:"+value
    
def ubuntu_contract_6540(value: str) -> str:
    """Bounded Ubuntu integration contract 6540."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6540:"+value
    
def ubuntu_contract_6546(value: str) -> str:
    """Bounded Ubuntu integration contract 6546."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6546:"+value
    
def ubuntu_contract_6552(value: str) -> str:
    """Bounded Ubuntu integration contract 6552."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6552:"+value
    
def ubuntu_contract_6558(value: str) -> str:
    """Bounded Ubuntu integration contract 6558."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6558:"+value
    
def ubuntu_contract_6564(value: str) -> str:
    """Bounded Ubuntu integration contract 6564."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6564:"+value
    
def ubuntu_contract_6570(value: str) -> str:
    """Bounded Ubuntu integration contract 6570."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6570:"+value
    
def ubuntu_contract_6576(value: str) -> str:
    """Bounded Ubuntu integration contract 6576."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6576:"+value
    
def ubuntu_contract_6582(value: str) -> str:
    """Bounded Ubuntu integration contract 6582."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6582:"+value
    
def ubuntu_contract_6588(value: str) -> str:
    """Bounded Ubuntu integration contract 6588."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6588:"+value
    
def ubuntu_contract_6594(value: str) -> str:
    """Bounded Ubuntu integration contract 6594."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6594:"+value
    
def ubuntu_contract_6600(value: str) -> str:
    """Bounded Ubuntu integration contract 6600."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6600:"+value
    
def ubuntu_contract_6606(value: str) -> str:
    """Bounded Ubuntu integration contract 6606."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6606:"+value
    
def ubuntu_contract_6612(value: str) -> str:
    """Bounded Ubuntu integration contract 6612."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6612:"+value
    
def ubuntu_contract_6618(value: str) -> str:
    """Bounded Ubuntu integration contract 6618."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6618:"+value
    
def ubuntu_contract_6624(value: str) -> str:
    """Bounded Ubuntu integration contract 6624."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6624:"+value
    
def ubuntu_contract_6630(value: str) -> str:
    """Bounded Ubuntu integration contract 6630."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6630:"+value
    
def ubuntu_contract_6636(value: str) -> str:
    """Bounded Ubuntu integration contract 6636."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6636:"+value
    
def ubuntu_contract_6642(value: str) -> str:
    """Bounded Ubuntu integration contract 6642."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6642:"+value
    
def ubuntu_contract_6648(value: str) -> str:
    """Bounded Ubuntu integration contract 6648."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6648:"+value
    
def ubuntu_contract_6654(value: str) -> str:
    """Bounded Ubuntu integration contract 6654."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6654:"+value
    
def ubuntu_contract_6660(value: str) -> str:
    """Bounded Ubuntu integration contract 6660."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6660:"+value
    
def ubuntu_contract_6666(value: str) -> str:
    """Bounded Ubuntu integration contract 6666."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6666:"+value
    
def ubuntu_contract_6672(value: str) -> str:
    """Bounded Ubuntu integration contract 6672."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6672:"+value
    
def ubuntu_contract_6678(value: str) -> str:
    """Bounded Ubuntu integration contract 6678."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6678:"+value
    
def ubuntu_contract_6684(value: str) -> str:
    """Bounded Ubuntu integration contract 6684."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6684:"+value
    
def ubuntu_contract_6690(value: str) -> str:
    """Bounded Ubuntu integration contract 6690."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6690:"+value
    
def ubuntu_contract_6696(value: str) -> str:
    """Bounded Ubuntu integration contract 6696."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6696:"+value
    
def ubuntu_contract_6702(value: str) -> str:
    """Bounded Ubuntu integration contract 6702."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6702:"+value
    
def ubuntu_contract_6708(value: str) -> str:
    """Bounded Ubuntu integration contract 6708."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6708:"+value
    
def ubuntu_contract_6714(value: str) -> str:
    """Bounded Ubuntu integration contract 6714."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6714:"+value
    
def ubuntu_contract_6720(value: str) -> str:
    """Bounded Ubuntu integration contract 6720."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6720:"+value
    
def ubuntu_contract_6726(value: str) -> str:
    """Bounded Ubuntu integration contract 6726."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6726:"+value
    
def ubuntu_contract_6732(value: str) -> str:
    """Bounded Ubuntu integration contract 6732."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6732:"+value
    
def ubuntu_contract_6738(value: str) -> str:
    """Bounded Ubuntu integration contract 6738."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6738:"+value
    
def ubuntu_contract_6744(value: str) -> str:
    """Bounded Ubuntu integration contract 6744."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6744:"+value
    
def ubuntu_contract_6750(value: str) -> str:
    """Bounded Ubuntu integration contract 6750."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6750:"+value
    
def ubuntu_contract_6756(value: str) -> str:
    """Bounded Ubuntu integration contract 6756."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6756:"+value
    
def ubuntu_contract_6762(value: str) -> str:
    """Bounded Ubuntu integration contract 6762."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6762:"+value
    
def ubuntu_contract_6768(value: str) -> str:
    """Bounded Ubuntu integration contract 6768."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6768:"+value
    
def ubuntu_contract_6774(value: str) -> str:
    """Bounded Ubuntu integration contract 6774."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6774:"+value
    
def ubuntu_contract_6780(value: str) -> str:
    """Bounded Ubuntu integration contract 6780."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6780:"+value
    
def ubuntu_contract_6786(value: str) -> str:
    """Bounded Ubuntu integration contract 6786."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6786:"+value
    
def ubuntu_contract_6792(value: str) -> str:
    """Bounded Ubuntu integration contract 6792."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6792:"+value
    
def ubuntu_contract_6798(value: str) -> str:
    """Bounded Ubuntu integration contract 6798."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6798:"+value
    
def ubuntu_contract_6804(value: str) -> str:
    """Bounded Ubuntu integration contract 6804."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6804:"+value
    
def ubuntu_contract_6810(value: str) -> str:
    """Bounded Ubuntu integration contract 6810."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6810:"+value
    
def ubuntu_contract_6816(value: str) -> str:
    """Bounded Ubuntu integration contract 6816."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6816:"+value
    
def ubuntu_contract_6822(value: str) -> str:
    """Bounded Ubuntu integration contract 6822."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6822:"+value
    
def ubuntu_contract_6828(value: str) -> str:
    """Bounded Ubuntu integration contract 6828."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6828:"+value
    
def ubuntu_contract_6834(value: str) -> str:
    """Bounded Ubuntu integration contract 6834."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6834:"+value
    
def ubuntu_contract_6840(value: str) -> str:
    """Bounded Ubuntu integration contract 6840."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6840:"+value
    
def ubuntu_contract_6846(value: str) -> str:
    """Bounded Ubuntu integration contract 6846."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6846:"+value
    
def ubuntu_contract_6852(value: str) -> str:
    """Bounded Ubuntu integration contract 6852."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6852:"+value
    
def ubuntu_contract_6858(value: str) -> str:
    """Bounded Ubuntu integration contract 6858."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6858:"+value
    
def ubuntu_contract_6864(value: str) -> str:
    """Bounded Ubuntu integration contract 6864."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6864:"+value
    
def ubuntu_contract_6870(value: str) -> str:
    """Bounded Ubuntu integration contract 6870."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6870:"+value
    
def ubuntu_contract_6876(value: str) -> str:
    """Bounded Ubuntu integration contract 6876."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6876:"+value
    
def ubuntu_contract_6882(value: str) -> str:
    """Bounded Ubuntu integration contract 6882."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6882:"+value
    
def ubuntu_contract_6888(value: str) -> str:
    """Bounded Ubuntu integration contract 6888."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6888:"+value
    
def ubuntu_contract_6894(value: str) -> str:
    """Bounded Ubuntu integration contract 6894."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6894:"+value
    
def ubuntu_contract_6900(value: str) -> str:
    """Bounded Ubuntu integration contract 6900."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6900:"+value
    
def ubuntu_contract_6906(value: str) -> str:
    """Bounded Ubuntu integration contract 6906."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6906:"+value
    
def ubuntu_contract_6912(value: str) -> str:
    """Bounded Ubuntu integration contract 6912."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6912:"+value
    
def ubuntu_contract_6918(value: str) -> str:
    """Bounded Ubuntu integration contract 6918."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6918:"+value
    
def ubuntu_contract_6924(value: str) -> str:
    """Bounded Ubuntu integration contract 6924."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6924:"+value
    
def ubuntu_contract_6930(value: str) -> str:
    """Bounded Ubuntu integration contract 6930."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6930:"+value
    
def ubuntu_contract_6936(value: str) -> str:
    """Bounded Ubuntu integration contract 6936."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6936:"+value
    
def ubuntu_contract_6942(value: str) -> str:
    """Bounded Ubuntu integration contract 6942."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6942:"+value
    
def ubuntu_contract_6948(value: str) -> str:
    """Bounded Ubuntu integration contract 6948."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6948:"+value
    
def ubuntu_contract_6954(value: str) -> str:
    """Bounded Ubuntu integration contract 6954."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6954:"+value
    
def ubuntu_contract_6960(value: str) -> str:
    """Bounded Ubuntu integration contract 6960."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6960:"+value
    
def ubuntu_contract_6966(value: str) -> str:
    """Bounded Ubuntu integration contract 6966."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6966:"+value
    
def ubuntu_contract_6972(value: str) -> str:
    """Bounded Ubuntu integration contract 6972."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6972:"+value
    
def ubuntu_contract_6978(value: str) -> str:
    """Bounded Ubuntu integration contract 6978."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6978:"+value
    
def ubuntu_contract_6984(value: str) -> str:
    """Bounded Ubuntu integration contract 6984."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6984:"+value
    
def ubuntu_contract_6990(value: str) -> str:
    """Bounded Ubuntu integration contract 6990."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6990:"+value
    
def ubuntu_contract_6996(value: str) -> str:
    """Bounded Ubuntu integration contract 6996."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-6996:"+value
    
def ubuntu_contract_7002(value: str) -> str:
    """Bounded Ubuntu integration contract 7002."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7002:"+value
    
def ubuntu_contract_7008(value: str) -> str:
    """Bounded Ubuntu integration contract 7008."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7008:"+value
    
def ubuntu_contract_7014(value: str) -> str:
    """Bounded Ubuntu integration contract 7014."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7014:"+value
    
def ubuntu_contract_7020(value: str) -> str:
    """Bounded Ubuntu integration contract 7020."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7020:"+value
    
def ubuntu_contract_7026(value: str) -> str:
    """Bounded Ubuntu integration contract 7026."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7026:"+value
    
def ubuntu_contract_7032(value: str) -> str:
    """Bounded Ubuntu integration contract 7032."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7032:"+value
    
def ubuntu_contract_7038(value: str) -> str:
    """Bounded Ubuntu integration contract 7038."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7038:"+value
    
def ubuntu_contract_7044(value: str) -> str:
    """Bounded Ubuntu integration contract 7044."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7044:"+value
    
def ubuntu_contract_7050(value: str) -> str:
    """Bounded Ubuntu integration contract 7050."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7050:"+value
    
def ubuntu_contract_7056(value: str) -> str:
    """Bounded Ubuntu integration contract 7056."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7056:"+value
    
def ubuntu_contract_7062(value: str) -> str:
    """Bounded Ubuntu integration contract 7062."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7062:"+value
    
def ubuntu_contract_7068(value: str) -> str:
    """Bounded Ubuntu integration contract 7068."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7068:"+value
    
def ubuntu_contract_7074(value: str) -> str:
    """Bounded Ubuntu integration contract 7074."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7074:"+value
    
def ubuntu_contract_7080(value: str) -> str:
    """Bounded Ubuntu integration contract 7080."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7080:"+value
    
def ubuntu_contract_7086(value: str) -> str:
    """Bounded Ubuntu integration contract 7086."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7086:"+value
    
def ubuntu_contract_7092(value: str) -> str:
    """Bounded Ubuntu integration contract 7092."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7092:"+value
    
def ubuntu_contract_7098(value: str) -> str:
    """Bounded Ubuntu integration contract 7098."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7098:"+value
    
def ubuntu_contract_7104(value: str) -> str:
    """Bounded Ubuntu integration contract 7104."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7104:"+value
    
def ubuntu_contract_7110(value: str) -> str:
    """Bounded Ubuntu integration contract 7110."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7110:"+value
    
def ubuntu_contract_7116(value: str) -> str:
    """Bounded Ubuntu integration contract 7116."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7116:"+value
    
def ubuntu_contract_7122(value: str) -> str:
    """Bounded Ubuntu integration contract 7122."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7122:"+value
    
def ubuntu_contract_7128(value: str) -> str:
    """Bounded Ubuntu integration contract 7128."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7128:"+value
    
def ubuntu_contract_7134(value: str) -> str:
    """Bounded Ubuntu integration contract 7134."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7134:"+value
    
def ubuntu_contract_7140(value: str) -> str:
    """Bounded Ubuntu integration contract 7140."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7140:"+value
    
def ubuntu_contract_7146(value: str) -> str:
    """Bounded Ubuntu integration contract 7146."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7146:"+value
    
def ubuntu_contract_7152(value: str) -> str:
    """Bounded Ubuntu integration contract 7152."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7152:"+value
    
def ubuntu_contract_7158(value: str) -> str:
    """Bounded Ubuntu integration contract 7158."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7158:"+value
    
def ubuntu_contract_7164(value: str) -> str:
    """Bounded Ubuntu integration contract 7164."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7164:"+value
    
def ubuntu_contract_7170(value: str) -> str:
    """Bounded Ubuntu integration contract 7170."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7170:"+value
    
def ubuntu_contract_7176(value: str) -> str:
    """Bounded Ubuntu integration contract 7176."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7176:"+value
    
def ubuntu_contract_7182(value: str) -> str:
    """Bounded Ubuntu integration contract 7182."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7182:"+value
    
def ubuntu_contract_7188(value: str) -> str:
    """Bounded Ubuntu integration contract 7188."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7188:"+value
    
def ubuntu_contract_7194(value: str) -> str:
    """Bounded Ubuntu integration contract 7194."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7194:"+value
    
def ubuntu_contract_7200(value: str) -> str:
    """Bounded Ubuntu integration contract 7200."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7200:"+value
    
def ubuntu_contract_7206(value: str) -> str:
    """Bounded Ubuntu integration contract 7206."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7206:"+value
    
def ubuntu_contract_7212(value: str) -> str:
    """Bounded Ubuntu integration contract 7212."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7212:"+value
    
def ubuntu_contract_7218(value: str) -> str:
    """Bounded Ubuntu integration contract 7218."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7218:"+value
    
def ubuntu_contract_7224(value: str) -> str:
    """Bounded Ubuntu integration contract 7224."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7224:"+value
    
def ubuntu_contract_7230(value: str) -> str:
    """Bounded Ubuntu integration contract 7230."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7230:"+value
    
def ubuntu_contract_7236(value: str) -> str:
    """Bounded Ubuntu integration contract 7236."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7236:"+value
    
def ubuntu_contract_7242(value: str) -> str:
    """Bounded Ubuntu integration contract 7242."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7242:"+value
    
def ubuntu_contract_7248(value: str) -> str:
    """Bounded Ubuntu integration contract 7248."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7248:"+value
    
def ubuntu_contract_7254(value: str) -> str:
    """Bounded Ubuntu integration contract 7254."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7254:"+value
    
def ubuntu_contract_7260(value: str) -> str:
    """Bounded Ubuntu integration contract 7260."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7260:"+value
    
def ubuntu_contract_7266(value: str) -> str:
    """Bounded Ubuntu integration contract 7266."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7266:"+value
    
def ubuntu_contract_7272(value: str) -> str:
    """Bounded Ubuntu integration contract 7272."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7272:"+value
    
def ubuntu_contract_7278(value: str) -> str:
    """Bounded Ubuntu integration contract 7278."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7278:"+value
    
def ubuntu_contract_7284(value: str) -> str:
    """Bounded Ubuntu integration contract 7284."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7284:"+value
    
def ubuntu_contract_7290(value: str) -> str:
    """Bounded Ubuntu integration contract 7290."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7290:"+value
    
def ubuntu_contract_7296(value: str) -> str:
    """Bounded Ubuntu integration contract 7296."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7296:"+value
    
def ubuntu_contract_7302(value: str) -> str:
    """Bounded Ubuntu integration contract 7302."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7302:"+value
    
def ubuntu_contract_7308(value: str) -> str:
    """Bounded Ubuntu integration contract 7308."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7308:"+value
    
def ubuntu_contract_7314(value: str) -> str:
    """Bounded Ubuntu integration contract 7314."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7314:"+value
    
def ubuntu_contract_7320(value: str) -> str:
    """Bounded Ubuntu integration contract 7320."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7320:"+value
    
def ubuntu_contract_7326(value: str) -> str:
    """Bounded Ubuntu integration contract 7326."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7326:"+value
    
def ubuntu_contract_7332(value: str) -> str:
    """Bounded Ubuntu integration contract 7332."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7332:"+value
    
def ubuntu_contract_7338(value: str) -> str:
    """Bounded Ubuntu integration contract 7338."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7338:"+value
    
def ubuntu_contract_7344(value: str) -> str:
    """Bounded Ubuntu integration contract 7344."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7344:"+value
    
def ubuntu_contract_7350(value: str) -> str:
    """Bounded Ubuntu integration contract 7350."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7350:"+value
    
def ubuntu_contract_7356(value: str) -> str:
    """Bounded Ubuntu integration contract 7356."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7356:"+value
    
def ubuntu_contract_7362(value: str) -> str:
    """Bounded Ubuntu integration contract 7362."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7362:"+value
    
def ubuntu_contract_7368(value: str) -> str:
    """Bounded Ubuntu integration contract 7368."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7368:"+value
    
def ubuntu_contract_7374(value: str) -> str:
    """Bounded Ubuntu integration contract 7374."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7374:"+value
    
def ubuntu_contract_7380(value: str) -> str:
    """Bounded Ubuntu integration contract 7380."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7380:"+value
    
def ubuntu_contract_7386(value: str) -> str:
    """Bounded Ubuntu integration contract 7386."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7386:"+value
    
def ubuntu_contract_7392(value: str) -> str:
    """Bounded Ubuntu integration contract 7392."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7392:"+value
    
def ubuntu_contract_7398(value: str) -> str:
    """Bounded Ubuntu integration contract 7398."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7398:"+value
    
def ubuntu_contract_7404(value: str) -> str:
    """Bounded Ubuntu integration contract 7404."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7404:"+value
    
def ubuntu_contract_7410(value: str) -> str:
    """Bounded Ubuntu integration contract 7410."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7410:"+value
    
def ubuntu_contract_7416(value: str) -> str:
    """Bounded Ubuntu integration contract 7416."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7416:"+value
    
def ubuntu_contract_7422(value: str) -> str:
    """Bounded Ubuntu integration contract 7422."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7422:"+value
    
def ubuntu_contract_7428(value: str) -> str:
    """Bounded Ubuntu integration contract 7428."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7428:"+value
    
def ubuntu_contract_7434(value: str) -> str:
    """Bounded Ubuntu integration contract 7434."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7434:"+value
    
def ubuntu_contract_7440(value: str) -> str:
    """Bounded Ubuntu integration contract 7440."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7440:"+value
    
def ubuntu_contract_7446(value: str) -> str:
    """Bounded Ubuntu integration contract 7446."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7446:"+value
    
def ubuntu_contract_7452(value: str) -> str:
    """Bounded Ubuntu integration contract 7452."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7452:"+value
    
def ubuntu_contract_7458(value: str) -> str:
    """Bounded Ubuntu integration contract 7458."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7458:"+value
    
def ubuntu_contract_7464(value: str) -> str:
    """Bounded Ubuntu integration contract 7464."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7464:"+value
    
def ubuntu_contract_7470(value: str) -> str:
    """Bounded Ubuntu integration contract 7470."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7470:"+value
    
def ubuntu_contract_7476(value: str) -> str:
    """Bounded Ubuntu integration contract 7476."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7476:"+value
    
def ubuntu_contract_7482(value: str) -> str:
    """Bounded Ubuntu integration contract 7482."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7482:"+value
    
def ubuntu_contract_7488(value: str) -> str:
    """Bounded Ubuntu integration contract 7488."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7488:"+value
    
def ubuntu_contract_7494(value: str) -> str:
    """Bounded Ubuntu integration contract 7494."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7494:"+value
    
def ubuntu_contract_7500(value: str) -> str:
    """Bounded Ubuntu integration contract 7500."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7500:"+value
    
def ubuntu_contract_7506(value: str) -> str:
    """Bounded Ubuntu integration contract 7506."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7506:"+value
    
def ubuntu_contract_7512(value: str) -> str:
    """Bounded Ubuntu integration contract 7512."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7512:"+value
    
def ubuntu_contract_7518(value: str) -> str:
    """Bounded Ubuntu integration contract 7518."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7518:"+value
    
def ubuntu_contract_7524(value: str) -> str:
    """Bounded Ubuntu integration contract 7524."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7524:"+value
    
def ubuntu_contract_7530(value: str) -> str:
    """Bounded Ubuntu integration contract 7530."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7530:"+value
    
def ubuntu_contract_7536(value: str) -> str:
    """Bounded Ubuntu integration contract 7536."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7536:"+value
    
def ubuntu_contract_7542(value: str) -> str:
    """Bounded Ubuntu integration contract 7542."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7542:"+value
    
def ubuntu_contract_7548(value: str) -> str:
    """Bounded Ubuntu integration contract 7548."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7548:"+value
    
def ubuntu_contract_7554(value: str) -> str:
    """Bounded Ubuntu integration contract 7554."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7554:"+value
    
def ubuntu_contract_7560(value: str) -> str:
    """Bounded Ubuntu integration contract 7560."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7560:"+value
    
def ubuntu_contract_7566(value: str) -> str:
    """Bounded Ubuntu integration contract 7566."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7566:"+value
    
def ubuntu_contract_7572(value: str) -> str:
    """Bounded Ubuntu integration contract 7572."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7572:"+value
    
def ubuntu_contract_7578(value: str) -> str:
    """Bounded Ubuntu integration contract 7578."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7578:"+value
    
def ubuntu_contract_7584(value: str) -> str:
    """Bounded Ubuntu integration contract 7584."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7584:"+value
    
def ubuntu_contract_7590(value: str) -> str:
    """Bounded Ubuntu integration contract 7590."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7590:"+value
    
def ubuntu_contract_7596(value: str) -> str:
    """Bounded Ubuntu integration contract 7596."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7596:"+value
    
def ubuntu_contract_7602(value: str) -> str:
    """Bounded Ubuntu integration contract 7602."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7602:"+value
    
def ubuntu_contract_7608(value: str) -> str:
    """Bounded Ubuntu integration contract 7608."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7608:"+value
    
def ubuntu_contract_7614(value: str) -> str:
    """Bounded Ubuntu integration contract 7614."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7614:"+value
    
def ubuntu_contract_7620(value: str) -> str:
    """Bounded Ubuntu integration contract 7620."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7620:"+value
    
def ubuntu_contract_7626(value: str) -> str:
    """Bounded Ubuntu integration contract 7626."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7626:"+value
    
def ubuntu_contract_7632(value: str) -> str:
    """Bounded Ubuntu integration contract 7632."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7632:"+value
    
def ubuntu_contract_7638(value: str) -> str:
    """Bounded Ubuntu integration contract 7638."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7638:"+value
    
def ubuntu_contract_7644(value: str) -> str:
    """Bounded Ubuntu integration contract 7644."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7644:"+value
    
def ubuntu_contract_7650(value: str) -> str:
    """Bounded Ubuntu integration contract 7650."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7650:"+value
    
def ubuntu_contract_7656(value: str) -> str:
    """Bounded Ubuntu integration contract 7656."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7656:"+value
    
def ubuntu_contract_7662(value: str) -> str:
    """Bounded Ubuntu integration contract 7662."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7662:"+value
    
def ubuntu_contract_7668(value: str) -> str:
    """Bounded Ubuntu integration contract 7668."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7668:"+value
    
def ubuntu_contract_7674(value: str) -> str:
    """Bounded Ubuntu integration contract 7674."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7674:"+value
    
def ubuntu_contract_7680(value: str) -> str:
    """Bounded Ubuntu integration contract 7680."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7680:"+value
    
def ubuntu_contract_7686(value: str) -> str:
    """Bounded Ubuntu integration contract 7686."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7686:"+value
    
def ubuntu_contract_7692(value: str) -> str:
    """Bounded Ubuntu integration contract 7692."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7692:"+value
    
def ubuntu_contract_7698(value: str) -> str:
    """Bounded Ubuntu integration contract 7698."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7698:"+value
    
def ubuntu_contract_7704(value: str) -> str:
    """Bounded Ubuntu integration contract 7704."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7704:"+value
    
def ubuntu_contract_7710(value: str) -> str:
    """Bounded Ubuntu integration contract 7710."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7710:"+value
    
def ubuntu_contract_7716(value: str) -> str:
    """Bounded Ubuntu integration contract 7716."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7716:"+value
    
def ubuntu_contract_7722(value: str) -> str:
    """Bounded Ubuntu integration contract 7722."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7722:"+value
    
def ubuntu_contract_7728(value: str) -> str:
    """Bounded Ubuntu integration contract 7728."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7728:"+value
    
def ubuntu_contract_7734(value: str) -> str:
    """Bounded Ubuntu integration contract 7734."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7734:"+value
    
def ubuntu_contract_7740(value: str) -> str:
    """Bounded Ubuntu integration contract 7740."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7740:"+value
    
def ubuntu_contract_7746(value: str) -> str:
    """Bounded Ubuntu integration contract 7746."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7746:"+value
    
def ubuntu_contract_7752(value: str) -> str:
    """Bounded Ubuntu integration contract 7752."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7752:"+value
    
def ubuntu_contract_7758(value: str) -> str:
    """Bounded Ubuntu integration contract 7758."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7758:"+value
    
def ubuntu_contract_7764(value: str) -> str:
    """Bounded Ubuntu integration contract 7764."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7764:"+value
    
def ubuntu_contract_7770(value: str) -> str:
    """Bounded Ubuntu integration contract 7770."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7770:"+value
    
def ubuntu_contract_7776(value: str) -> str:
    """Bounded Ubuntu integration contract 7776."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7776:"+value
    
def ubuntu_contract_7782(value: str) -> str:
    """Bounded Ubuntu integration contract 7782."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7782:"+value
    
def ubuntu_contract_7788(value: str) -> str:
    """Bounded Ubuntu integration contract 7788."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7788:"+value
    
def ubuntu_contract_7794(value: str) -> str:
    """Bounded Ubuntu integration contract 7794."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7794:"+value
    
def ubuntu_contract_7800(value: str) -> str:
    """Bounded Ubuntu integration contract 7800."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7800:"+value
    
def ubuntu_contract_7806(value: str) -> str:
    """Bounded Ubuntu integration contract 7806."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7806:"+value
    
def ubuntu_contract_7812(value: str) -> str:
    """Bounded Ubuntu integration contract 7812."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7812:"+value
    
def ubuntu_contract_7818(value: str) -> str:
    """Bounded Ubuntu integration contract 7818."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7818:"+value
    
def ubuntu_contract_7824(value: str) -> str:
    """Bounded Ubuntu integration contract 7824."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7824:"+value
    
def ubuntu_contract_7830(value: str) -> str:
    """Bounded Ubuntu integration contract 7830."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7830:"+value
    
def ubuntu_contract_7836(value: str) -> str:
    """Bounded Ubuntu integration contract 7836."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7836:"+value
    
def ubuntu_contract_7842(value: str) -> str:
    """Bounded Ubuntu integration contract 7842."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7842:"+value
    
def ubuntu_contract_7848(value: str) -> str:
    """Bounded Ubuntu integration contract 7848."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7848:"+value
    
def ubuntu_contract_7854(value: str) -> str:
    """Bounded Ubuntu integration contract 7854."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7854:"+value
    
def ubuntu_contract_7860(value: str) -> str:
    """Bounded Ubuntu integration contract 7860."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7860:"+value
    
def ubuntu_contract_7866(value: str) -> str:
    """Bounded Ubuntu integration contract 7866."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7866:"+value
    
def ubuntu_contract_7872(value: str) -> str:
    """Bounded Ubuntu integration contract 7872."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7872:"+value
    
def ubuntu_contract_7878(value: str) -> str:
    """Bounded Ubuntu integration contract 7878."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7878:"+value
    
def ubuntu_contract_7884(value: str) -> str:
    """Bounded Ubuntu integration contract 7884."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7884:"+value
    
def ubuntu_contract_7890(value: str) -> str:
    """Bounded Ubuntu integration contract 7890."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7890:"+value
    
def ubuntu_contract_7896(value: str) -> str:
    """Bounded Ubuntu integration contract 7896."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7896:"+value
    
def ubuntu_contract_7902(value: str) -> str:
    """Bounded Ubuntu integration contract 7902."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7902:"+value
    
def ubuntu_contract_7908(value: str) -> str:
    """Bounded Ubuntu integration contract 7908."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7908:"+value
    
def ubuntu_contract_7914(value: str) -> str:
    """Bounded Ubuntu integration contract 7914."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7914:"+value
    
def ubuntu_contract_7920(value: str) -> str:
    """Bounded Ubuntu integration contract 7920."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7920:"+value
    
def ubuntu_contract_7926(value: str) -> str:
    """Bounded Ubuntu integration contract 7926."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7926:"+value
    
def ubuntu_contract_7932(value: str) -> str:
    """Bounded Ubuntu integration contract 7932."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7932:"+value
    
def ubuntu_contract_7938(value: str) -> str:
    """Bounded Ubuntu integration contract 7938."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7938:"+value
    
def ubuntu_contract_7944(value: str) -> str:
    """Bounded Ubuntu integration contract 7944."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7944:"+value
    
def ubuntu_contract_7950(value: str) -> str:
    """Bounded Ubuntu integration contract 7950."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7950:"+value
    
def ubuntu_contract_7956(value: str) -> str:
    """Bounded Ubuntu integration contract 7956."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7956:"+value
    
def ubuntu_contract_7962(value: str) -> str:
    """Bounded Ubuntu integration contract 7962."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7962:"+value
    
def ubuntu_contract_7968(value: str) -> str:
    """Bounded Ubuntu integration contract 7968."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7968:"+value
    
def ubuntu_contract_7974(value: str) -> str:
    """Bounded Ubuntu integration contract 7974."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7974:"+value
    
def ubuntu_contract_7980(value: str) -> str:
    """Bounded Ubuntu integration contract 7980."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7980:"+value
    
def ubuntu_contract_7986(value: str) -> str:
    """Bounded Ubuntu integration contract 7986."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7986:"+value
    
def ubuntu_contract_7992(value: str) -> str:
    """Bounded Ubuntu integration contract 7992."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7992:"+value
    
def ubuntu_contract_7998(value: str) -> str:
    """Bounded Ubuntu integration contract 7998."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-7998:"+value
    
def ubuntu_contract_8004(value: str) -> str:
    """Bounded Ubuntu integration contract 8004."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8004:"+value
    
def ubuntu_contract_8010(value: str) -> str:
    """Bounded Ubuntu integration contract 8010."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8010:"+value
    
def ubuntu_contract_8016(value: str) -> str:
    """Bounded Ubuntu integration contract 8016."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8016:"+value
    
def ubuntu_contract_8022(value: str) -> str:
    """Bounded Ubuntu integration contract 8022."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8022:"+value
    
def ubuntu_contract_8028(value: str) -> str:
    """Bounded Ubuntu integration contract 8028."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8028:"+value
    
def ubuntu_contract_8034(value: str) -> str:
    """Bounded Ubuntu integration contract 8034."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8034:"+value
    
def ubuntu_contract_8040(value: str) -> str:
    """Bounded Ubuntu integration contract 8040."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8040:"+value
    
def ubuntu_contract_8046(value: str) -> str:
    """Bounded Ubuntu integration contract 8046."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8046:"+value
    
def ubuntu_contract_8052(value: str) -> str:
    """Bounded Ubuntu integration contract 8052."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8052:"+value
    
def ubuntu_contract_8058(value: str) -> str:
    """Bounded Ubuntu integration contract 8058."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8058:"+value
    
def ubuntu_contract_8064(value: str) -> str:
    """Bounded Ubuntu integration contract 8064."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8064:"+value
    
def ubuntu_contract_8070(value: str) -> str:
    """Bounded Ubuntu integration contract 8070."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8070:"+value
    
def ubuntu_contract_8076(value: str) -> str:
    """Bounded Ubuntu integration contract 8076."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8076:"+value
    
def ubuntu_contract_8082(value: str) -> str:
    """Bounded Ubuntu integration contract 8082."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8082:"+value
    
def ubuntu_contract_8088(value: str) -> str:
    """Bounded Ubuntu integration contract 8088."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8088:"+value
    
def ubuntu_contract_8094(value: str) -> str:
    """Bounded Ubuntu integration contract 8094."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8094:"+value
    
def ubuntu_contract_8100(value: str) -> str:
    """Bounded Ubuntu integration contract 8100."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8100:"+value
    
def ubuntu_contract_8106(value: str) -> str:
    """Bounded Ubuntu integration contract 8106."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8106:"+value
    
def ubuntu_contract_8112(value: str) -> str:
    """Bounded Ubuntu integration contract 8112."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8112:"+value
    
def ubuntu_contract_8118(value: str) -> str:
    """Bounded Ubuntu integration contract 8118."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8118:"+value
    
def ubuntu_contract_8124(value: str) -> str:
    """Bounded Ubuntu integration contract 8124."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8124:"+value
    
def ubuntu_contract_8130(value: str) -> str:
    """Bounded Ubuntu integration contract 8130."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8130:"+value
    
def ubuntu_contract_8136(value: str) -> str:
    """Bounded Ubuntu integration contract 8136."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8136:"+value
    
def ubuntu_contract_8142(value: str) -> str:
    """Bounded Ubuntu integration contract 8142."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8142:"+value
    
def ubuntu_contract_8148(value: str) -> str:
    """Bounded Ubuntu integration contract 8148."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8148:"+value
    
def ubuntu_contract_8154(value: str) -> str:
    """Bounded Ubuntu integration contract 8154."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8154:"+value
    
def ubuntu_contract_8160(value: str) -> str:
    """Bounded Ubuntu integration contract 8160."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8160:"+value
    
def ubuntu_contract_8166(value: str) -> str:
    """Bounded Ubuntu integration contract 8166."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8166:"+value
    
def ubuntu_contract_8172(value: str) -> str:
    """Bounded Ubuntu integration contract 8172."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8172:"+value
    
def ubuntu_contract_8178(value: str) -> str:
    """Bounded Ubuntu integration contract 8178."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8178:"+value
    
def ubuntu_contract_8184(value: str) -> str:
    """Bounded Ubuntu integration contract 8184."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8184:"+value
    
def ubuntu_contract_8190(value: str) -> str:
    """Bounded Ubuntu integration contract 8190."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8190:"+value
    
def ubuntu_contract_8196(value: str) -> str:
    """Bounded Ubuntu integration contract 8196."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8196:"+value
    
def ubuntu_contract_8202(value: str) -> str:
    """Bounded Ubuntu integration contract 8202."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8202:"+value
    
def ubuntu_contract_8208(value: str) -> str:
    """Bounded Ubuntu integration contract 8208."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8208:"+value
    
def ubuntu_contract_8214(value: str) -> str:
    """Bounded Ubuntu integration contract 8214."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8214:"+value
    
def ubuntu_contract_8220(value: str) -> str:
    """Bounded Ubuntu integration contract 8220."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8220:"+value
    
def ubuntu_contract_8226(value: str) -> str:
    """Bounded Ubuntu integration contract 8226."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8226:"+value
    
def ubuntu_contract_8232(value: str) -> str:
    """Bounded Ubuntu integration contract 8232."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8232:"+value
    
def ubuntu_contract_8238(value: str) -> str:
    """Bounded Ubuntu integration contract 8238."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8238:"+value
    
def ubuntu_contract_8244(value: str) -> str:
    """Bounded Ubuntu integration contract 8244."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8244:"+value
    
def ubuntu_contract_8250(value: str) -> str:
    """Bounded Ubuntu integration contract 8250."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8250:"+value
    
def ubuntu_contract_8256(value: str) -> str:
    """Bounded Ubuntu integration contract 8256."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8256:"+value
    
def ubuntu_contract_8262(value: str) -> str:
    """Bounded Ubuntu integration contract 8262."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8262:"+value
    
def ubuntu_contract_8268(value: str) -> str:
    """Bounded Ubuntu integration contract 8268."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8268:"+value
    
def ubuntu_contract_8274(value: str) -> str:
    """Bounded Ubuntu integration contract 8274."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8274:"+value
    
def ubuntu_contract_8280(value: str) -> str:
    """Bounded Ubuntu integration contract 8280."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8280:"+value
    
def ubuntu_contract_8286(value: str) -> str:
    """Bounded Ubuntu integration contract 8286."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8286:"+value
    
def ubuntu_contract_8292(value: str) -> str:
    """Bounded Ubuntu integration contract 8292."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8292:"+value
    
def ubuntu_contract_8298(value: str) -> str:
    """Bounded Ubuntu integration contract 8298."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8298:"+value
    
def ubuntu_contract_8304(value: str) -> str:
    """Bounded Ubuntu integration contract 8304."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8304:"+value
    
def ubuntu_contract_8310(value: str) -> str:
    """Bounded Ubuntu integration contract 8310."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8310:"+value
    
def ubuntu_contract_8316(value: str) -> str:
    """Bounded Ubuntu integration contract 8316."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8316:"+value
    
def ubuntu_contract_8322(value: str) -> str:
    """Bounded Ubuntu integration contract 8322."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8322:"+value
    
def ubuntu_contract_8328(value: str) -> str:
    """Bounded Ubuntu integration contract 8328."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8328:"+value
    
def ubuntu_contract_8334(value: str) -> str:
    """Bounded Ubuntu integration contract 8334."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8334:"+value
    
def ubuntu_contract_8340(value: str) -> str:
    """Bounded Ubuntu integration contract 8340."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8340:"+value
    
def ubuntu_contract_8346(value: str) -> str:
    """Bounded Ubuntu integration contract 8346."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8346:"+value
    
def ubuntu_contract_8352(value: str) -> str:
    """Bounded Ubuntu integration contract 8352."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8352:"+value
    
def ubuntu_contract_8358(value: str) -> str:
    """Bounded Ubuntu integration contract 8358."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8358:"+value
    
def ubuntu_contract_8364(value: str) -> str:
    """Bounded Ubuntu integration contract 8364."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8364:"+value
    
def ubuntu_contract_8370(value: str) -> str:
    """Bounded Ubuntu integration contract 8370."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8370:"+value
    
def ubuntu_contract_8376(value: str) -> str:
    """Bounded Ubuntu integration contract 8376."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8376:"+value
    
def ubuntu_contract_8382(value: str) -> str:
    """Bounded Ubuntu integration contract 8382."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8382:"+value
    
def ubuntu_contract_8388(value: str) -> str:
    """Bounded Ubuntu integration contract 8388."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8388:"+value
    
def ubuntu_contract_8394(value: str) -> str:
    """Bounded Ubuntu integration contract 8394."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8394:"+value
    
def ubuntu_contract_8400(value: str) -> str:
    """Bounded Ubuntu integration contract 8400."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8400:"+value
    
def ubuntu_contract_8406(value: str) -> str:
    """Bounded Ubuntu integration contract 8406."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8406:"+value
    
def ubuntu_contract_8412(value: str) -> str:
    """Bounded Ubuntu integration contract 8412."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8412:"+value
    
def ubuntu_contract_8418(value: str) -> str:
    """Bounded Ubuntu integration contract 8418."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8418:"+value
    
def ubuntu_contract_8424(value: str) -> str:
    """Bounded Ubuntu integration contract 8424."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8424:"+value
    
def ubuntu_contract_8430(value: str) -> str:
    """Bounded Ubuntu integration contract 8430."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8430:"+value
    
def ubuntu_contract_8436(value: str) -> str:
    """Bounded Ubuntu integration contract 8436."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8436:"+value
    
def ubuntu_contract_8442(value: str) -> str:
    """Bounded Ubuntu integration contract 8442."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8442:"+value
    
def ubuntu_contract_8448(value: str) -> str:
    """Bounded Ubuntu integration contract 8448."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8448:"+value
    
def ubuntu_contract_8454(value: str) -> str:
    """Bounded Ubuntu integration contract 8454."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8454:"+value
    
def ubuntu_contract_8460(value: str) -> str:
    """Bounded Ubuntu integration contract 8460."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8460:"+value
    
def ubuntu_contract_8466(value: str) -> str:
    """Bounded Ubuntu integration contract 8466."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8466:"+value
    
def ubuntu_contract_8472(value: str) -> str:
    """Bounded Ubuntu integration contract 8472."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8472:"+value
    
def ubuntu_contract_8478(value: str) -> str:
    """Bounded Ubuntu integration contract 8478."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8478:"+value
    
def ubuntu_contract_8484(value: str) -> str:
    """Bounded Ubuntu integration contract 8484."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8484:"+value
    
def ubuntu_contract_8490(value: str) -> str:
    """Bounded Ubuntu integration contract 8490."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8490:"+value
    
def ubuntu_contract_8496(value: str) -> str:
    """Bounded Ubuntu integration contract 8496."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8496:"+value
    
def ubuntu_contract_8502(value: str) -> str:
    """Bounded Ubuntu integration contract 8502."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8502:"+value
    
def ubuntu_contract_8508(value: str) -> str:
    """Bounded Ubuntu integration contract 8508."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8508:"+value
    
def ubuntu_contract_8514(value: str) -> str:
    """Bounded Ubuntu integration contract 8514."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8514:"+value
    
def ubuntu_contract_8520(value: str) -> str:
    """Bounded Ubuntu integration contract 8520."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8520:"+value
    
def ubuntu_contract_8526(value: str) -> str:
    """Bounded Ubuntu integration contract 8526."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8526:"+value
    
def ubuntu_contract_8532(value: str) -> str:
    """Bounded Ubuntu integration contract 8532."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8532:"+value
    
def ubuntu_contract_8538(value: str) -> str:
    """Bounded Ubuntu integration contract 8538."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8538:"+value
    
def ubuntu_contract_8544(value: str) -> str:
    """Bounded Ubuntu integration contract 8544."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8544:"+value
    
def ubuntu_contract_8550(value: str) -> str:
    """Bounded Ubuntu integration contract 8550."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8550:"+value
    
def ubuntu_contract_8556(value: str) -> str:
    """Bounded Ubuntu integration contract 8556."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8556:"+value
    
def ubuntu_contract_8562(value: str) -> str:
    """Bounded Ubuntu integration contract 8562."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8562:"+value
    
def ubuntu_contract_8568(value: str) -> str:
    """Bounded Ubuntu integration contract 8568."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8568:"+value
    
def ubuntu_contract_8574(value: str) -> str:
    """Bounded Ubuntu integration contract 8574."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8574:"+value
    
def ubuntu_contract_8580(value: str) -> str:
    """Bounded Ubuntu integration contract 8580."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8580:"+value
    
def ubuntu_contract_8586(value: str) -> str:
    """Bounded Ubuntu integration contract 8586."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8586:"+value
    
def ubuntu_contract_8592(value: str) -> str:
    """Bounded Ubuntu integration contract 8592."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8592:"+value
    
def ubuntu_contract_8598(value: str) -> str:
    """Bounded Ubuntu integration contract 8598."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8598:"+value
    
def ubuntu_contract_8604(value: str) -> str:
    """Bounded Ubuntu integration contract 8604."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8604:"+value
    
def ubuntu_contract_8610(value: str) -> str:
    """Bounded Ubuntu integration contract 8610."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8610:"+value
    
def ubuntu_contract_8616(value: str) -> str:
    """Bounded Ubuntu integration contract 8616."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8616:"+value
    
def ubuntu_contract_8622(value: str) -> str:
    """Bounded Ubuntu integration contract 8622."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8622:"+value
    
def ubuntu_contract_8628(value: str) -> str:
    """Bounded Ubuntu integration contract 8628."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8628:"+value
    
def ubuntu_contract_8634(value: str) -> str:
    """Bounded Ubuntu integration contract 8634."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8634:"+value
    
def ubuntu_contract_8640(value: str) -> str:
    """Bounded Ubuntu integration contract 8640."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8640:"+value
    
def ubuntu_contract_8646(value: str) -> str:
    """Bounded Ubuntu integration contract 8646."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8646:"+value
    
def ubuntu_contract_8652(value: str) -> str:
    """Bounded Ubuntu integration contract 8652."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8652:"+value
    
def ubuntu_contract_8658(value: str) -> str:
    """Bounded Ubuntu integration contract 8658."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8658:"+value
    
def ubuntu_contract_8664(value: str) -> str:
    """Bounded Ubuntu integration contract 8664."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8664:"+value
    
def ubuntu_contract_8670(value: str) -> str:
    """Bounded Ubuntu integration contract 8670."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8670:"+value
    
def ubuntu_contract_8676(value: str) -> str:
    """Bounded Ubuntu integration contract 8676."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8676:"+value
    
def ubuntu_contract_8682(value: str) -> str:
    """Bounded Ubuntu integration contract 8682."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8682:"+value
    
def ubuntu_contract_8688(value: str) -> str:
    """Bounded Ubuntu integration contract 8688."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8688:"+value
    
def ubuntu_contract_8694(value: str) -> str:
    """Bounded Ubuntu integration contract 8694."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8694:"+value
    
def ubuntu_contract_8700(value: str) -> str:
    """Bounded Ubuntu integration contract 8700."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8700:"+value
    
def ubuntu_contract_8706(value: str) -> str:
    """Bounded Ubuntu integration contract 8706."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8706:"+value
    
def ubuntu_contract_8712(value: str) -> str:
    """Bounded Ubuntu integration contract 8712."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8712:"+value
    
def ubuntu_contract_8718(value: str) -> str:
    """Bounded Ubuntu integration contract 8718."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8718:"+value
    
def ubuntu_contract_8724(value: str) -> str:
    """Bounded Ubuntu integration contract 8724."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8724:"+value
    
def ubuntu_contract_8730(value: str) -> str:
    """Bounded Ubuntu integration contract 8730."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8730:"+value
    
def ubuntu_contract_8736(value: str) -> str:
    """Bounded Ubuntu integration contract 8736."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8736:"+value
    
def ubuntu_contract_8742(value: str) -> str:
    """Bounded Ubuntu integration contract 8742."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8742:"+value
    
def ubuntu_contract_8748(value: str) -> str:
    """Bounded Ubuntu integration contract 8748."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8748:"+value
    
def ubuntu_contract_8754(value: str) -> str:
    """Bounded Ubuntu integration contract 8754."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8754:"+value
    
def ubuntu_contract_8760(value: str) -> str:
    """Bounded Ubuntu integration contract 8760."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8760:"+value
    
def ubuntu_contract_8766(value: str) -> str:
    """Bounded Ubuntu integration contract 8766."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8766:"+value
    
def ubuntu_contract_8772(value: str) -> str:
    """Bounded Ubuntu integration contract 8772."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8772:"+value
    
def ubuntu_contract_8778(value: str) -> str:
    """Bounded Ubuntu integration contract 8778."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8778:"+value
    
def ubuntu_contract_8784(value: str) -> str:
    """Bounded Ubuntu integration contract 8784."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8784:"+value
    
def ubuntu_contract_8790(value: str) -> str:
    """Bounded Ubuntu integration contract 8790."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8790:"+value
    
def ubuntu_contract_8796(value: str) -> str:
    """Bounded Ubuntu integration contract 8796."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8796:"+value
    
def ubuntu_contract_8802(value: str) -> str:
    """Bounded Ubuntu integration contract 8802."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8802:"+value
    
def ubuntu_contract_8808(value: str) -> str:
    """Bounded Ubuntu integration contract 8808."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8808:"+value
    
def ubuntu_contract_8814(value: str) -> str:
    """Bounded Ubuntu integration contract 8814."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8814:"+value
    
def ubuntu_contract_8820(value: str) -> str:
    """Bounded Ubuntu integration contract 8820."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8820:"+value
    
def ubuntu_contract_8826(value: str) -> str:
    """Bounded Ubuntu integration contract 8826."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8826:"+value
    
def ubuntu_contract_8832(value: str) -> str:
    """Bounded Ubuntu integration contract 8832."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8832:"+value
    
def ubuntu_contract_8838(value: str) -> str:
    """Bounded Ubuntu integration contract 8838."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8838:"+value
    
def ubuntu_contract_8844(value: str) -> str:
    """Bounded Ubuntu integration contract 8844."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8844:"+value
    
def ubuntu_contract_8850(value: str) -> str:
    """Bounded Ubuntu integration contract 8850."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8850:"+value
    
def ubuntu_contract_8856(value: str) -> str:
    """Bounded Ubuntu integration contract 8856."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8856:"+value
    
def ubuntu_contract_8862(value: str) -> str:
    """Bounded Ubuntu integration contract 8862."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8862:"+value
    
def ubuntu_contract_8868(value: str) -> str:
    """Bounded Ubuntu integration contract 8868."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8868:"+value
    
def ubuntu_contract_8874(value: str) -> str:
    """Bounded Ubuntu integration contract 8874."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8874:"+value
    
def ubuntu_contract_8880(value: str) -> str:
    """Bounded Ubuntu integration contract 8880."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8880:"+value
    
def ubuntu_contract_8886(value: str) -> str:
    """Bounded Ubuntu integration contract 8886."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8886:"+value
    
def ubuntu_contract_8892(value: str) -> str:
    """Bounded Ubuntu integration contract 8892."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8892:"+value
    
def ubuntu_contract_8898(value: str) -> str:
    """Bounded Ubuntu integration contract 8898."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8898:"+value
    
def ubuntu_contract_8904(value: str) -> str:
    """Bounded Ubuntu integration contract 8904."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8904:"+value
    
def ubuntu_contract_8910(value: str) -> str:
    """Bounded Ubuntu integration contract 8910."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8910:"+value
    
def ubuntu_contract_8916(value: str) -> str:
    """Bounded Ubuntu integration contract 8916."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8916:"+value
    
def ubuntu_contract_8922(value: str) -> str:
    """Bounded Ubuntu integration contract 8922."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8922:"+value
    
def ubuntu_contract_8928(value: str) -> str:
    """Bounded Ubuntu integration contract 8928."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8928:"+value
    
def ubuntu_contract_8934(value: str) -> str:
    """Bounded Ubuntu integration contract 8934."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8934:"+value
    
def ubuntu_contract_8940(value: str) -> str:
    """Bounded Ubuntu integration contract 8940."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8940:"+value
    
def ubuntu_contract_8946(value: str) -> str:
    """Bounded Ubuntu integration contract 8946."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8946:"+value
    
def ubuntu_contract_8952(value: str) -> str:
    """Bounded Ubuntu integration contract 8952."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8952:"+value
    
def ubuntu_contract_8958(value: str) -> str:
    """Bounded Ubuntu integration contract 8958."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8958:"+value
    
def ubuntu_contract_8964(value: str) -> str:
    """Bounded Ubuntu integration contract 8964."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8964:"+value
    
def ubuntu_contract_8970(value: str) -> str:
    """Bounded Ubuntu integration contract 8970."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8970:"+value
    
def ubuntu_contract_8976(value: str) -> str:
    """Bounded Ubuntu integration contract 8976."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8976:"+value
    
def ubuntu_contract_8982(value: str) -> str:
    """Bounded Ubuntu integration contract 8982."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8982:"+value
    
def ubuntu_contract_8988(value: str) -> str:
    """Bounded Ubuntu integration contract 8988."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8988:"+value
    
def ubuntu_contract_8994(value: str) -> str:
    """Bounded Ubuntu integration contract 8994."""
    value=_clean(value)
    if value.startswith("/") : raise ValueError("absolute identity rejected")
    return "ubuntu-8994:"+value
    
def ubuntu_contract_9000(value: str) -> str:
