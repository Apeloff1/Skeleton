from __future__ import annotations
from dataclasses import dataclass, field
from time import time
from typing import Dict


@dataclass
class TenantQuota:
    max_agents: int = 20
    max_workspaces: int = 10
    submits_per_minute: int = 60
    submits_per_day: int = 2000
    max_concurrent_work: int = 10
    model_units_per_day: int = 100_000


class _WindowCounter:
    def __init__(self):
        self.events: list[float] = []

    def add(self, ts: float | None = None):
        self.events.append(ts or time())

    def count_since(self, seconds: float) -> int:
        cutoff = time() - seconds
        self.events = [t for t in self.events if t >= cutoff]
        return len(self.events)


class QuotaService:
    def __init__(self):
        self.quotas: Dict[str, TenantQuota] = {}
        self._minute: Dict[str, _WindowCounter] = {}
        self._day: Dict[str, _WindowCounter] = {}
        self._model_day: Dict[str, float] = {}
        self._concurrent: Dict[str, int] = {}

    def get(self, tenant_id: str) -> TenantQuota:
        return self.quotas.setdefault(tenant_id, TenantQuota())

    def set_quota(self, tenant_id: str, quota: TenantQuota):
        self.quotas[tenant_id] = quota

    def check_and_consume_submit(self, tenant_id: str) -> tuple[bool, str]:
        q = self.get(tenant_id)
        minute = self._minute.setdefault(tenant_id, _WindowCounter())
        day = self._day.setdefault(tenant_id, _WindowCounter())
        if minute.count_since(60) >= q.submits_per_minute:
            return False, "submits_per_minute exceeded"
        if day.count_since(86400) >= q.submits_per_day:
            return False, "submits_per_day exceeded"
        if self._concurrent.get(tenant_id, 0) >= q.max_concurrent_work:
            return False, "max_concurrent_work exceeded"
        minute.add()
        day.add()
        self._concurrent[tenant_id] = self._concurrent.get(tenant_id, 0) + 1
        return True, "ok"

    def release_concurrent(self, tenant_id: str):
        self._concurrent[tenant_id] = max(0, self._concurrent.get(tenant_id, 0) - 1)

    def consume_model_units(self, tenant_id: str, units: float) -> tuple[bool, str]:
        q = self.get(tenant_id)
        used = self._model_day.get(tenant_id, 0.0) + units
        if used > q.model_units_per_day:
            return False, "model_units_per_day exceeded"
        self._model_day[tenant_id] = used
        return True, "ok"

    def snapshot(self, tenant_id: str) -> dict:
        q = self.get(tenant_id)
        return {
            "quota": q.__dict__,
            "submits_last_minute": self._minute.get(tenant_id, _WindowCounter()).count_since(60),
            "submits_last_day": self._day.get(tenant_id, _WindowCounter()).count_since(86400),
            "concurrent": self._concurrent.get(tenant_id, 0),
            "model_units_day": self._model_day.get(tenant_id, 0.0),
        }


QUOTAS = QuotaService()
