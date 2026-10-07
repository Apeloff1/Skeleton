"""Plain-data values that may live in live-world components, resources and events.

Live-world state must be (a) deterministic to hash, (b) losslessly
serialisable to JSON for snapshots, and (c) safe to hand to sandboxed
scripts.  This module defines that value domain once:

* ``None``, ``bool``, ``int``, finite ``float``, ``str``, ``bytes``
* ``list`` / ``tuple`` of values
* ``dict`` with ``str`` keys

Anything else (objects, functions, sets, NaN/inf) is rejected, which is what
keeps host objects from leaking into script-visible state.

:func:`to_json` / :func:`from_json` form a tagged, lossless JSON mapping:
tuples, bytes and dicts whose keys could collide with a tag are wrapped, so
``from_json(json.loads(json.dumps(to_json(v)))) == v`` with identical types.
"""
from __future__ import annotations

import base64
import math
from typing import Any

from .errors import BoundsError, ValidationError

MAX_VALUE_DEPTH = 32
MAX_VALUE_ITEMS = 1_000_000
_TAG_TUPLE = "$t"
_TAG_BYTES = "$b"
_TAG_DICT = "$d"
_SCALARS = (str, int, float, bool, type(None))


class _Budget:
    __slots__ = ("remaining",)

    def __init__(self, items: int) -> None:
        self.remaining = items

    def take(self) -> None:
        self.remaining -= 1
        if self.remaining < 0:
            raise BoundsError("value exceeds item bound", context={"maximum": MAX_VALUE_ITEMS})


def check_value(value: Any, *, label: str = "value", max_items: int = MAX_VALUE_ITEMS) -> Any:
    """Validate ``value`` against the plain-data domain and return it."""
    _check(value, 0, _Budget(max_items), label)
    return value


def _check(value: Any, depth: int, budget: _Budget, label: str) -> None:
    if depth > MAX_VALUE_DEPTH:
        raise ValidationError(f"{label} nests too deeply", context={"maximum": MAX_VALUE_DEPTH})
    budget.take()
    kind = type(value)
    if kind is float:
        if not math.isfinite(value):
            raise ValidationError(f"{label} contains a non-finite float")
        return
    if kind in (str, int, bool, type(None), bytes):
        return
    if kind is list or kind is tuple:
        for item in value:
            _check(item, depth + 1, budget, label)
        return
    if kind is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValidationError(f"{label} has a non-string mapping key", context={"key_type": type(key).__name__})
            _check(item, depth + 1, budget, label)
        return
    raise ValidationError(f"{label} contains unsupported type", context={"type": kind.__name__})


def copy_value(value: Any) -> Any:
    """Fast structural copy for already-validated plain data."""
    kind = type(value)
    if kind in _SCALARS or kind is bytes:
        return value
    if kind is list:
        return [copy_value(v) for v in value]
    if kind is dict:
        return {k: copy_value(v) for k, v in value.items()}
    if kind is tuple:
        return tuple(copy_value(v) for v in value)
    raise ValidationError("copy_value received unsupported type", context={"type": kind.__name__})


def canonical_copy(value: Any) -> Any:
    """Structural copy with every mapping re-ordered by key.

    Stored mappings are kept in sorted-key order so that dict iteration order
    (observable by systems and scripts) is identical before and after a JSON
    snapshot round trip, which serialises with sorted keys.
    """
    kind = type(value)
    if kind in _SCALARS or kind is bytes:
        return value
    if kind is list:
        return [canonical_copy(v) for v in value]
    if kind is dict:
        return {k: canonical_copy(value[k]) for k in sorted(value)}
    if kind is tuple:
        return tuple(canonical_copy(v) for v in value)
    raise ValidationError("canonical_copy received unsupported type", context={"type": kind.__name__})


def freeze_value(value: Any) -> Any:
    """Checked canonical copy: validate then copy (use at trust boundaries)."""
    check_value(value)
    return canonical_copy(value)


def to_json(value: Any) -> Any:
    kind = type(value)
    if kind in _SCALARS:
        if kind is float and not math.isfinite(value):
            raise ValidationError("non-finite float is not serialisable")
        return value
    if kind is bytes:
        return {_TAG_BYTES: base64.b64encode(value).decode("ascii")}
    if kind is list:
        return [to_json(v) for v in value]
    if kind is tuple:
        return {_TAG_TUPLE: [to_json(v) for v in value]}
    if kind is dict:
        body = {k: to_json(v) for k, v in value.items()}
        if len(value) == 1 and next(iter(value)) in (_TAG_TUPLE, _TAG_BYTES, _TAG_DICT):
            return {_TAG_DICT: body}
        return body
    raise ValidationError("value is not serialisable", context={"type": kind.__name__})


def from_json(node: Any) -> Any:
    kind = type(node)
    if kind in _SCALARS:
        return node
    if kind is list:
        return [from_json(v) for v in node]
    if kind is dict:
        if len(node) == 1:
            (key, inner), = node.items()
            if key == _TAG_TUPLE:
                if type(inner) is not list:
                    raise ValidationError("malformed tuple tag")
                return tuple(from_json(v) for v in inner)
            if key == _TAG_BYTES:
                if type(inner) is not str:
                    raise ValidationError("malformed bytes tag")
                try:
                    return base64.b64decode(inner.encode("ascii"), validate=True)
                except (ValueError, UnicodeEncodeError) as exc:
                    raise ValidationError("malformed bytes payload") from exc
            if key == _TAG_DICT:
                if type(inner) is not dict:
                    raise ValidationError("malformed dict tag")
                return {k: from_json(v) for k, v in inner.items()}
        return {k: from_json(v) for k, v in node.items()}
    raise ValidationError("json node has unsupported type", context={"type": kind.__name__})


__all__ = ["MAX_VALUE_DEPTH", "MAX_VALUE_ITEMS", "canonical_copy", "check_value", "copy_value", "freeze_value", "from_json", "to_json"]
