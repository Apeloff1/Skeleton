#!/usr/bin/env python3
"""Fail-closed validation for cumulative masterplan overlay authority."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"machine/masterplan_overlay_registry.json"
MANDATORY={"advanced-ai-100","frontier-96","cs-300","learning-400-adversarial-400","psi-1000","ess-1000","competitive-200","game-builder-500"}

class OverlayUnionError(RuntimeError):
    pass

def _version_tuple(value: str) -> tuple[int,...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except Exception as exc:
        raise OverlayUnionError(f"invalid semantic version: {value!r}") from exc

def _get_path(obj: Any, dotted: str) -> Any:
    value=obj
    for part in dotted.split("."):
        if not isinstance(value,dict) or part not in value:
            raise KeyError(dotted)
        value=value[part]
    return value

def _check_semantics(oid: str, parsed: dict[str,Any], checks: list[dict[str,Any]]) -> list[str]:
    errors=[]
    for check in checks:
        path=str(check.get("path",""))
        kind=check.get("kind")
        expected=check.get("expected")
        try:
            value=_get_path(parsed,path)
        except KeyError:
            errors.append(f"{oid}: semantic path missing: {path}")
            continue
        if kind=="length":
            try:
                actual=len(value)
            except TypeError:
                errors.append(f"{oid}: semantic path is not sized: {path}")
                continue
            if actual!=expected:
                errors.append(f"{oid}: {path} length {actual} != {expected}")
        elif kind=="equals":
            if value!=expected:
                errors.append(f"{oid}: {path}={value!r} != {expected!r}")
        else:
            errors.append(f"{oid}: unknown semantic check kind {kind!r}")
    return errors

def validate(root: Path=ROOT, registry_path: Path|None=None) -> list[str]:
    errors: list[str]=[]
    registry_path=registry_path or (root/"machine/masterplan_overlay_registry.json")
    try:
        registry=json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse overlay registry: {exc}"]

    plan_path=root/registry["canonical_plan"]
    human_plan_path=root/registry["human_plan"]
    index_path=root/registry["human_index"]
    try:
        plan=json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse canonical plan: {exc}"]

    current=str(plan.get("plan_version","0.0.0"))
    minimum=str(registry.get("minimum_plan_version","0.0.0"))
    try:
        if _version_tuple(current)<_version_tuple(minimum):
            errors.append(f"plan_version regressed: {current} < {minimum}")
    except OverlayUnionError as exc:
        errors.append(str(exc))

    plan_serialized=json.dumps(plan,sort_keys=True)
    human_plan=human_plan_path.read_text(encoding="utf-8") if human_plan_path.is_file() else ""
    human_index=index_path.read_text(encoding="utf-8") if index_path.is_file() else ""

    seen=set()
    for overlay in registry.get("overlays",[]):
        oid=overlay.get("id")
        if not oid or oid in seen:
            errors.append(f"duplicate or missing overlay id: {oid!r}")
            continue
        seen.add(oid)
        authority=overlay.get("authority")
        if not isinstance(authority,str) or not authority:
            errors.append(f"{oid}: missing authority path")
            continue
        path=root/authority
        if not path.is_file():
            errors.append(f"{oid}: missing authority {authority}")
            continue
        size=path.stat().st_size
        minimum_bytes=int(overlay.get("min_bytes",1))
        if size<minimum_bytes:
            errors.append(f"{oid}: authority too small/empty: {authority} bytes={size} min={minimum_bytes}")
            continue
        try:
            parsed=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{oid}: authority is not valid JSON: {exc}")
            continue
        if not isinstance(parsed,dict) or not parsed:
            errors.append(f"{oid}: authority root must be a non-empty object")
            continue
        errors.extend(_check_semantics(oid,parsed,overlay.get("semantic_checks",[])))
        if authority not in plan_serialized:
            errors.append(f"{oid}: canonical plan does not reference {authority}")
        if authority not in human_plan and authority not in human_index:
            errors.append(f"{oid}: neither MASTER_PLAN nor MASTER_INDEX references {authority}")
        for companion in overlay.get("companions",[]):
            cpath=root/companion
            if not cpath.is_file():
                errors.append(f"{oid}: missing companion {companion}")
            elif cpath.stat().st_size==0:
                errors.append(f"{oid}: zero-byte companion {companion}")

    missing=sorted(MANDATORY-seen)
    unexpected=sorted(seen-MANDATORY)
    if missing:
        errors.append("registry missing mandatory overlays: "+", ".join(missing))
    if unexpected:
        errors.append("registry has unreviewed overlay ids: "+", ".join(unexpected))
    return errors

def main() -> int:
    errors=validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("masterplan overlay union: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
