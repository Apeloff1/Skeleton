"""Gate evaluators. Each module exposes PARAMS (required param names -> type)
and evaluate(params, data) -> (reasons, metrics). Empty reasons means pass."""
from __future__ import annotations

from typing import Callable

from ..errors import SchemaError
from . import fps, perf, promotion, replay, retention, soak

_GATES = {m.NAME: m for m in (fps, perf, soak, retention, replay, promotion)}


def validate_params(gate: str, params: dict, where: str) -> None:
    mod = _GATES[gate]
    for key, typ in mod.PARAMS.items():
        if key not in params:
            raise SchemaError(where, f"gate '{gate}' requires param '{key}'")
        val = params[key]
        ok = isinstance(val, typ) and not isinstance(val, bool) if typ is not bool else isinstance(val, bool)
        if not ok:
            raise SchemaError(where, f"param '{key}' must be {getattr(typ, '__name__', typ)}")
    check: Callable | None = getattr(mod, "check_params", None)
    if check:
        msg = check(params)
        if msg:
            raise SchemaError(where, msg)


def evaluate(gate: str, params: dict, data: dict) -> tuple[list[str], dict]:
    return _GATES[gate].evaluate(params, data)
