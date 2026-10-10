"""Hardware-aware Dragon admission using the canonical product scheduler.

Telemetry is an adapter input, not a platform-name inference. Execution workers
must honor checkpoint requests before release of reserved resources. No model,
thread, network call or OS background task is started here.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from threading import RLock
from uuid import uuid4

from skeleton.ai.product.resource_scheduler import ResourceRequest, schedule_resources
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourceScheduler, ResourceRequest as GlobalRequest, ResourceVector, ResourcePolicyError,
)


def _integer(value: int, minimum: int, maximum: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True, slots=True)
class HardwareSample:
    available_memory_bytes: int
    cpu_units: int
    pressure: float
    battery_fraction: float
    charging: bool
    thermal_limited: bool
    sampled_at: float

    def __post_init__(self) -> None:
        _integer(self.available_memory_bytes, 0, 2**50, "memory")
        _integer(self.cpu_units, 1, 1024, "cpu")
        for value in (self.pressure, self.battery_fraction):
            if isinstance(value, bool) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError("invalid hardware fraction")
        if not isinstance(self.charging, bool) or not isinstance(self.thermal_limited, bool):
            raise ValueError("invalid hardware flag")
        if isinstance(self.sampled_at, bool) or not isfinite(self.sampled_at):
            raise ValueError("invalid hardware timestamp")


@dataclass(frozen=True, slots=True)
class ResourcePlan:
    foreground: bool
    memory_bytes: int
    cpu_units: int
    chunk_bytes: int
    context_bytes: int
    retrieval_candidates: int
    effort: str
    background_allowed: bool
    reason: str


def plan_resources(sample: HardwareSample, *, now: float, foreground: bool) -> ResourcePlan:
    if not isinstance(foreground, bool) or isinstance(now, bool) or not isfinite(now):
        raise ValueError("invalid resource request")
    age = now - sample.sampled_at
    if age < 0 or age > 5:
        return ResourcePlan(foreground, 0, 0, 1024, 0, 0, "defer", False, "stale_telemetry")
    if sample.thermal_limited or sample.pressure >= .95:
        return ResourcePlan(foreground, 0, 0, 1024, 0, 0, "defer", False, "thermal_or_pressure")
    # Reserve at least half the currently available memory for the app/OS.
    # Device generation/year never grants compute authority.
    memory = min(512 * 1024**2, sample.available_memory_bytes // (2 if foreground else 8))
    if memory < 8 * 1024**2:
        return ResourcePlan(foreground, 0, 0, 1024, 0, 0, "defer", False, "memory_reserve")
    low_battery = sample.battery_fraction < .2 and not sample.charging
    background = not foreground and sample.pressure < .5 and not low_battery
    if not foreground and not background:
        return ResourcePlan(False, 0, 0, 1024, 0, 0, "defer", False, "background_guard")
    cpu = max(1, min(4, sample.cpu_units // (2 if foreground else 4)))
    effort = "high" if foreground and sample.pressure < .25 and memory >= 128 * 1024**2 else "low"
    context = min(64 * 1024, memory // 1024)
    return ResourcePlan(foreground, memory, cpu, min(4096, context), context,
                        min(256, max(8, context // 256)), effort, background, "admitted")


# User activity (penta) always wins. The requested background order follows.
PRIORITIES = {"user": 500, "autonomous": 400, "idle": 300,
              "training": 200, "acquisition": 100, "distillation": 100}


@dataclass(frozen=True, slots=True)
class SessionTask:
    task_id: str
    lane: str
    memory_bytes: int
    cpu_units: int
    checkpointable: bool = True
    gpu_millis: int = 0
    io_tokens: int = 0
    provider_tokens: int = 0

    def request(self) -> ResourceRequest:
        if self.lane not in PRIORITIES or not isinstance(self.checkpointable, bool):
            raise ValueError("unsupported workload lane")
        for name in ("gpu_millis", "io_tokens", "provider_tokens"):
            _integer(getattr(self, name), 0, 10**12, name)
        return ResourceRequest(self.task_id, self.cpu_units, self.memory_bytes,
                               PRIORITIES[self.lane], self.lane == "user", self.checkpointable)


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    admitted: tuple[str, ...]
    checkpoint_requested: tuple[str, ...]
    foreground_ready: bool
    effort: str
    reason: str
    execution_authorized: bool = False


class DragonResourceSession:
    """Small session admission adapter; outstanding workers keep reservations.

    Checkpoint acknowledgement means the worker has stopped/released memory.
    A cancellation request alone NEVER makes space available for a model.
    """
    def __init__(self, *, global_resources: GlobalResourceScheduler | None = None,
                 tenant: str = "", interactive_plane: str = "interactive",
                 background_plane: str = "background") -> None:
        if global_resources is not None:
            if not isinstance(global_resources, GlobalResourceScheduler) or not tenant or len(tenant) > 128:
                raise ValueError("global resource admission requires scheduler and tenant")
            global_resources.policy.plane(interactive_plane)
            global_resources.policy.plane(background_plane)
        self._global = global_resources
        self._tenant = tenant
        self._interactive_plane, self._background_plane = interactive_plane, background_plane
        self._namespace = uuid4().hex
        self._attempt = 0
        self._grants: dict[str, str] = {}
        self._active: dict[str, SessionTask] = {}
        self._yielding: set[str] = set()
        self._lock = RLock()

    def dispatch(self, tasks: tuple[SessionTask, ...], sample: HardwareSample,
                 *, now: float) -> DispatchDecision:
        if len(tasks) > 64 or len({t.task_id for t in tasks}) != len(tasks):
            raise ValueError("task budget or duplicate task")
        requests = tuple(t.request() for t in tasks)
        with self._lock:
            if any(t.task_id in self._active for t in tasks):
                raise ValueError("task already running")
            foreground = any(t.lane == "user" for t in tasks)
            plan = plan_resources(sample, now=now, foreground=foreground)
            if foreground:
                self._yielding.update(k for k, t in self._active.items()
                                      if t.lane != "user" and t.checkpointable)
            memory = sum(t.memory_bytes for t in self._active.values())
            cpu = sum(t.cpu_units for t in self._active.values())
            admitted = schedule_resources(requests, max(0, plan.cpu_units - cpu),
                                           max(0, plan.memory_bytes - memory))
            if foreground and any(t.lane != "user" for t in self._active.values()):
                admitted = ()
            # Once foreground appears, don't begin any more background work.
            admitted = tuple(r for r in admitted if not foreground or r.foreground)
            if foreground and len(admitted) != sum(t.lane == "user" for t in tasks):
                # A foreground batch is atomic: partial admission would leave
                # a retry blocked by its own unstarted task reservations.
                admitted = ()
            selected = {r.task_id for r in admitted}
            busy_before = bool(self._active)
            globally_admitted = bool(admitted) and self._global is not None
            if self._global is not None and admitted:
                self._attempt += 1
                tickets = []; grants = []
                try:
                    for task in tasks:
                        if task.task_id not in selected:
                            continue
                        request_id = f"dragon:{self._namespace}:{self._attempt}:{task.task_id}"
                        self._global.submit(GlobalRequest(request_id,
                            self._interactive_plane if task.lane == "user" else self._background_plane,
                            self._tenant, ResourceVector(cpu_millis=task.cpu_units * 1000,
                                memory_mb=(task.memory_bytes + 1024**2 - 1) // 1024**2,
                                gpu_millis=task.gpu_millis, io_tokens=task.io_tokens,
                                provider_tokens=task.provider_tokens),
                            # Global scheduler uses LOWER numeric priority;
                            # product scheduler uses higher. Translate explicitly.
                            0 if task.lane == "user" else 7 - PRIORITIES[task.lane] // 100,
                            task.checkpointable))
                        tickets.append(request_id)
                        grant = self._global.admit_request(request_id)
                        if grant is None:
                            globally_admitted = False
                            break
                        grants.append((task.task_id, grant.grant_id))
                    if not globally_admitted:
                        for _, grant_id in grants:
                            self._global.release(grant_id)
                        for request_id in tickets[len(grants):]:
                            self._global.cancel(request_id)
                        admitted = (); selected = set()
                    else:
                        self._grants.update(grants)
                except Exception as exc:
                    for _, grant_id in grants:
                        self._global.release(grant_id)
                    for request_id in tickets[len(grants):]:
                        self._global.cancel(request_id)
                    if isinstance(exc, ResourcePolicyError):
                        admitted = (); selected = set(); globally_admitted = False
                    else:
                        raise
            self._active.update((t.task_id, t) for t in tasks if t.task_id in selected)
            ready = foreground and all(t.task_id in selected for t in tasks if t.lane == "user")
            return DispatchDecision(tuple(r.task_id for r in admitted), tuple(sorted(self._yielding)),
                                    ready, ("low" if busy_before else plan.effort) if ready else "defer",
                                    "draining_background" if foreground and not ready and any(t.lane != "user" for t in self._active.values()) else
                                    "global_capacity" if self._global is not None and not admitted and plan.memory_bytes else plan.reason,
                                    globally_admitted)

    def stopped(self, task_id: str) -> None:
        with self._lock:
            if task_id not in self._active:
                raise ValueError("unknown active task")
            if task_id in self._grants:
                # Only an actual worker-stop acknowledgement releases the
                # global grant, including grants revoked by another plane.
                grant_id = self._grants[task_id]
                grant = next(g for g in self._global.active_grants() if g.grant_id == grant_id)
                if grant.state == "revoking":
                    self._global.ack_preempted(grant_id)
                else:
                    self._global.release(grant_id)
                del self._grants[task_id]
            del self._active[task_id]
            self._yielding.discard(task_id)
