"""Deterministic tick scheduler for the live world.

Ordering and parallel-safety planning are delegated to the existing
:class:`~.schedule.SystemGraph` (phases, ``after``/``before`` edges and
read/write conflict batching) so there is exactly one planner in the ECS
package.  This module adds what a game loop needs on top:

* **Access declarations** in one namespace: plain names are components,
  ``res:<name>`` are resources, ``event:<channel>`` are event channels.  With
  ``strict_access`` the :class:`SystemContext` rejects any undeclared touch
  (:class:`~.errors.AccessViolationError`), which is what makes the planner's
  "these systems may run concurrently" batches trustworthy.
* **Sync points**: each system records structural changes into its own
  :class:`~.deferred.CommandQueue`; queues are applied after every batch in
  plan order, so the outcome never depends on intra-batch ordering.
* **Change detection**: ``world.change_tick`` is bumped before each system
  run and each sync point, and each system's previous-run tick is kept in
  ``world.meta`` — so it is snapshotted with the world and a restored world
  resumes with identical ``added=``/``changed=`` semantics.
* **Run criteria**: ``every=N``/``offset=`` cadence and ``run_if`` predicates.
* **Per-system RNG streams** derived from ``(world rng, system, tick)`` so a
  system's draws never depend on which other systems ran.
* **Atomic ticks** (optional): snapshot before, restore on any failure.
* :class:`FixedStepRunner`: integer-nanosecond accumulator turning variable
  frame times into a deterministic number of fixed ticks, with a substep
  clamp against the "spiral of death".
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .canonical import digest
from .deferred import ApplyReceipt, CommandQueue
from .errors import AccessViolationError, ScheduleError, ValidationError
from .live import LiveWorld
from .rng import DeterministicRng
from .schedule import ExecutionPlan, SystemGraph, SystemPhase, SystemSpec

SystemFn = Callable[["SystemContext"], Any]
RunCondition = Callable[[LiveWorld], bool]
LAST_RUN_META = "scheduler.last_run"
WORLD_TOKEN = "*world*"
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
MAX_SUBSTEPS = 64


def _tokens(value: Iterable[str] | str, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    out = tuple(value)
    for item in out:
        if not isinstance(item, str) or not item:
            raise ValidationError(f"{label} entries must be non-empty names")
    return tuple(sorted(set(out)))


@dataclass(frozen=True)
class SystemDef:
    name: str
    fn: SystemFn
    phase: SystemPhase = SystemPhase.UPDATE
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    every: int = 1
    offset: int = 0
    run_if: RunCondition | None = None
    exclusive: bool = False
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_RE.fullmatch(self.name):
            raise ValidationError("invalid system name", context={"name": self.name})
        if not callable(self.fn):
            raise ValidationError("system fn must be callable", context={"name": self.name})
        object.__setattr__(self, "phase", SystemPhase(self.phase))
        for attr in ("reads", "writes", "after", "before"):
            object.__setattr__(self, attr, _tokens(getattr(self, attr), attr))
        if isinstance(self.every, bool) or not isinstance(self.every, int) or self.every < 1:
            raise ValidationError("every must be a positive integer", context={"name": self.name})
        if isinstance(self.offset, bool) or not isinstance(self.offset, int) or not 0 <= self.offset < self.every:
            raise ValidationError("offset must satisfy 0 <= offset < every", context={"name": self.name})
        if self.run_if is not None and not callable(self.run_if):
            raise ValidationError("run_if must be callable")

    @property
    def readable(self) -> frozenset[str]:
        return frozenset(self.reads) | frozenset(self.writes)

    def should_run(self, world: LiveWorld, tick: int) -> bool:
        if not self.enabled:
            return False
        if tick % self.every != self.offset:
            return False
        return bool(self.run_if(world)) if self.run_if is not None else True

    def spec(self, any_exclusive: bool) -> SystemSpec:
        reads = set(self.reads)
        writes = set(self.writes)
        if self.exclusive:
            writes.add(WORLD_TOKEN)
        elif any_exclusive:
            reads.add(WORLD_TOKEN)
        return SystemSpec(
            self.name, self.phase, reads=tuple(reads), writes=tuple(writes),
            after=self.after, before=self.before, enabled=self.enabled,
        )


class SystemContext:
    """What a system sees during one run. Enforces declared access when strict."""

    __slots__ = ("_rng", "commands", "dt", "since", "strict", "system", "tick", "world")

    def __init__(self, world: LiveWorld, commands: CommandQueue, tick: int, dt: float, since: int, system: SystemDef, strict: bool) -> None:
        self.world = world
        self.commands = commands
        self.tick = tick
        self.dt = dt
        self.since = since
        self.system = system
        self.strict = strict
        self._rng: DeterministicRng | None = None

    @property
    def name(self) -> str:
        return self.system.name

    def _check(self, names: Iterable[str], *, write: bool) -> None:
        if not self.strict or self.system.exclusive:
            return
        allowed = self.system.writes if write else self.system.readable
        for name in names:
            if name not in allowed:
                raise AccessViolationError(
                    "system accessed an undeclared " + ("write" if write else "read"),
                    context={"system": self.system.name, "name": name},
                )

    # -- components ---------------------------------------------------------
    def query(self, *fetch: str, **filters: Any):
        names = list(fetch)
        for key in ("optional", "with_", "without", "added", "changed"):
            value = filters.get(key, ())
            names.extend((value,) if isinstance(value, str) else value)
        self._check(names, write=False)
        mut = filters.get("mut", ())
        self._check((mut,) if isinstance(mut, str) else mut, write=True)
        if (filters.get("added") or filters.get("changed")) and "since" not in filters:
            filters["since"] = self.since
        return self.world.query(*fetch, **filters)

    def get(self, handle: int, name: str, *default: Any) -> Any:
        self._check((name,), write=False)
        return self.world.get(handle, name, *default)

    def has(self, handle: int, name: str) -> bool:
        self._check((name,), write=False)
        return self.world.has(handle, name)

    def get_mut(self, handle: int, name: str) -> Any:
        self._check((name,), write=True)
        return self.world.get_mut(handle, name)

    def set(self, handle: int, name: str, value: Any) -> None:
        """Replace an existing component value in place (non-structural)."""
        self._check((name,), write=True)
        if not self.world.has(handle, name):
            self.commands.insert(handle, name, value)
            return
        self.world.insert(handle, name, value)

    def patch(self, handle: int, name: str, fields: Mapping[str, Any]) -> Any:
        self._check((name,), write=True)
        return self.world.patch(handle, name, fields)

    def removed(self, name: str) -> tuple[int, ...]:
        self._check((name,), write=False)
        return self.world.removed(name)

    # -- resources ----------------------------------------------------------
    def resource(self, name: str, *default: Any) -> Any:
        self._check(("res:" + name,), write=False)
        return self.world.get_resource(name, *default)

    def set_resource(self, name: str, value: Any) -> None:
        self._check(("res:" + name,), write=True)
        self.world.set_resource(name, value)

    # -- events -------------------------------------------------------------
    def send(self, channel: str, payload: Any) -> None:
        self._check(("event:" + channel,), write=True)
        self.world.send(channel, payload)

    def read(self, channel: str) -> list[Any]:
        self._check(("event:" + channel,), write=False)
        return self.world.reader(channel, "system:" + self.system.name).payloads()

    def read_records(self, channel: str):
        self._check(("event:" + channel,), write=False)
        return self.world.reader(channel, "system:" + self.system.name).read()

    # -- randomness ---------------------------------------------------------
    @property
    def rng(self) -> DeterministicRng:
        if self._rng is None:
            self._rng = self.world.rng.fork(f"system:{self.system.name}:tick:{self.tick}")
        return self._rng


@dataclass(frozen=True)
class SystemRun:
    name: str
    ran: bool
    commands: int = 0
    change_tick: int = 0


@dataclass(frozen=True)
class TickReport:
    tick: int
    plan_fingerprint: str
    systems: tuple[SystemRun, ...]
    applied: int
    skipped_commands: tuple = ()
    state_digest: str | None = None

    @property
    def ran(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.systems if s.ran)


class SystemFailure(ScheduleError):
    code = "SIM.ECS.SYSTEM_FAILURE"


class TickScheduler:
    def __init__(self, *, strict_access: bool = True, atomic: bool = False, fixed_dt: float = 1.0 / 60.0, digest_each_tick: bool = False) -> None:
        if not isinstance(fixed_dt, (int, float)) or isinstance(fixed_dt, bool) or not fixed_dt > 0:
            raise ValidationError("fixed_dt must be positive")
        self.strict_access = bool(strict_access)
        self.atomic = bool(atomic)
        self.fixed_dt = float(fixed_dt)
        self.digest_each_tick = bool(digest_each_tick)
        self._systems: dict[str, SystemDef] = {}
        self._plan: ExecutionPlan | None = None

    # -- registration -----------------------------------------------------
    def add(self, definition: SystemDef) -> SystemDef:
        if not isinstance(definition, SystemDef):
            raise ValidationError("add requires a SystemDef")
        if definition.name in self._systems:
            raise ScheduleError("duplicate system name", context={"name": definition.name})
        # Planning is lazy so systems may be added in any order; unknown
        # ``after``/``before`` targets and cycles surface on plan()/run_tick().
        self._systems[definition.name] = definition
        self._plan = None
        return definition

    def add_system(self, fn: SystemFn, *, name: str | None = None, **options: Any) -> SystemDef:
        return self.add(SystemDef(name or getattr(fn, "__name__", ""), fn, **options))

    def system(self, **options: Any) -> Callable[[SystemFn], SystemFn]:
        """Decorator form of :meth:`add_system`."""
        def decorate(fn: SystemFn) -> SystemFn:
            self.add_system(fn, **options)
            return fn
        return decorate

    def remove(self, name: str) -> SystemDef:
        if name not in self._systems:
            raise ScheduleError("unknown system", context={"name": name})
        dependants = [d.name for d in self._systems.values() if name in d.after or name in d.before]
        if dependants:
            raise ScheduleError("system is referenced by other systems", context={"name": name, "dependants": sorted(dependants)})
        self._plan = None
        return self._systems.pop(name)

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._systems:
            raise ScheduleError("unknown system", context={"name": name})
        old = self._systems[name]
        self._systems[name] = SystemDef(**{**old.__dict__, "enabled": bool(enabled)})
        self._plan = None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._systems))

    def get(self, name: str) -> SystemDef:
        return self._systems[name]

    # -- planning ---------------------------------------------------------
    def plan(self) -> ExecutionPlan:
        if self._plan is None:
            graph = SystemGraph()
            any_exclusive = any(d.exclusive for d in self._systems.values())
            for name in sorted(self._systems):
                graph.register(self._systems[name].spec(any_exclusive))
            self._plan = graph.plan()
        return self._plan

    # -- execution --------------------------------------------------------
    def run_tick(self, world: LiveWorld) -> TickReport:
        plan = self.plan()
        snapshot = world.snapshot() if self.atomic else None
        last_run: dict[str, int] = dict(world.meta.get(LAST_RUN_META, {}))
        pending: list[CommandQueue] = []
        runs: list[SystemRun] = []
        applied = 0
        skipped: list = []
        world.tick += 1
        tick = world.tick
        current: str | None = None
        try:
            for batch in plan.batches:
                queues: list[CommandQueue] = []
                for name in batch.system_ids:
                    definition = self._systems[name]
                    if not definition.should_run(world, tick):
                        runs.append(SystemRun(name, False))
                        continue
                    current = name
                    world.change_tick += 1
                    queue = CommandQueue(world, source=name)
                    pending.append(queue)
                    ctx = SystemContext(world, queue, tick, self.fixed_dt, last_run.get(name, -1), definition, self.strict_access)
                    definition.fn(ctx)
                    last_run[name] = world.change_tick
                    queues.append(queue)
                    runs.append(SystemRun(name, True, len(queue), world.change_tick))
                current = None
                if queues:
                    world.change_tick += 1
                    for queue in queues:
                        receipt: ApplyReceipt = queue.apply()
                        applied += receipt.applied
                        skipped.extend(receipt.skipped)
            world.meta[LAST_RUN_META] = {k: last_run[k] for k in sorted(last_run)}
            world.events.update()
            world.clear_trackers()
        except Exception as exc:
            for queue in pending:
                queue.discard()
            if snapshot is not None:
                world.restore(snapshot)
            else:
                world.meta[LAST_RUN_META] = {k: last_run[k] for k in sorted(last_run)}
            if current is not None:
                raise SystemFailure(
                    "system raised during tick",
                    context={"system": current, "tick": tick, "error_type": type(exc).__name__, "error": str(exc)[:500], "rolled_back": snapshot is not None},
                ) from exc
            raise
        return TickReport(
            tick=tick,
            plan_fingerprint=plan.fingerprint,
            systems=tuple(runs),
            applied=applied,
            skipped_commands=tuple(skipped),
            state_digest=world.state_digest if self.digest_each_tick else None,
        )

    def run(self, world: LiveWorld, ticks: int) -> list[TickReport]:
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
            raise ValidationError("ticks must be a non-negative integer")
        return [self.run_tick(world) for _ in range(ticks)]

    def fingerprint(self) -> str:
        return digest({
            "domain": "skeleton.simulation.ecs.tick_scheduler.v1",
            "plan": self.plan().fingerprint,
            "cadence": {n: [d.every, d.offset, d.enabled, d.exclusive] for n, d in sorted(self._systems.items())},
            "fixed_dt": self.fixed_dt.hex(),
        })


@dataclass
class FrameReport:
    ticks: int
    alpha: float
    dropped_ns: int
    reports: list[TickReport] = field(default_factory=list)


class FixedStepRunner:
    """Variable frame time in, fixed deterministic ticks out."""

    def __init__(self, scheduler: TickScheduler, world: LiveWorld, *, step_ns: int | None = None, max_substeps: int = 8) -> None:
        if step_ns is None:
            step_ns = round(scheduler.fixed_dt * 1_000_000_000)
        if isinstance(step_ns, bool) or not isinstance(step_ns, int) or step_ns < 1:
            raise ValidationError("step_ns must be a positive integer")
        if isinstance(max_substeps, bool) or not isinstance(max_substeps, int) or not 1 <= max_substeps <= MAX_SUBSTEPS:
            raise ValidationError("max_substeps out of range")
        self.scheduler = scheduler
        self.world = world
        self.step_ns = step_ns
        self.max_substeps = max_substeps
        self.accumulator_ns = 0

    def advance(self, frame_ns: int) -> FrameReport:
        if isinstance(frame_ns, bool) or not isinstance(frame_ns, int) or frame_ns < 0:
            raise ValidationError("frame_ns must be a non-negative integer")
        self.accumulator_ns += frame_ns
        reports = []
        while self.accumulator_ns >= self.step_ns and len(reports) < self.max_substeps:
            reports.append(self.scheduler.run_tick(self.world))
            self.accumulator_ns -= self.step_ns
        dropped = 0
        if self.accumulator_ns >= self.step_ns:
            # Clamp: keep at most one step of backlog instead of spiralling.
            dropped = self.accumulator_ns - (self.accumulator_ns % self.step_ns)
            self.accumulator_ns -= dropped
        return FrameReport(len(reports), self.accumulator_ns / self.step_ns, dropped, reports)


__all__ = [
    "LAST_RUN_META",
    "FixedStepRunner",
    "FrameReport",
    "SystemContext",
    "SystemDef",
    "SystemFailure",
    "SystemRun",
    "TickReport",
    "TickScheduler",
]
