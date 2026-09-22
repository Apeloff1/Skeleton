"""Declarative Ubuntu security resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

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

__all__ = [
    "SecurityApparmorPlan",
    "SecurityAuditPlan",
    "SecurityPermissionsPlan",
    "SecurityLimitsPlan",
    "SecuritySysctlPlan",
    "SecuritySshPlan",
    "SecuritySudoPlan",
    "SecuritySecretsPlan",
    "SecurityCertPlan",
    "SecurityKernelPlan",
    "validate_security_apparmor",
    "plan_security_apparmor",
    "audit_security_apparmor",
    "validate_security_audit",
    "plan_security_audit",
    "audit_security_audit",
    "validate_security_permissions",
    "plan_security_permissions",
    "audit_security_permissions",
    "validate_security_limits",
    "plan_security_limits",
    "audit_security_limits",
    "validate_security_sysctl",
    "plan_security_sysctl",
    "audit_security_sysctl",
    "validate_security_ssh",
    "plan_security_ssh",
    "audit_security_ssh",
    "validate_security_sudo",
    "plan_security_sudo",
    "audit_security_sudo",
    "validate_security_secrets",
    "plan_security_secrets",
    "audit_security_secrets",
    "validate_security_cert",
    "plan_security_cert",
    "audit_security_cert",
    "validate_security_kernel",
    "plan_security_kernel",
    "audit_security_kernel",
]
