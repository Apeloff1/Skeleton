"""Compile and run AST-sandboxed game-logic scripts.

A script is plain Python restricted by :mod:`.script_policy`, instrumented by
:mod:`.script_rewrite` and executed against the guard namespace from
:mod:`.script_guard`.  Typical use::

    script = compile_script('''
    def on_tick(api):
        for e, hp in query("health"):
            if hp["hp"] <= 0:
                despawn(e)
    ''', name="reaper")
    script.call("on_tick", None, api={...})

Values crossing the host/script boundary are restricted to the ECS value
domain (``None``/bool/int/float/str/list/tuple/dict) and deep-copied, so a
script never holds a reference to host state.
"""
from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import CodeType, FunctionType
from typing import Any

from skeleton.simulation.ecs.errors import (
    ScriptError,
    ScriptLimitError,
    ScriptRuntimeError,
    ScriptValidationError,
)

from .script_guard import Budget, build_globals
from .script_policy import validate_source
from .script_rewrite import instrument

_PLAIN = (type(None), bool, int, float, str)
MAX_BOUNDARY_DEPTH = 32
MAX_BOUNDARY_ITEMS = 100_000


def to_script_value(value: Any, *, _depth: int = 0, _count: list[int] | None = None) -> Any:
    """Deep-copy ``value`` into the script value domain (raises on host objects)."""
    count = _count if _count is not None else [0]
    count[0] += 1
    if count[0] > MAX_BOUNDARY_ITEMS:
        raise ScriptRuntimeError("value crossing the sandbox boundary is too large")
    if _depth > MAX_BOUNDARY_DEPTH:
        raise ScriptRuntimeError("value crossing the sandbox boundary is nested too deeply")
    if isinstance(value, _PLAIN):
        return value
    if isinstance(value, (list, tuple)):
        items = [to_script_value(v, _depth=_depth + 1, _count=count) for v in value]
        return items if isinstance(value, list) else tuple(items)
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if not isinstance(k, (str, int)) or isinstance(k, bool):
                raise ScriptRuntimeError("mapping keys crossing the sandbox must be str or int", context={"key_type": type(k).__name__})
            out[k] = to_script_value(v, _depth=_depth + 1, _count=count)
        return out
    raise ScriptRuntimeError("value type cannot cross the sandbox boundary", context={"type": type(value).__name__})


@dataclass(frozen=True)
class ScriptLimits:
    max_steps: int = 200_000
    max_depth: int = 48
    max_memory: int = 8 * 1024 * 1024
    max_seconds: float = 0.25

    def budget(self, clock: Callable[[], float] | None = None) -> Budget:
        kw: dict[str, Any] = {}
        if clock is not None:
            kw["clock"] = clock
        return Budget(max_steps=self.max_steps, max_depth=self.max_depth, max_memory=self.max_memory, max_seconds=self.max_seconds, **kw)


@dataclass
class ScriptResult:
    value: Any
    usage: dict[str, Any]


@dataclass
class CompiledScript:
    name: str
    source: str
    digest: str
    code: CodeType
    functions: tuple[str, ...]
    limits: ScriptLimits = field(default_factory=ScriptLimits)

    def instantiate(self, api: Mapping[str, Any] | None = None, *, clock: Callable[[], float] | None = None) -> ScriptInstance:
        return ScriptInstance(self, api or {}, clock=clock)

    def call(self, function: str, *args: Any, api: Mapping[str, Any] | None = None, clock: Callable[[], float] | None = None) -> ScriptResult:
        """One-shot: fresh namespace, run module body, then ``function(*args)``."""
        return self.instantiate(api, clock=clock).call(function, *args)


class ScriptInstance:
    """A script's module namespace, persisting top-level state between calls.

    Module-level variables survive across :meth:`call` invocations (useful
    for counters/cooldowns) but every call gets a fresh budget.
    """

    def __init__(self, script: CompiledScript, api: Mapping[str, Any], *, clock: Callable[[], float] | None = None) -> None:
        self.script = script
        self.budget = script.limits.budget(clock)
        self.globals = build_globals(self.budget, api)
        self._run(lambda: exec(script.code, self.globals))  # noqa: S102 - instrumented, policy-validated code

    def has(self, function: str) -> bool:
        return isinstance(self.globals.get(function), FunctionType) and function in self.script.functions

    def bind(self, name: str, value: Any) -> None:
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ScriptRuntimeError("invalid binding name", context={"name": name})
        self.globals[name] = value

    def call(self, function: str, *args: Any) -> ScriptResult:
        if not self.has(function):
            raise ScriptRuntimeError("script has no such function", context={"script": self.script.name, "function": function})
        fn = self.globals[function]
        safe_args = tuple(to_script_value(a) for a in args)
        value = self._run(lambda: fn(*safe_args))
        return ScriptResult(to_script_value(value), self.budget.usage())

    def _run(self, thunk: Callable[[], Any]) -> Any:
        self.budget.reset()
        try:
            return thunk()
        except ScriptError:
            raise
        except RecursionError as exc:
            raise ScriptLimitError("script recursion exhausted the host stack", context={"script": self.script.name}) from exc
        except MemoryError as exc:
            raise ScriptLimitError("script exhausted host memory", context={"script": self.script.name}) from exc
        except Exception as exc:  # noqa: BLE001 - normalise script faults
            raise ScriptRuntimeError(
                f"{type(exc).__name__}: {exc}"[:500],
                context={"script": self.script.name, "error_type": type(exc).__name__, "line": _script_line(exc)},
            ) from None


def _script_line(exc: BaseException) -> int | None:
    tb = exc.__traceback__
    line = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename.startswith("<script:"):
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def compile_script(source: str, *, name: str = "script", limits: ScriptLimits | None = None) -> CompiledScript:
    """Validate, instrument and compile ``source`` (raises ScriptValidationError)."""
    if not isinstance(name, str) or not name or len(name) > 128:
        raise ScriptValidationError("invalid script name", context={"violations": []})
    filename = f"<script:{name}>"
    tree = validate_source(source, filename=filename)
    functions = tuple(n.name for n in tree.body if isinstance(n, ast.FunctionDef))
    instrumented = instrument(tree)
    code = compile(instrumented, filename, "exec", dont_inherit=True)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return CompiledScript(name=name, source=source, digest=digest, code=code, functions=functions, limits=limits or ScriptLimits())


def check_script(source: str) -> list[dict[str, Any]]:
    """Editor helper: ``[]`` when valid, else the ordered violation records."""
    try:
        validate_source(source)
    except ScriptValidationError as exc:
        return list(exc.context.get("violations", []))
    return []


__all__ = [
    "CompiledScript",
    "ScriptInstance",
    "ScriptLimits",
    "ScriptResult",
    "check_script",
    "compile_script",
    "to_script_value",
]
