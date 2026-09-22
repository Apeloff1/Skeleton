"""Declarative Ubuntu storage resource policies.

This module contains data-only planning primitives. It never executes host
commands; execution authority remains outside the Ubuntu planning package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import UbuntuAction, UbuntuPlan, _clean, validate_plan

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

__all__ = [
    "StorageMountPlan",
    "StorageFstabPlan",
    "StorageDiskPlan",
    "StoragePartitionPlan",
    "StorageLvmPlan",
    "StorageZfsPlan",
    "StorageRaidPlan",
    "StorageQuotaPlan",
    "StorageTmpfsPlan",
    "StorageBackupPlan",
    "validate_storage_mount",
    "plan_storage_mount",
    "audit_storage_mount",
    "validate_storage_fstab",
    "plan_storage_fstab",
    "audit_storage_fstab",
    "validate_storage_disk",
    "plan_storage_disk",
    "audit_storage_disk",
    "validate_storage_partition",
    "plan_storage_partition",
    "audit_storage_partition",
    "validate_storage_lvm",
    "plan_storage_lvm",
    "audit_storage_lvm",
    "validate_storage_zfs",
    "plan_storage_zfs",
    "audit_storage_zfs",
    "validate_storage_raid",
    "plan_storage_raid",
    "audit_storage_raid",
    "validate_storage_quota",
    "plan_storage_quota",
    "audit_storage_quota",
    "validate_storage_tmpfs",
    "plan_storage_tmpfs",
    "audit_storage_tmpfs",
    "validate_storage_backup",
    "plan_storage_backup",
    "audit_storage_backup",
]
