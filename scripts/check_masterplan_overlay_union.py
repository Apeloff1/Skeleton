#!/usr/bin/env python3
"""Fail-closed validation for cumulative masterplan overlay authority."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"machine/masterplan_overlay_registry.json"

class OverlayUnionError(RuntimeError):
    pass

def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except Exception as exc:
        raise OverlayUnionError(f"invalid semantic version: {value!r}") from exc

def validate() -> list[str]:
    errors: list[str]=[]
    try:
        registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse overlay registry: {exc}"]

    plan_path=ROOT/registry["canonical_plan"]
    human_plan_path=ROOT/registry["human_plan"]
    index_path=ROOT/registry["human_index"]
    try:
        plan=json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse canonical plan: {exc}"]

    current=str(plan.get("plan_version","0.0.0"))
    minimum=str(registry.get("minimum_plan_version","0.0.0"))
    if _version_tuple(current) < _version_tuple(minimum):
        errors.append(f"plan_version regressed: {current} < {minimum}")

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
        path=ROOT/authority
        if not path.is_file():
            errors.append(f"{oid}: missing authority {authority}")
            continue
        size=path.stat().st_size
        minimum_bytes=int(overlay.get("min_bytes",1))
        if size < minimum_bytes:
            errors.append(f"{oid}: authority too small/empty: {authority} bytes={size} min={minimum_bytes}")
            continue
        try:
            parsed=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{oid}: authority is not valid JSON: {exc}")
            continue
        if not isinstance(parsed,dict) or not parsed:
            errors.append(f"{oid}: authority root must be a non-empty object")
        if authority not in plan_serialized:
            errors.append(f"{oid}: canonical plan does not reference {authority}")
        if authority not in human_plan and authority not in human_index:
            errors.append(f"{oid}: neither MASTER_PLAN nor MASTER_INDEX references {authority}")
        for companion in overlay.get("companions",[]):
            cpath=ROOT/companion
            if not cpath.is_file():
                errors.append(f"{oid}: missing companion {companion}")
            elif cpath.stat().st_size == 0:
                errors.append(f"{oid}: zero-byte companion {companion}")

    expected={"advanced-ai-100","frontier-96","cs-300","learning-400-adversarial-400","psi-1000","ess-1000","competitive-200","game-builder-500"}
    missing=sorted(expected-seen)
    if missing:
        errors.append("registry missing mandatory overlays: "+", ".join(missing))
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
