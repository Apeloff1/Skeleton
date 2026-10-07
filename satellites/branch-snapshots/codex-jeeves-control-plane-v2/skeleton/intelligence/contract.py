"""Structured-output contracts — check, then repair, never guess.

Wave-4 SOTA (grammar/contract-constrained generation reliability): the
2026 pattern is validate → repair → revalidate, not "hope the model got
the shape right." This module is the contract side of the OUTPUT fault
class in ``resilience/faults.py``: a lightweight schema (no JSON-Schema
dependency) plus a repair pass that fixes what's mechanically fixable
(missing fields get defaults, type coercions, unknown keys dropped) and
reports what it can't.

Schema shape::

    {
        "name":     {"type": str,  "required": True},
        "count":    {"type": int,  "default": 0, "coerce": True},
        "tags":     {"type": list, "default": list},
        "metadata": {"type": dict, "required": False},
    }

Pure domain, deterministic, no model needed — the repair is rule-based.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ContractIssue:
    field: str
    problem: str                    # missing | wrong_type | unknown_key
    detail: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "problem": self.problem, "detail": self.detail}


@dataclass
class RepairResult:
    payload: Dict[str, Any]
    issues: List[ContractIssue]
    repaired: List[str]             # fields mechanically fixed
    ok: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload": self.payload,
            "issues": [i.to_dict() for i in self.issues],
            "repaired": self.repaired,
            "ok": self.ok,
        }


_COERCERS = {
    int: lambda v: int(float(v)),
    float: lambda v: float(v),
    str: lambda v: str(v),
    bool: lambda v: v if isinstance(v, bool) else str(v).lower() in {"1", "true", "yes", "on"},
    list: lambda v: list(v) if not isinstance(v, (str, bytes)) else [v],
    dict: lambda v: dict(v),
}


class Contract:
    """Validate and repair payloads against a lightweight field schema."""

    def __init__(self, schema: Mapping[str, Mapping[str, Any]], *,
                 strict_keys: bool = True) -> None:
        self.schema = {k: dict(v) for k, v in schema.items()}
        self.strict_keys = strict_keys

    def validate(self, payload: Mapping[str, Any]) -> List[ContractIssue]:
        issues: List[ContractIssue] = []
        for name, spec in self.schema.items():
            value = payload.get(name)
            if value is None:
                if spec.get("required") and "default" not in spec:
                    issues.append(ContractIssue(name, "missing", "required, no default"))
                continue
            want = spec.get("type")
            if want is not None and not isinstance(value, want):
                issues.append(ContractIssue(
                    name, "wrong_type",
                    f"want {want.__name__}, got {type(value).__name__}",
                ))
        if self.strict_keys:
            for key in payload:
                if key not in self.schema:
                    issues.append(ContractIssue(key, "unknown_key", ""))
        return issues

    def repair(self, payload: Mapping[str, Any]) -> RepairResult:
        """Fix what's mechanical; return the repaired payload + open issues."""
        out: Dict[str, Any] = dict(payload)
        repaired: List[str] = []

        # fill defaults for missing fields
        for name, spec in self.schema.items():
            if out.get(name) is None and "default" in spec:
                default = spec["default"]
                out[name] = default() if callable(default) else default
                repaired.append(name)

        # coerce wrong types where the spec allows
        for name, spec in self.schema.items():
            value = out.get(name)
            want = spec.get("type")
            if value is None or want is None or isinstance(value, want):
                continue
            if spec.get("coerce") and want in _COERCERS:
                try:
                    out[name] = _COERCERS[want](value)
                    repaired.append(name)
                except (TypeError, ValueError):
                    pass

        # drop unknown keys in strict mode
        if self.strict_keys:
            for key in list(out):
                if key not in self.schema:
                    del out[key]
                    repaired.append(key)

        issues = self.validate(out)
        return RepairResult(payload=out, issues=issues, repaired=repaired,
                            ok=not issues)
