"""Declarative Ubuntu ci resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

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

__all__ = [
    "CiRunnerPlan",
    "CiCachePlan",
    "CiArtifactPlan",
    "CiWorkspacePlan",
    "CiCheckoutPlan",
    "CiToolchainPlan",
    "CiTestPlan",
    "CiLintPlan",
    "CiCoveragePlan",
    "CiPublishPlan",
    "validate_ci_runner",
    "plan_ci_runner",
    "audit_ci_runner",
    "validate_ci_cache",
    "plan_ci_cache",
    "audit_ci_cache",
    "validate_ci_artifact",
    "plan_ci_artifact",
    "audit_ci_artifact",
    "validate_ci_workspace",
    "plan_ci_workspace",
    "audit_ci_workspace",
    "validate_ci_checkout",
    "plan_ci_checkout",
    "audit_ci_checkout",
    "validate_ci_toolchain",
    "plan_ci_toolchain",
    "audit_ci_toolchain",
    "validate_ci_test",
    "plan_ci_test",
    "audit_ci_test",
    "validate_ci_lint",
    "plan_ci_lint",
    "audit_ci_lint",
    "validate_ci_coverage",
    "plan_ci_coverage",
    "audit_ci_coverage",
    "validate_ci_publish",
    "plan_ci_publish",
    "audit_ci_publish",
]
