"""Bounded, locally owned inference worker placement and admission; no implicit remote execution."""
from .workers import Worker,WorkerRegistry
from .placement import PlacementRequest,PlacementDecision,place
from .queues import TenantFairQueue
from .fence import WorkerFences
from .batch import BatchPlanner
__all__=['Worker','WorkerRegistry','PlacementRequest','PlacementDecision','place','TenantFairQueue','WorkerFences','BatchPlanner']
