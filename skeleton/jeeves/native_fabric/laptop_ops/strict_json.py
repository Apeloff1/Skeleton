"""Reject ambiguous, oversized or duplicate-key operator JSON before checks."""
from __future__ import annotations
import json
from .contracts import LaptopGateHold, canonical


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
