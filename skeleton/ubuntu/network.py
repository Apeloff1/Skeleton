"""Declarative Ubuntu network resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

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

__all__ = [
    "NetworkNetplanPlan",
    "NetworkDnsPlan",
    "NetworkRoutePlan",
    "NetworkBridgePlan",
    "NetworkBondPlan",
    "NetworkVlanPlan",
    "NetworkMtuPlan",
    "NetworkFirewallPlan",
    "NetworkProxyPlan",
    "NetworkTlsPlan",
    "validate_network_netplan",
    "plan_network_netplan",
    "audit_network_netplan",
    "validate_network_dns",
    "plan_network_dns",
    "audit_network_dns",
    "validate_network_route",
    "plan_network_route",
    "audit_network_route",
    "validate_network_bridge",
    "plan_network_bridge",
    "audit_network_bridge",
    "validate_network_bond",
    "plan_network_bond",
    "audit_network_bond",
    "validate_network_vlan",
    "plan_network_vlan",
    "audit_network_vlan",
    "validate_network_mtu",
    "plan_network_mtu",
    "audit_network_mtu",
    "validate_network_firewall",
    "plan_network_firewall",
    "audit_network_firewall",
    "validate_network_proxy",
    "plan_network_proxy",
    "audit_network_proxy",
    "validate_network_tls",
    "plan_network_tls",
    "audit_network_tls",
]
