from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import SchemaError

CASE_ID_RE = re.compile(r"^GFM-[A-Z]{2,8}-\d{2,3}$")
KNOWN_GATES = ("fps", "perf", "soak", "retention", "replay", "promotion")
SEVERITIES = ("sev1", "sev2", "sev3")


@dataclass(frozen=True)
class QualCase:
    id: str
    gate: str
    title: str
    todo_ref: str
    severity: str
    params: dict = field(default_factory=dict)
    requires_hardware: bool = False


def _req(doc: dict, key: str, typ: type, where: str) -> Any:
    if key not in doc:
        raise SchemaError(where, f"missing required field '{key}'")
    val = doc[key]
    if not isinstance(val, typ) or (typ is int and isinstance(val, bool)):
        raise SchemaError(where, f"field '{key}' must be {typ.__name__}")
    return val


def parse_case(doc: Any, where: str = "<case>") -> QualCase:
    if not isinstance(doc, dict):
        raise SchemaError(where, "case must be an object")
    allowed = {"id", "gate", "title", "todo_ref", "severity", "params", "requires_hardware"}
    extra = set(doc) - allowed
    if extra:
        raise SchemaError(where, f"unknown fields {sorted(extra)}")
    cid = _req(doc, "id", str, where)
    if not CASE_ID_RE.match(cid):
        raise SchemaError(where, f"id '{cid}' must match {CASE_ID_RE.pattern}")
    gate = _req(doc, "gate", str, where)
    if gate not in KNOWN_GATES:
        raise SchemaError(where, f"gate '{gate}' not in {KNOWN_GATES}")
    title = _req(doc, "title", str, where).strip()
    if not title:
        raise SchemaError(where, "title must be non-empty")
    todo_ref = _req(doc, "todo_ref", str, where)
    sev = _req(doc, "severity", str, where)
    if sev not in SEVERITIES:
        raise SchemaError(where, f"severity '{sev}' not in {SEVERITIES}")
    params = doc.get("params", {})
    if not isinstance(params, dict):
        raise SchemaError(where, "params must be an object")
    hw = doc.get("requires_hardware", False)
    if not isinstance(hw, bool):
        raise SchemaError(where, "requires_hardware must be boolean")
    from .gates import validate_params
    validate_params(gate, params, where)
    return QualCase(cid, gate, title, todo_ref, sev, params, hw)


def load_case(path: str | Path) -> QualCase:
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(str(p), f"invalid JSON: {exc.msg}") from exc
    return parse_case(doc, str(p))


def load_cases(directory: str | Path) -> list[QualCase]:
    cases = [load_case(p) for p in sorted(Path(directory).glob("*.json"))]
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            raise SchemaError(str(directory), f"duplicate case id {c.id}")
        seen.add(c.id)
    return cases
