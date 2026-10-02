"""Run sandboxed scripts as ECS systems.

:func:`script_system` turns a :class:`~.script.CompiledScript` exposing
``on_tick()`` into a :class:`~skeleton.simulation.ecs.ticker.SystemDef`.
During each run the script sees a small host API bound to that tick's
:class:`SystemContext` (so declared ``reads``/``writes`` are enforced by
the scheduler's strict access checks):

=================  =========================================================
``query(*names)``  list of ``[entity, value, ...]`` rows (deep copies)
``read(e, name)``  one component value (``None`` if absent)
``write(e, n, v)`` replace / insert a component value
``patch(e, n, d)`` merge fields into a component value
``spawn(d)``       deferred spawn of ``{component: value}``
``despawn(e)``     deferred despawn
``emit(ch, p)``    send an event
``events(ch)``     payloads received on a channel since last run
``resource(n)``    read a resource (``None`` if absent)
``store(n, v)``    write a resource
``rand()``         deterministic float in [0, 1) for this system/tick
``randint(a, b)``  deterministic integer in [a, b]
``tick``, ``dt``   current tick number and fixed step
=================  =========================================================

Structural changes always go through the command queue, so scripts can
never trip the "structural change during iteration" guard.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from skeleton.simulation.ecs.errors import ScriptRuntimeError, ValidationError
from skeleton.simulation.ecs.schedule import SystemPhase
from skeleton.simulation.ecs.ticker import SystemContext, SystemDef

from .script import CompiledScript, ScriptInstance, compile_script, to_script_value

ENTRYPOINT = "on_tick"
MAX_QUERY_ROWS = 10_000


def _host(value: Any) -> Any:
    """Values coming *out* of a script are re-validated into the value domain."""
    return to_script_value(value)


def _entity(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScriptRuntimeError("entity handles are non-negative integers", context={"value": repr(value)[:40]})
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ScriptRuntimeError(f"{label} must be a non-empty string")
    return value


def build_api(ctx: SystemContext) -> dict[str, Any]:
    """Host API for one system run (closures over ``ctx``)."""

    def query(*names: Any) -> list[list[Any]]:
        fetch = [_name(n, "component name") for n in names]
        rows: list[list[Any]] = []
        for row in ctx.query(*fetch):
            rows.append([row[0], *(to_script_value(v) for v in row[1:])])
            if len(rows) > MAX_QUERY_ROWS:
                raise ScriptRuntimeError("query returned too many rows", context={"maximum": MAX_QUERY_ROWS})
        return rows

    def read(e: Any, name: Any) -> Any:
        handle, comp = _entity(e), _name(name, "component name")
        if not ctx.world.is_alive(handle):
            return None
        return to_script_value(ctx.get(handle, comp, None))

    def write(e: Any, name: Any, value: Any) -> None:
        ctx.set(_entity(e), _name(name, "component name"), _host(value))

    def patch(e: Any, name: Any, fields: Any) -> None:
        if not isinstance(fields, Mapping):
            raise ScriptRuntimeError("patch fields must be a dict")
        ctx.patch(_entity(e), _name(name, "component name"), _host(fields))

    def spawn(components: Any = None) -> None:
        if components is not None and not isinstance(components, Mapping):
            raise ScriptRuntimeError("spawn takes a dict of components")
        comps = _host(components or {})
        ctx._check(comps.keys(), write=True)  # noqa: SLF001 - same-package access contract
        ctx.commands.spawn(comps)

    def despawn(e: Any) -> None:
        ctx.commands.despawn(_entity(e))

    def emit(channel: Any, payload: Any = None) -> None:
        ctx.send(_name(channel, "channel"), _host(payload))

    def events(channel: Any) -> list[Any]:
        return [to_script_value(p) for p in ctx.read(_name(channel, "channel"))]

    def resource(name: Any) -> Any:
        return to_script_value(ctx.resource(_name(name, "resource"), None))

    def store(name: Any, value: Any) -> None:
        ctx.set_resource(_name(name, "resource"), _host(value))

    def rand() -> float:
        return ctx.rng.random()

    def randint(a: Any, b: Any) -> int:
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (a, b)) or a > b:
            raise ScriptRuntimeError("randint(a, b) needs integers with a <= b")
        return ctx.rng.randint(a, b)

    return {
        "query": query, "read": read, "write": write, "patch": patch, "spawn": spawn, "despawn": despawn,
        "emit": emit, "events": events, "resource": resource, "store": store, "rand": rand, "randint": randint,
        "tick": ctx.tick, "dt": ctx.dt,
    }


class ScriptSystem:
    """Callable system body backed by a persistent :class:`ScriptInstance`."""

    def __init__(self, script: CompiledScript, entrypoint: str = ENTRYPOINT) -> None:
        if entrypoint not in script.functions:
            raise ValidationError("script lacks its entrypoint", context={"script": script.name, "entrypoint": entrypoint})
        self.script = script
        self.entrypoint = entrypoint
        self.instance: ScriptInstance | None = None
        self.runs = 0
        self.last_usage: dict[str, Any] = {}

    def __call__(self, ctx: SystemContext) -> None:
        api = build_api(ctx)
        if self.instance is None:
            self.instance = self.script.instantiate(api)
        else:
            for key, value in api.items():
                self.instance.bind(key, value)
        result = self.instance.call(self.entrypoint)
        self.runs += 1
        self.last_usage = result.usage


def script_system(
    script: CompiledScript | str,
    *,
    name: str | None = None,
    reads: Iterable[str] = (),
    writes: Iterable[str] = (),
    after: Iterable[str] = (),
    before: Iterable[str] = (),
    phase: SystemPhase | int = SystemPhase.UPDATE,
    every: int = 1,
    offset: int = 0,
    entrypoint: str = ENTRYPOINT,
) -> SystemDef:
    """Build a scheduler :class:`SystemDef` that runs ``script`` each tick."""
    compiled = compile_script(script, name=name or "script") if isinstance(script, str) else script
    body = ScriptSystem(compiled, entrypoint)
    return SystemDef(
        name=name or compiled.name,
        fn=body,
        phase=phase,
        reads=tuple(reads),
        writes=tuple(writes),
        after=tuple(after),
        before=tuple(before),
        every=every,
        offset=offset,
    )


__all__ = ["ENTRYPOINT", "ScriptSystem", "build_api", "script_system"]
