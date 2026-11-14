"""Bounded strict JSON boundary for offline local inference telemetry.

Reject ambiguous duplicate keys, nonfinite values, excessive nesting and
large decoded structures before any profile or admission state is modified.
No network access, provider credential handling or device qualification.
"""
from __future__ import annotations

import json
import math


def load_strict_telemetry_json(
    raw: bytes, *, max_bytes: int, max_depth: int = 32,
    max_nodes: int = 200_000,
) -> object:
    if type(raw) is not bytes or type(max_bytes) is not int or not 1 <= max_bytes <= 1 << 24:
        raise ValueError("bounded UTF-8 telemetry input required")
    if len(raw) > max_bytes:
        raise ValueError("telemetry input exceeds byte budget")
    if type(max_depth) is not int or not 1 <= max_depth <= 128:
        raise ValueError("invalid JSON depth limit")
    if type(max_nodes) is not int or not 1 <= max_nodes <= 1_000_000:
        raise ValueError("invalid JSON node limit")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate telemetry JSON key")
            result[key] = value
        return result

    def finite(value: str) -> float:
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError("invalid telemetry number") from exc
        if not math.isfinite(number):
            raise ValueError("nonfinite telemetry number")
        return number

    def constant(_: str) -> object:
        raise ValueError("nonfinite telemetry constant")

    try:
        root = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique,
            parse_constant=constant,
            parse_float=finite,
        )
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid or deeply nested telemetry JSON") from exc

    stack: list[tuple[object, int]] = [(root, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("telemetry JSON exceeds structure budget")
        if type(item) is dict:
            stack.extend((value, depth + 1) for value in item.values())
        elif type(item) is list:
            stack.extend((value, depth + 1) for value in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite telemetry number")
    return root


__all__ = ["load_strict_telemetry_json"]
