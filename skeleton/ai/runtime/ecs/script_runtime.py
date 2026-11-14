"""B023: capability-scoped host for sandboxed gameplay scripts.

Builds on the AST sandbox in :mod:`.script` (policy -> rewrite -> guards) and
adds the runtime contract the B023 spec asks for:

* **Capability permissions** - every host API function is registered under a
  capability (``"ecs.read"``, ``"ecs.write"``, ``"audio.play"`` ...).  A
  script only ever sees the functions of capabilities it was *granted*; an
  ungranted or unknown capability is never exposed (fail-closed).
* **Quotas** - per-script cumulative ceilings (calls, steps) across
  invocations on top of the per-call :class:`ScriptLimits` budget.  A script
  that exceeds a quota, or faults ``max_faults`` times, is quarantined and
  every further call is refused until an explicit reload.
* **Diagnostics** - a bounded, structured log of validation failures, limit
  hits, runtime faults, quota refusals and reloads.
* **Hot-reload boundaries** - :meth:`ScriptHost.reload` validates and
  compiles the new source *before* touching the running instance; a failing
  reload keeps the previous version live.  Only declared persistent keys are
  carried over, and only through :func:`to_script_value` (plain data).

Nothing here evaluates untrusted text directly: all code goes through
:func:`compile_script`, which rejects imports, IO and dunder escapes.
"""
from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from skeleton.simulation.ecs.errors import (
    ScriptError,
    ScriptLimitError,
    ScriptRuntimeError,
    ScriptValidationError,
)

from .script import CompiledScript, ScriptInstance, ScriptLimits, ScriptResult, compile_script, to_script_value

_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
MAX_DIAGNOSTICS = 256
MAX_CAPABILITIES = 64


class CapabilityError(ScriptError):
    """Capability registration/grant rejected."""

    code = "SIM.ECS.SCRIPT.CAPABILITY"


class QuotaExceededError(ScriptLimitError):
    """A cumulative per-script quota was exhausted; the script is quarantined."""

    code = "SIM.ECS.SCRIPT.QUOTA"


class ScriptQuarantinedError(ScriptRuntimeError):
    """The script is quarantined and refuses calls until reloaded."""

    code = "SIM.ECS.SCRIPT.QUARANTINED"


def _require_capability(name: str) -> str:
    if not isinstance(name, str) or not _CAPABILITY_RE.match(name):
        raise CapabilityError("invalid capability name", context={"capability": name})
    return name


class CapabilityRegistry:
    """Maps capability -> {api name: host callable}."""

    def __init__(self) -> None:
        self._caps: dict[str, dict[str, Callable[..., Any]]] = {}
        self._owner: dict[str, str] = {}

    def register(self, capability: str, name: str, fn: Callable[..., Any]) -> None:
        _require_capability(capability)
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise CapabilityError("invalid api name", context={"name": name})
        if not callable(fn):
            raise CapabilityError("api must be callable", context={"name": name})
        if name in self._owner and self._owner[name] != capability:
            raise CapabilityError("api name already owned by another capability", context={"name": name, "owner": self._owner[name]})
        if capability not in self._caps and len(self._caps) >= MAX_CAPABILITIES:
            raise CapabilityError("capability budget exceeded")
        self._caps.setdefault(capability, {})[name] = fn
        self._owner[name] = capability

    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._caps))

    def api_for(self, grants: Iterable[str]) -> dict[str, Callable[..., Any]]:
        api: dict[str, Callable[..., Any]] = {}
        for cap in sorted(set(grants)):
            _require_capability(cap)
            if cap not in self._caps:
                raise CapabilityError("unknown capability", context={"capability": cap})
            api.update(self._caps[cap])
        return api


@dataclass(frozen=True)
class ScriptQuota:
    max_calls: int = 10_000
    max_total_steps: int = 50_000_000
    max_faults: int = 3

    def __post_init__(self) -> None:
        for k in ("max_calls", "max_total_steps", "max_faults"):
            v = getattr(self, k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                raise ScriptRuntimeError("quota values must be positive ints", context={"field": k})


@dataclass(frozen=True)
class Diagnostic:
    seq: int
    script: str
    kind: str  # validation | limit | fault | quota | quarantine | reload | reload_rejected
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "script": self.script, "kind": self.kind, "message": self.message, "context": dict(self.context)}


@dataclass
class _Slot:
    compiled: CompiledScript
    instance: ScriptInstance
    grants: frozenset[str]
    quota: ScriptQuota
    persistent: tuple[str, ...]
    generation: int = 1
    calls: int = 0
    total_steps: int = 0
    faults: int = 0
    quarantined: bool = False


