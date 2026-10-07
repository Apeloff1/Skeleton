#!/usr/bin/env python3
"""Validate semantic cardinality of every cumulative frontier overlay."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"machine/masterplan_overlay_semantic_registry.json"
MANDATORY=("advanced-ai-100","frontier-96","cs-300","learning-400-adversarial-400","psi-1000","ess-1000","competitive-200","game-builder-500")

def _version_tuple(value: str) -> tuple[int,...]:
    return tuple(int(part) for part in value.split("."))

def _get_path(obj: Any,dotted: str) -> Any:
    value=obj
    for part in dotted.split("."):
        if not isinstance(value,dict) or part not in value:
            raise KeyError(dotted)
        value=value[part]
    return value

def _semantic_errors(oid: str,parsed: dict[str,Any],checks: list[dict[str,Any]]) -> list[str]:
    errors=[]
    for check in checks:
        path=str(check["path"]); kind=check["kind"]; expected=check["expected"]
        try:
            value=_get_path(parsed,path)
        except KeyError:
            errors.append(f"{oid}: missing semantic path {path}")
            continue
        if kind=="length":
            try: actual=len(value)
            except TypeError:
                errors.append(f"{oid}: {path} is not sized")
                continue
            if actual!=expected:
                errors.append(f"{oid}: {path} length {actual} != {expected}")
        elif kind=="equals":
            if value!=expected:
                errors.append(f"{oid}: {path}={value!r} != {expected!r}")
        else:
            errors.append(f"{oid}: unsupported semantic check {kind!r}")
    return errors

def validate(root: Path=ROOT,registry_path: Path|None=None) -> list[str]:
    errors=[]
    registry_path=registry_path or (root/"machine/masterplan_overlay_semantic_registry.json")
    try:
        registry=json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse semantic registry: {exc}"]
    try:
        plan=json.loads((root/registry["canonical_plan"]).read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse canonical plan: {exc}"]
    try:
        if _version_tuple(str(plan.get("plan_version","0.0.0"))) < _version_tuple(str(registry["minimum_plan_version"])):
            errors.append(f"plan_version regressed below {registry['minimum_plan_version']}")
    except Exception as exc:
        errors.append(f"invalid plan_version: {exc}")
    stack=plan.get("frontier_overlay_stack") or {}
    canonical={entry.get("id"):entry.get("authority") for entry in stack.get("overlays",[]) if isinstance(entry,dict)}
    ids=[entry.get("id") for entry in registry.get("overlays",[])]
    if tuple(ids)!=MANDATORY:
        errors.append(f"semantic registry overlay order/identity drifted: {ids}")
    for overlay in registry.get("overlays",[]):
        oid=overlay["id"]; authority=overlay["authority"]; path=root/authority
        if canonical.get(oid)!=authority:
            errors.append(f"{oid}: canonical stack authority drifted: {canonical.get(oid)!r} != {authority!r}")
            continue
        if not path.is_file():
            errors.append(f"{oid}: missing authority {authority}")
            continue
        size=path.stat().st_size
        if size<int(overlay.get("min_bytes",1)):
            errors.append(f"{oid}: authority truncated: bytes={size}")
            continue
        try:
            parsed=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{oid}: invalid JSON authority: {exc}")
            continue
        if not isinstance(parsed,dict) or not parsed:
            errors.append(f"{oid}: authority root must be a non-empty object")
            continue
        errors.extend(_semantic_errors(oid,parsed,overlay.get("semantic_checks",[])))
    return errors

def main() -> int:
    errors=validate()
    if errors:
        for error in errors: print("ERROR:",error)
        return 1
    print("masterplan overlay semantics: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
