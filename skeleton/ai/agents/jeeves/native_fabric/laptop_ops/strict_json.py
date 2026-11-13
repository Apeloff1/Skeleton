"""Reject ambiguous, oversized or duplicate-key operator JSON before checks."""
from __future__ import annotations
import json
from .contracts import LaptopGateHold, canonical


def _validate_scalar_tree(value: object) -> None:
    """Bound nesting and reject ill-formed Unicode even when JSON escapes it.

    JSON permits escaped surrogate code points, but they are not valid
    Unicode scalar values. Escaping them back to ASCII must not turn them
    into acceptable model/source evidence. Iteration avoids recursively
    walking attacker-controlled input.
    """
    stack: list[tuple[object, int]] = [(value, 0)]
    visited = 0
    while stack:
        current, depth = stack.pop()
        visited += 1
        if depth > 48 or visited > 4096:
            raise LaptopGateHold("evidence depth or element budget exceeded")
        if type(current) is str:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in current):
                raise LaptopGateHold("non-scalar Unicode evidence is forbidden")
        elif type(current) is dict:
            for key, child in current.items():
                if type(key) is not str:
                    raise LaptopGateHold("evidence object key must be text")
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif type(current) is list:
            stack.extend((child, depth + 1) for child in current)


def decode(raw: bytes, *, maximum: int = 65536) -> object:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise LaptopGateHold("bounded UTF-8 JSON evidence required")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise LaptopGateHold("duplicate evidence JSON key")
            out[key] = value
        return out

    def reject_constant(value):
        raise LaptopGateHold("nonfinite numeric evidence is forbidden")

    try:
        result = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=pairs,
                            parse_constant=reject_constant)
        _validate_scalar_tree(result)
        canonical(result, maximum=maximum)
        return result
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise LaptopGateHold("invalid strict evidence encoding") from exc


def record(raw: bytes) -> dict[str, object]:
    value = decode(raw)
    if type(value) is not dict or set(value) != {"schema", "domain", "evidence"}:
        raise LaptopGateHold("unknown or missing top-level evidence fields")
    if value["schema"] != "jeeves.laptop_ops.evidence.v1":
        raise LaptopGateHold("unsupported operator evidence version")
    if type(value["evidence"]) is not dict:
        raise LaptopGateHold("typed stage mapping required")
    return value
