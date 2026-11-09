"""Routing table from logical work classes to worker requirements."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Mapping

from skeleton.shells.worker_affinity import AffinityTerm,JobRequirements
from skeleton.shells.worker_identity import WorkerRole


@dataclass(frozen=True)
class WorkerRoute:
    work_class:str
    requirements:JobRequirements
    principal_prefix:str=""
    enabled:bool=True

    def __post_init__(self)->None:
        if not self.work_class or len(self.work_class)>128:
            raise ValueError("invalid work_class")
        if len(self.principal_prefix)>128:
            raise ValueError("principal_prefix too long")


class WorkerRoutes:
    def __init__(self,*,max_routes:int=1000)->None:
        self.max_routes=max_routes
        self._routes:dict[str,WorkerRoute]={}
        self._lock=threading.RLock()

    def set(self,route:WorkerRoute)->None:
        with self._lock:
            if route.work_class not in self._routes and len(self._routes)>=self.max_routes:
                raise RuntimeError("worker route capacity exhausted")
            self._routes[route.work_class]=route

    def remove(self,work_class:str)->bool:
        with self._lock:return self._routes.pop(work_class,None) is not None

    def resolve(self,work_class:str,*,principal:str="")->JobRequirements:
        with self._lock:
            route=self._routes.get(work_class)
            if route is None:raise KeyError(work_class)
            if not route.enabled:raise RuntimeError("worker route is disabled")
            if route.principal_prefix and not principal.startswith(route.principal_prefix):
                raise RuntimeError("principal is outside worker route scope")
            return route.requirements

    def snapshot(self)->tuple[WorkerRoute,...]:
        with self._lock:return tuple(sorted(self._routes.values(),key=lambda x:x.work_class))

    @classmethod
    def defaults(cls)->"WorkerRoutes":
        routes=cls()
        routes.set(WorkerRoute("build",JobRequirements(required_role=WorkerRole.BUILDER)))
        routes.set(WorkerRoute("test",JobRequirements(required_role=WorkerRole.TESTER)))
        routes.set(WorkerRoute("analysis",JobRequirements(required_role=WorkerRole.ANALYZER)))
        routes.set(WorkerRoute("maintenance",JobRequirements(required_role=WorkerRole.MAINTENANCE)))
        return routes
