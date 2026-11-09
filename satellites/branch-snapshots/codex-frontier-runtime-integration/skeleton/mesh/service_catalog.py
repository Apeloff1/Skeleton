"""Service catalog — ownership, tiering, and metadata for all services.

The single source of truth for what services exist, who owns them,
what tier they run at, their on-call channel, docs links, and runtime
dependencies. Powers ownership lookup in incidents and compliance
reports for undocumented services.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


TIERS = {"tier0": "revenue-critical", "tier1": "user-facing", "tier2": "internal", "tier3": "experimental"}


@dataclass
class ServiceEntry:
    name: str
    owner: str
    tier: str = "tier2"
    oncall: str = ""
    repo: str = ""
    docs: str = ""
    runbook_id: str = ""
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    registered_ns: int = 0

    def documented(self) -> bool:
        return bool(self.docs or self.runbook_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "owner": self.owner,
            "tier": self.tier,
            "oncall": self.oncall,
            "repo": self.repo,
            "docs": self.docs,
            "runbook_id": self.runbook_id,
            "dependencies": self.dependencies,
            "tags": self.tags,
            "documented": self.documented(),
        }


class ServiceCatalog:
    """Ownership and metadata registry for all services."""

    def __init__(self):
        self._services: Dict[str, ServiceEntry] = {}

    def register(self, name: str, owner: str, tier: str = "tier2", **kwargs: Any) -> ServiceEntry:
        entry = ServiceEntry(name=name, owner=owner, tier=tier if tier in TIERS else "tier2",
                             registered_ns=time.time_ns(), **kwargs)
        self._services[name] = entry
        return entry

    def get(self, name: str) -> Optional[ServiceEntry]:
        return self._services.get(name)

    def update(self, name: str, **fields: Any) -> bool:
        entry = self._services.get(name)
        if not entry:
            return False
        for k, v in fields.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        return True

    def deregister(self, name: str) -> bool:
        return self._services.pop(name, None) is not None

    def by_owner(self, owner: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._services.values() if s.owner == owner]

    def by_tier(self, tier: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._services.values() if s.tier == tier]

    def oncall_for(self, name: str) -> Optional[str]:
        entry = self._services.get(name)
        return entry.oncall if entry else None

    def undocumented(self) -> List[str]:
        return sorted(s.name for s in self._services.values() if not s.documented())

    def orphan_dependencies(self) -> Dict[str, List[str]]:
        orphans: Dict[str, List[str]] = {}
        for s in self._services.values():
            missing = [d for d in s.dependencies if d not in self._services]
            if missing:
                orphans[s.name] = missing
        return orphans

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "service-catalog-card",
            "services": len(self._services),
            "by_tier": {t: len(self.by_tier(t)) for t in TIERS},
            "undocumented": self.undocumented(),
            "orphan_dependencies": self.orphan_dependencies(),
        }
