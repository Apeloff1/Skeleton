"""Runtime guards for sandboxed scripts (sandbox layer 3).

:class:`Budget` meters steps, call depth, modelled memory and wall time.
:func:`build_globals` assembles the only namespace a script ever sees: a
curated builtins table, a frozen ``math`` namespace and the ``_sbx_*`` guard
functions the rewriter (:mod:`.script_rewrite`) injects calls to.

Every attribute call/load is mediated by :data:`METHOD_TABLE` keyed on the
*concrete* receiver type, so even if a policy allowlist name is reached on an
unexpected object (e.g. ``some_function.get``) it is refused.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from skeleton.simulation.ecs.errors import (
    ScriptDepthLimitError,
    ScriptMemoryLimitError,
    ScriptRuntimeError,
    ScriptStepLimitError,
    ScriptTimeLimitError,
)

DEFAULT_MAX_STEPS = 200_000
DEFAULT_MAX_DEPTH = 48
DEFAULT_MAX_MEMORY = 8 * 1024 * 1024  # modelled bytes
DEFAULT_MAX_SECONDS = 0.25
MAX_INT_BITS = 4_096
MAX_SEQUENCE = 1_000_000


class Budget:
    """Mutable per-invocation execution budget."""

    __slots__ = ("_clock", "deadline", "depth", "max_depth", "max_memory", "max_seconds", "max_steps", "memory", "steps")

    def __init__(
        self,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_memory: int = DEFAULT_MAX_MEMORY,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        for label, value in (("max_steps", max_steps), ("max_depth", max_depth), ("max_memory", max_memory)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if not isinstance(max_seconds, (int, float)) or max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.max_memory = max_memory
        self.max_seconds = float(max_seconds)
        self._clock = clock
        self.steps = 0
        self.depth = 0
        self.memory = 0
        self.deadline = clock() + self.max_seconds

    def reset(self) -> None:
        self.steps = 0
        self.depth = 0
        self.memory = 0
        self.deadline = self._clock() + self.max_seconds

    def step(self, n: int = 1) -> None:
        self.steps += n
        if self.steps > self.max_steps:
            raise ScriptStepLimitError("script exceeded its step budget", context={"max_steps": self.max_steps})
        if (self.steps & 0x3FF) < n or n > 1024:
            self.check_time()

    def check_time(self) -> None:
        if self._clock() > self.deadline:
            raise ScriptTimeLimitError("script exceeded its time budget", context={"max_seconds": self.max_seconds})

    def enter(self) -> None:
        self.depth += 1
        if self.depth > self.max_depth:
            raise ScriptDepthLimitError("script exceeded its call-depth budget", context={"max_depth": self.max_depth})

    def leave(self) -> None:
        self.depth = max(0, self.depth - 1)

    def alloc(self, nbytes: int) -> None:
        self.memory += max(0, int(nbytes))
        if self.memory > self.max_memory:
            raise ScriptMemoryLimitError("script exceeded its memory budget", context={"max_memory": self.max_memory})

    def usage(self) -> dict[str, Any]:
        return {"steps": self.steps, "memory": self.memory, "max_steps": self.max_steps, "max_memory": self.max_memory}


# ---------------------------------------------------------------------------
# size model
# ---------------------------------------------------------------------------
def size_of(value: Any) -> int:
    """Cheap modelled size (bytes) of a script value — shallow by design."""
    if value is None or isinstance(value, bool):
        return 8
    if isinstance(value, int):
        return 28 + value.bit_length() // 8
    if isinstance(value, float):
        return 24
    if isinstance(value, str):
        return 49 + len(value)
    if isinstance(value, bytes):
        return 33 + len(value)
    if isinstance(value, (list, tuple)):
        return 56 + 8 * len(value)
    if isinstance(value, dict):
        return 64 + 24 * len(value)
    return 64


def _length(value: Any) -> int | None:
    if isinstance(value, (str, bytes, list, tuple)):
        return len(value)
    return None


def _predict_binop(op: str, a: Any, b: Any) -> int:
    """Predict result size *before* computing; raise if clearly unbounded."""
    if op == "*":
        for seq, n in ((a, b), (b, a)):
            ln = _length(seq)
            if ln is not None and isinstance(n, int) and not isinstance(n, bool):
                count = ln * max(0, n)
                if count > MAX_SEQUENCE:
                    raise ScriptMemoryLimitError("sequence repetition too large", context={"length": count})
                return count * (1 if isinstance(seq, (str, bytes)) else 8)
        if isinstance(a, int) and isinstance(b, int):
            bits = a.bit_length() + b.bit_length()
            if bits > MAX_INT_BITS:
                raise ScriptMemoryLimitError("integer result too large", context={"bits": bits})
            return bits // 8
        return 0
    if op == "**":
        if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool):
            if b < 0:
                return 24
            if abs(a) > 1:
                bits = a.bit_length() * b
                if bits > MAX_INT_BITS:
                    raise ScriptMemoryLimitError("integer power too large", context={"bits": bits})
                return bits // 8
            return 28
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return 24
        return 0
    if op == "<<":
        if isinstance(a, int) and isinstance(b, int):
            if b < 0:
                return 0
            bits = a.bit_length() + b
            if bits > MAX_INT_BITS:
                raise ScriptMemoryLimitError("shift result too large", context={"bits": bits})
            return bits // 8
        return 0
    if op == "+":
        la, lb = _length(a), _length(b)
        if la is not None and lb is not None:
            if la + lb > MAX_SEQUENCE:
                raise ScriptMemoryLimitError("concatenation too large", context={"length": la + lb})
            return la + lb
        return 0
    if op == "%":
        if isinstance(a, (str, bytes)):
            # printf-style formatting: bound by inputs; widths are policy-limited.
            return len(a) + size_of(b)
        return 0
    return 0


_BINOPS: dict[str, Callable[[Any, Any], Any]] = {
    "+": lambda a, b: a + b,
    "*": lambda a, b: a * b,
    "**": lambda a, b: a ** b,
    "<<": lambda a, b: a << b,
    "%": lambda a, b: a % b,
}


# ---------------------------------------------------------------------------
# attribute mediation
# ---------------------------------------------------------------------------
_STR_METHODS = frozenset({
    "capitalize", "casefold", "center", "count", "endswith", "find", "index", "isalnum",
    "isalpha", "isdigit", "islower", "isnumeric", "isspace", "istitle", "isupper", "join",
    "ljust", "lower", "lstrip", "partition", "removeprefix", "removesuffix", "replace",
    "rfind", "rindex", "rjust", "rpartition", "rsplit", "rstrip", "split", "splitlines",
    "startswith", "strip", "swapcase", "title", "upper", "zfill",
})
_GROWING_STR = frozenset({"center", "ljust", "rjust", "zfill", "replace", "join"})

METHOD_TABLE: dict[type, frozenset[str]] = {
    str: _STR_METHODS,
    list: frozenset({"append", "clear", "copy", "count", "extend", "index", "insert", "pop", "remove", "reverse", "sort"}),
    dict: frozenset({"clear", "copy", "get", "items", "keys", "pop", "popitem", "setdefault", "update", "values"}),
    tuple: frozenset({"count", "index"}),
    int: frozenset({"bit_length"}),
    float: frozenset({"is_integer", "hex"}),
    bytes: frozenset({"decode", "hex"}),
}


class MathNamespace:
    """Read-only math namespace exposed to scripts as ``math``."""

    __slots__ = ()
    _members: Mapping[str, Any] = {}

    def __repr__(self) -> str:
        return "<sandbox math>"


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


MATH_MEMBERS: dict[str, Any] = {
    "pi": math.pi, "tau": math.tau, "e": math.e, "inf": math.inf,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "floor": math.floor, "ceil": math.ceil, "trunc": math.trunc, "fabs": math.fabs,
    "hypot": math.hypot, "exp": math.exp, "log": math.log, "log2": math.log2, "log10": math.log10,
    "degrees": math.degrees, "radians": math.radians, "isfinite": math.isfinite,
    "isclose": math.isclose, "copysign": math.copysign, "fmod": math.fmod, "gcd": math.gcd,
    "dist": math.dist, "lerp": _lerp, "clamp": _clamp, "sign": _sign,
}


def _math_pow(a: float, b: float) -> float:
    return math.pow(a, b)


MATH_MEMBERS["pow"] = _math_pow
MATH = MathNamespace()


class ScriptRecord:
    """Opaque read-only record handed to scripts (e.g. entity views).

    Scripts reach fields only via ``rec.get(name)`` / ``rec.keys()`` etc.;
    it is just a dict subclass registered in the method table.
    """


class Guards:
    """Guard callables bound to one :class:`Budget`."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget

    def step(self, n: int) -> None:
        self.budget.step(n)

    def enter(self) -> None:
        self.budget.enter()

    def leave(self) -> None:
        self.budget.leave()

    def iter(self, iterable: Iterable[Any]) -> Iterator[Any]:
        budget = self.budget
        for item in iterable:
            budget.step(1)
            yield item

    def list(self, gen: Iterable[Any]) -> list[Any]:
        out: list[Any] = []
        budget = self.budget
        for item in gen:
            budget.alloc(8 + size_of(item))
            out.append(item)
        return out

    def dict(self, gen: Iterable[tuple[Any, Any]]) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        budget = self.budget
        for key, value in gen:
            budget.alloc(24 + size_of(value))
            out[key] = value
        return out

    def gen(self, gen: Iterable[Any]) -> Iterator[Any]:
        return iter(gen)

    def binop(self, op: str, a: Any, b: Any) -> Any:
        self.budget.alloc(_predict_binop(op, a, b))
        return _BINOPS[op](a, b)

    def slice(self, lower: Any, upper: Any, step: Any) -> slice:
        return slice(lower, upper, step)

    def alloc(self, value: Any) -> Any:
        self.budget.alloc(size_of(value))
        return value

    def getattr(self, obj: Any, name: str) -> Any:
        if isinstance(obj, MathNamespace):
            if name in MATH_MEMBERS:
                return MATH_MEMBERS[name]
            raise ScriptRuntimeError("math has no such member", context={"name": name})
        allowed = METHOD_TABLE.get(type(obj))
        if allowed is None or name not in allowed:
            raise ScriptRuntimeError(
                "attribute not available in scripts",
                context={"type": type(obj).__name__, "attribute": name},
            )
        return getattr(obj, name)

    def attr(self, obj: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        method = self.getattr(obj, name)
        if isinstance(obj, str) and name in _GROWING_STR:
            self._predict_str(obj, name, args)
        elif isinstance(obj, list) and name in {"extend", "insert", "append"}:
            grow = len(args[0]) if name == "extend" and args and hasattr(args[0], "__len__") else 1
            if len(obj) + grow > MAX_SEQUENCE:
                raise ScriptMemoryLimitError("list too large", context={"length": len(obj) + grow})
            self.budget.alloc(8 * grow)
        if name == "sort" and kwargs.get("key") is not None:
            self.budget.step(len(obj))
        result = method(*args, **kwargs)
        if isinstance(result, (str, list, dict, tuple, bytes)) and result is not obj:
            self.budget.alloc(size_of(result))
        return result

    def _predict_str(self, s: str, name: str, args: tuple[Any, ...]) -> None:
        if name in {"center", "ljust", "rjust", "zfill"} and args and isinstance(args[0], int):
            if args[0] > MAX_SEQUENCE:
                raise ScriptMemoryLimitError("string too large", context={"length": args[0]})
        elif name == "replace" and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            hits = s.count(args[0]) if args[0] else len(s) + 1
            size = len(s) + hits * max(0, len(args[1]) - len(args[0]))
            if size > MAX_SEQUENCE:
                raise ScriptMemoryLimitError("string too large", context={"length": size})
        elif name == "join" and args:
            try:
                parts = list(args[0])
            except TypeError:
                return
            size = sum(len(p) if isinstance(p, str) else 0 for p in parts) + len(s) * max(0, len(parts) - 1)
            if size > MAX_SEQUENCE:
                raise ScriptMemoryLimitError("string too large", context={"length": size})


# ---------------------------------------------------------------------------
# builtins
# ---------------------------------------------------------------------------
def _safe_range(budget: Budget) -> Callable[..., range]:
    def srange(*args: int) -> range:
        for a in args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise ScriptRuntimeError("range() arguments must be integers")
        return range(*args)

    return srange


def _metered(budget: Budget, fn: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for a in args:
            ln = _length(a)
            if ln is not None:
                budget.step(max(1, ln // 16))
        result = fn(*args, **kwargs)
        if isinstance(result, (list, dict, tuple, str)):
            budget.alloc(size_of(result))
        return result

    wrapper.__name__ = getattr(fn, "__name__", "builtin")
    return wrapper


def _materialize(budget: Budget, ctor: Callable[[Any], Any]) -> Callable[..., Any]:
    def build(iterable: Any = ()) -> Any:
        if isinstance(iterable, Mapping) and ctor is dict:
            budget.alloc(size_of(iterable))
            return dict(iterable)
        items = []
        for item in iterable:
            budget.step(1)
            budget.alloc(8 + size_of(item))
            items.append(item)
        return ctor(items)

    build.__name__ = getattr(ctor, "__name__", "ctor")
    return build


SAFE_EXCEPTIONS: dict[str, type[BaseException]] = {
    name: getattr(__import__("builtins"), name)
    for name in (
        "Exception", "ArithmeticError", "LookupError", "ValueError", "TypeError", "KeyError",
        "IndexError", "ZeroDivisionError", "RuntimeError", "AssertionError", "OverflowError",
    )
}


def build_builtins(budget: Budget) -> dict[str, Any]:
    m = lambda fn: _metered(budget, fn)  # noqa: E731
    table: dict[str, Any] = {
        "abs": abs, "min": m(min), "max": m(max), "sum": m(sum), "len": len, "round": round,
        "int": int, "float": float, "str": str, "bool": bool, "repr": repr, "ord": ord, "chr": chr,
        "divmod": divmod, "pow": lambda a, b: Guards(budget).binop("**", a, b),
        "range": _safe_range(budget), "enumerate": enumerate, "zip": zip, "reversed": reversed,
        "sorted": m(sorted), "any": any, "all": all, "isinstance": isinstance,
        "list": _materialize(budget, list), "tuple": _materialize(budget, tuple), "dict": _materialize(budget, dict),
        "map": map, "filter": filter, "print": lambda *a, **k: None,
        "True": True, "False": False, "None": None,
    }
    table.update(SAFE_EXCEPTIONS)
    return table


def build_globals(budget: Budget, api: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fresh script globals: builtins, ``math``, guard hooks and host ``api``."""
    guards = Guards(budget)
    g: dict[str, Any] = {"__builtins__": build_builtins(budget), "math": MATH, "__name__": "sandbox"}
    for hook in ("step", "enter", "leave", "iter", "list", "dict", "gen", "binop", "slice", "alloc", "getattr", "attr"):
        g["_sbx_" + hook] = getattr(guards, hook)
    for name, value in (api or {}).items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ValueError(f"invalid script api name {name!r}")
        g[name] = value
    return g


__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_MEMORY",
    "DEFAULT_MAX_SECONDS",
    "DEFAULT_MAX_STEPS",
    "MATH",
    "MATH_MEMBERS",
    "METHOD_TABLE",
    "Budget",
    "Guards",
    "build_builtins",
    "build_globals",
    "size_of",
]