class ScriptHost:
    """Loads, runs and hot-reloads scripts under capability grants and quotas."""

    def __init__(self, registry: CapabilityRegistry, *, limits: ScriptLimits | None = None, clock: Callable[[], float] | None = None) -> None:
        self.registry = registry
        self.limits = limits or ScriptLimits()
        self._clock = clock
        self._slots: dict[str, _Slot] = {}
        self._diag: deque[Diagnostic] = deque(maxlen=MAX_DIAGNOSTICS)
        self._seq = 0

    # -- diagnostics -------------------------------------------------
    def _log(self, script: str, kind: str, message: str, **context: Any) -> None:
        self._seq += 1
        self._diag.append(Diagnostic(self._seq, script, kind, str(message)[:500], context))

    def diagnostics(self, script: str | None = None) -> list[dict[str, Any]]:
        return [d.as_dict() for d in self._diag if script is None or d.script == script]

    # -- lifecycle ---------------------------------------------------
    def _build(self, name: str, source: str, grants: frozenset[str]) -> tuple[CompiledScript, ScriptInstance]:
        api = self.registry.api_for(grants)
        compiled = compile_script(source, name=name, limits=self.limits)
        return compiled, compiled.instantiate(api, clock=self._clock)

    def load(self, name: str, source: str, *, grants: Iterable[str] = (), quota: ScriptQuota | None = None, persistent: Iterable[str] = ()) -> int:
        if name in self._slots:
            raise ScriptRuntimeError("script already loaded; use reload", context={"script": name})
        grant_set = frozenset(grants)
        keys = tuple(sorted(set(persistent)))
        for k in keys:
            if not isinstance(k, str) or not _NAME_RE.match(k):
                raise ScriptRuntimeError("invalid persistent key", context={"key": k})
        try:
            compiled, instance = self._build(name, source, grant_set)
        except ScriptValidationError as exc:
            self._log(name, "validation", str(exc), violations=list(exc.context.get("violations", [])))
            raise
        except ScriptError as exc:
            self._log(name, "fault", str(exc), stage="load")
            raise
        self._slots[name] = _Slot(compiled, instance, grant_set, quota or ScriptQuota(), keys)
        return 1

    def reload(self, name: str, source: str) -> int:
        """Swap in new source; on any failure the old generation stays live."""
        slot = self._require(name)
        if source == slot.compiled.source and not slot.quarantined:
            return slot.generation
        try:
            compiled, instance = self._build(name, source, slot.grants)
            carried = {k: to_script_value(slot.instance.globals[k]) for k in slot.persistent if k in slot.instance.globals}
            for k, v in carried.items():
                instance.bind(k, v)
        except ScriptError as exc:
            self._log(name, "reload_rejected", str(exc), generation=slot.generation, violations=list(exc.context.get("violations", [])))
            raise
        slot.compiled, slot.instance = compiled, instance
        slot.generation += 1
        slot.calls = slot.total_steps = slot.faults = 0
        slot.quarantined = False
        self._log(name, "reload", "reloaded", generation=slot.generation, digest=compiled.digest, carried=sorted(carried))
        return slot.generation

    def unload(self, name: str) -> None:
        self._require(name)
        del self._slots[name]

    def _require(self, name: str) -> _Slot:
        try:
            return self._slots[name]
        except KeyError:
            raise ScriptRuntimeError("no such script", context={"script": name}) from None

    # -- execution ---------------------------------------------------
    def call(self, name: str, function: str, *args: Any) -> ScriptResult:
        slot = self._require(name)
        if slot.quarantined:
            raise ScriptQuarantinedError("script is quarantined", context={"script": name, "generation": slot.generation})
        if slot.calls >= slot.quota.max_calls:
            self._quarantine(slot, name, "call quota exhausted")
            raise QuotaExceededError("call quota exhausted", context={"script": name})
        slot.calls += 1
        try:
            result = slot.instance.call(function, *args)
        except ScriptLimitError as exc:
            self._log(name, "limit", str(exc), function=function, error=type(exc).__name__)
            self._fault(slot, name)
            raise
        except ScriptError as exc:
            self._log(name, "fault", str(exc), function=function, line=exc.context.get("line"))
            self._fault(slot, name)
            raise
        slot.total_steps += int(result.usage.get("steps", 0))
        if slot.total_steps > slot.quota.max_total_steps:
            self._quarantine(slot, name, "step quota exhausted")
        return result

    def _fault(self, slot: _Slot, name: str) -> None:
        slot.faults += 1
        if slot.faults >= slot.quota.max_faults:
            self._quarantine(slot, name, "fault budget exhausted")

    def _quarantine(self, slot: _Slot, name: str, reason: str) -> None:
        if not slot.quarantined:
            slot.quarantined = True
            self._log(name, "quarantine", reason, generation=slot.generation)

    def status(self, name: str) -> dict[str, Any]:
        s = self._require(name)
        return {
            "script": name,
            "generation": s.generation,
            "digest": s.compiled.digest,
            "grants": sorted(s.grants),
            "calls": s.calls,
            "total_steps": s.total_steps,
            "faults": s.faults,
            "quarantined": s.quarantined,
        }


__all__ = [
    "CapabilityError",
    "CapabilityRegistry",
    "Diagnostic",
    "QuotaExceededError",
    "ScriptHost",
    "ScriptQuarantinedError",
    "ScriptQuota",
]
