"""Retained Dragon executors on one injected canonical physical resource ledger.

This process-local adapter never constructs a global scheduler. Governors are
retained, not evicted/reset between requests. Durable practice quotas continue
to belong to the canonical practice database across application restarts.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
from threading import RLock
from uuid import uuid4
import time

from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope, ResourceGovernor
from .dragon_chunk_executor import DragonChunkExecutor
from .dragon_resource_session import DragonResourceSession
from .dragon_live_hardware import DragonLiveHardware
from .dragon_microknowledge import _id


class DragonPoolCapacityError(RuntimeError):
    pass


class DragonExecutionPool:
    def __init__(self, shared_resources: GlobalResourceScheduler, envelope: ResourceEnvelope,
                 *, capacity: int = 128, max_foreground: int = 64,
                 hardware=None, clock=time.time):
        if not isinstance(shared_resources, GlobalResourceScheduler) or not isinstance(envelope, ResourceEnvelope):
            raise ValueError("existing shared resource ledger and envelope required")
        for value in (capacity, max_foreground):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1024:
                raise ValueError("bounded pool capacity required")
        self.shared_resources, self.envelope = shared_resources, envelope
        self.capacity, self.max_foreground = capacity, max_foreground
        self.hardware = hardware or DragonLiveHardware().sample
        self.clock = clock
        self._workers = {}
        self._foreground = set()
        self._lock = RLock()

    @staticmethod
    def owner_key(tenant: str, principal: str) -> str:
        for value in (tenant, principal):
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200 or any(ord(c) < 32 for c in value):
                raise ValueError("invalid authenticated principal")
        return sha256((tenant.strip() + "\x00" + principal.strip().lower()).encode()).hexdigest()

    def executor(self, owner: str) -> DragonChunkExecutor:
        _id(owner)
        with self._lock:
            if owner in self._workers:
                return self._workers[owner]
            if len(self._workers) >= self.capacity:
                raise DragonPoolCapacityError("retained Dragon owner capacity exhausted")
            worker = DragonChunkExecutor(
                DragonResourceSession(global_resources=self.shared_resources, tenant=owner),
                ResourceGovernor(self.envelope), self.hardware, clock=self.clock)
            # A new owner cannot slip background work past another user's request.
            for _ in self._foreground:
                worker.foreground_arrived()
            self._workers[owner] = worker
            return worker

    @contextmanager
    def foreground(self, owner: str):
        _id(owner)
        with self._lock:
            if len(self._foreground) >= self.max_foreground:
                raise DragonPoolCapacityError("Dragon foreground capacity exhausted")
            token = uuid4().hex
            self._foreground.add(token)
            for worker in self._workers.values():
                worker.foreground_arrived()
        try:
            yield token
        finally:
            with self._lock:
                self._foreground.remove(token)
                for worker in self._workers.values():
                    worker.foreground_finished()

    def status(self) -> dict:
        with self._lock:
            return {"owners": len(self._workers), "capacity": self.capacity,
                    "foreground_requests": len(self._foreground),
                    "provider_tokens": sum(w.governor.tokens for w in self._workers.values()),
                    "artifact_bytes": sum(w.governor.artifact_bytes for w in self._workers.values()),
                    "accounting": "process_lifetime_plus_canonical_durable_practice_quotas"}
