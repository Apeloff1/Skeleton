"""Declarative Ubuntu runtime resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

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

__all__ = [
    "RuntimePythonPlan",
    "RuntimeDockerPlan",
    "RuntimeContainerdPlan",
    "RuntimePodmanPlan",
    "RuntimeBuildxPlan",
    "RuntimeQemuPlan",
    "RuntimeGccPlan",
    "RuntimeNodePlan",
    "RuntimeUvPlan",
    "RuntimePipPlan",
    "validate_runtime_python",
    "plan_runtime_python",
    "audit_runtime_python",
    "validate_runtime_docker",
    "plan_runtime_docker",
    "audit_runtime_docker",
    "validate_runtime_containerd",
    "plan_runtime_containerd",
    "audit_runtime_containerd",
    "validate_runtime_podman",
    "plan_runtime_podman",
    "audit_runtime_podman",
    "validate_runtime_buildx",
    "plan_runtime_buildx",
    "audit_runtime_buildx",
    "validate_runtime_qemu",
    "plan_runtime_qemu",
    "audit_runtime_qemu",
    "validate_runtime_gcc",
    "plan_runtime_gcc",
    "audit_runtime_gcc",
    "validate_runtime_node",
    "plan_runtime_node",
    "audit_runtime_node",
    "validate_runtime_uv",
    "plan_runtime_uv",
    "audit_runtime_uv",
    "validate_runtime_pip",
    "plan_runtime_pip",
    "audit_runtime_pip",
]
