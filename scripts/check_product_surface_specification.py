#!/usr/bin/env python3
"""Fail closed when a user-visible surface escapes the product specification.

The registry is an exact-head inventory.  It does not claim that a screen was
runtime-qualified: it binds every exposed Expo route and Hub modal to its
owner, interaction/backend map, state semantics, accessibility evidence and
source digest so incomplete surfaces cannot be added silently.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "machine/product_surface_specification.json"
HUB = ROOT / "frontend/app/hub.tsx"
REQUIRED_STATES = ("loading", "empty", "error", "retry", "success", "unavailable")
LAZY = re.compile(
    r"const\s+(?P<name>[A-Za-z][A-Za-z0-9_]*)\s*=\s*lazyNamed\(\(\)\s*=>\s*"
    r"import\(['\"](?P<target>\.\.[^'\"]+)['\"]\),\s*['\"][^'\"]+['\"]\)"
)
BACKEND = re.compile(r"['\"](?P<path>/api(?:/[^'\"?`$ {}]*)?)")
NAVIGATION = re.compile(r"(?:router\.(?:push|replace)|href)\s*\(?\s*['\"](?P<path>/[A-Za-z0-9_./-]+)")
INTERACTION = re.compile(r"\b(?:onPress|onLongPress|onSubmitEditing|onValueChange|onChangeText)\s*=")
ACCESSIBILITY = re.compile(r"\b(?:accessibility(?:Label|Role|Hint|State)|testID)\s*=")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route_id(path: Path) -> str:
    relative = path.relative_to(ROOT / "frontend/app").with_suffix("")
    return "route:" + "/".join(relative.parts)


def discover(root: Path = ROOT) -> dict[str, dict[str, str]]:
    surfaces: dict[str, dict[str, str]] = {}
    app = root / "frontend/app"
    for path in sorted(app.rglob("*.tsx")):
        if path.name == "_layout.tsx":
            continue
        sid = _route_id(path) if root == ROOT else "route:" + "/".join(path.relative_to(app).with_suffix("").parts)
        surfaces[sid] = {"kind": "expo_route", "source": path.relative_to(root).as_posix()}

    hub = root / "frontend/app/hub.tsx"
    if hub.is_file():
        text = hub.read_text(encoding="utf-8")
        for match in LAZY.finditer(text):
            name, target = match.group("name"), match.group("target")
            # A declaration alone is not a surfaced modal. Require JSX use.
            if len(re.findall(rf"<{re.escape(name)}\b", text)) == 0:
                continue
            source = (hub.parent / target).resolve()
            candidates = [source, Path(str(source) + ".tsx"), source / "index.tsx"]
            resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
            if resolved is None or root.resolve() not in resolved.parents:
                continue
            surfaces[f"modal:{name}"] = {
                "kind": "hub_modal",
                "source": resolved.relative_to(root).as_posix(),
            }
    return surfaces


def inspect_source(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "source_sha256": _sha(path),
        "interaction_count": len(INTERACTION.findall(text)),
        "backend_surfaces": sorted(set(match.group("path") for match in BACKEND.finditer(text))),
        "navigation_targets": sorted(set(match.group("path") for match in NAVIGATION.finditer(text))),
        "accessibility_signal_count": len(ACCESSIBILITY.findall(text)),
    }


def _delegated_backend_paths(
    root: Path, source: Path, source_text: str,
    row: dict[str, Any], sid: str, errors: list[str],
) -> set[str]:
    """Bind delegated API routes to directly imported, source-digested helpers.

    No runtime import, eval, glob discovery, or implicit source delegation.
    Undeclared helper paths remain absent from this static proof.
    """
    declared = row.get("backend_delegates", [])
    if not isinstance(declared, list) or len(declared) > 4:
        errors.append(f"{sid}: malformed bounded backend delegation inventory")
        return set()
    observed: set[str] = set()
    visited: set[str] = set()
    evidence = row.get("validation_evidence") or []
    for item in declared:
        if not isinstance(item, dict) or set(item) != {"source", "source_sha256"}:
            errors.append(f"{sid}: invalid backend delegation record")
            continue
        relative = item["source"]
        digest = item["source_sha256"]
        if (
            not isinstance(relative, str)
            or not relative.startswith("frontend/src/features/")
            or not relative.endswith(".ts")
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or relative in visited
            or not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
        ):
            errors.append(f"{sid}: invalid backend delegation path or digest")
            continue
        visited.add(relative)
        candidate = root / relative
        if not candidate.is_file() or candidate.is_symlink():
            errors.append(f"{sid}: delegated backend source missing or unsafe: {relative}")
            continue
        module = os.path.relpath(candidate.with_suffix(""), source.parent).replace(os.sep, "/")
        if not module.startswith("."):
            module = "./" + module
        if not re.search(r"\bfrom\s+['\"]" + re.escape(module) + r"['\"]", source_text):
            errors.append(f"{sid}: delegated backend source not statically imported: {relative}")
            continue
        if not isinstance(evidence, list) or relative not in evidence:
            errors.append(f"{sid}: delegated backend lacks explicit source evidence: {relative}")
        payload = candidate.read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            errors.append(f"{sid}: delegated backend source_sha256 drift: {relative}")
        paths = {match.group("path") for match in BACKEND.finditer(payload.decode("utf-8"))}
        if not paths:
            errors.append(f"{sid}: declared backend helper exposes no literal API paths: {relative}")
        observed.update(paths)
    return observed


def _load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    registry_path = root / "machine/product_surface_specification.json"
    try:
        payload = _load_registry(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"surface registry unreadable: {exc}"]
    if payload.get("schema_version") != "skeleton.product-surface-specification.v1":
        errors.append("surface registry schema drift")
    if payload.get("runtime_ready_claim") is not False:
        errors.append("static surface registry must not claim runtime readiness")
    if tuple(payload.get("required_states") or ()) != REQUIRED_STATES:
        errors.append("required surface state inventory drift")

    discovered = discover(root)
    rows = payload.get("surfaces")
    if not isinstance(rows, list):
        return errors + ["surface registry entries missing"]
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("surface_id"), str):
            errors.append("malformed surface entry")
            continue
        sid = row["surface_id"]
        if sid in indexed:
            errors.append(f"duplicate surface: {sid}")
        indexed[sid] = row
    for sid in sorted(set(discovered) - set(indexed)):
        errors.append(f"unregistered visible surface: {sid}")
    for sid in sorted(set(indexed) - set(discovered)):
        errors.append(f"stale registered surface: {sid}")

    for sid in sorted(set(indexed) & set(discovered)):
        row, actual = indexed[sid], discovered[sid]
        if row.get("kind") != actual["kind"] or row.get("source") != actual["source"]:
            errors.append(f"{sid}: source identity drift")
            continue
        source = root / actual["source"]
        observed = inspect_source(source)
        delegated = _delegated_backend_paths(
            root, source, source.read_text(encoding="utf-8"), row, sid, errors,
        )
        observed["backend_surfaces"] = sorted(set(observed["backend_surfaces"]) | delegated)
        for key in ("source_sha256", "interaction_count", "backend_surfaces", "navigation_targets", "accessibility_signal_count"):
            if row.get(key) != observed[key]:
                errors.append(f"{sid}: {key} drift")
        if row.get("owner") != "frontend/product-shell":
            errors.append(f"{sid}: invalid owner")
        if row.get("maturity") not in {"full_spec_target", "operational_candidate", "informational"}:
            errors.append(f"{sid}: maturity missing")
        if row.get("runtime_ready_claim") is not False:
            errors.append(f"{sid}: static entry claims runtime readiness")
        states = row.get("states")
        if not isinstance(states, dict) or tuple(states) != REQUIRED_STATES or any(not isinstance(states.get(key), str) or not states[key].strip() for key in REQUIRED_STATES):
            errors.append(f"{sid}: incomplete state contract")
        if observed["interaction_count"] and row.get("action_mode") != "interactive":
            errors.append(f"{sid}: interactive surface not mapped as interactive")
        if not observed["interaction_count"] and row.get("action_mode") != "informational":
            errors.append(f"{sid}: informational surface action mode drift")
        if row.get("backend_mode") not in {"api", "local_or_navigation"}:
            errors.append(f"{sid}: backend mode missing")
        if bool(observed["backend_surfaces"]) != (row.get("backend_mode") == "api"):
            errors.append(f"{sid}: backend mapping disagrees with source")
        evidence = row.get("validation_evidence")
        if not isinstance(evidence, list) or actual["source"] not in evidence or "scripts/check_product_surface_specification.py" not in evidence:
            errors.append(f"{sid}: validation evidence incomplete")
        if observed["interaction_count"] and observed["accessibility_signal_count"] == 0:
            # Existing debt remains visible without forging runtime qualification.
            if row.get("maturity") != "full_spec_target":
                errors.append(f"{sid}: interactive surface lacks accessibility evidence")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"product-surface-specification: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors[:120]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    routes = sum(row["kind"] == "expo_route" for row in payload["surfaces"])
    modals = sum(row["kind"] == "hub_modal" for row in payload["surfaces"])
    print(f"product-surface-specification: OK ({routes} Expo routes, {modals} surfaced Hub modals, {len(payload['surfaces'])} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
