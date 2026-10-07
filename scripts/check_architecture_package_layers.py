#!/usr/bin/env python3
"""Validate masterplan-bound Python package layers and import direction."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/python_package_layers.json")
MASTER_PLAN = Path("machine/ai_master_plan.json")


class PackageLayerError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackageLayerError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise PackageLayerError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackageLayerError(f"{relative} must contain an object")
    return data


def _normalize(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise PackageLayerError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PackageLayerError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise PackageLayerError(f"non-canonical repository path: {value!r}")
    return value


def _python_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        return (path,) if path.suffix == ".py" else ()
    if not path.is_dir():
        return ()
    return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)


def _module_from_path(relative: str) -> str | None:
    if not relative.startswith("skeleton/") or not relative.endswith(".py"):
        return None
    parts = list(PurePosixPath(relative).parts)
    parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _path_prefix_to_module(prefix: str) -> str:
    if prefix.endswith(".py"):
        mod = _module_from_path(prefix)
        if mod is None:
            raise PackageLayerError(f"cannot derive module from {prefix}")
        return mod
    return prefix.replace("/", ".")


def _classify_module(module: str, prefixes: list[tuple[str, str]]) -> str | None:
    matches = [
        (prefix, layer_id)
        for prefix, layer_id in prefixes
        if module == prefix or module.startswith(prefix + ".")
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def _absolute_imports(tree: ast.AST) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module, node.lineno))
    return imports


def _has_path_hack(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"append", "insert", "extend"}:
                value = func.value
                if (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "sys"
                    and value.attr == "path"
                ):
                    return True
        if isinstance(node, ast.Subscript):
            value = node.value
            if isinstance(value, ast.Attribute):
                if isinstance(value.value, ast.Name) and value.value.id == "os" and value.attr == "environ":
                    sl = node.slice
                    if isinstance(sl, ast.Constant) and sl.value == "PYTHONPATH":
                        return True
    return False


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load(root, MANIFEST)
    master = _load(root, MASTER_PLAN)

    if manifest.get("status") != "active":
        raise PackageLayerError("package layer manifest must be active")

    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    bindings = manifest.get("masterplan_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise PackageLayerError("masterplan_bindings must be non-empty")
    seen_bindings: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise PackageLayerError("masterplan binding must be an object")
        ref = binding.get("volume_ref")
        if ref in seen_bindings:
            raise PackageLayerError(f"duplicate masterplan binding: {ref}")
        seen_bindings.add(ref)
        volume = volumes.get(ref)
        if not isinstance(volume, dict):
            raise PackageLayerError(f"unknown masterplan volume: {ref}")
        if binding.get("title") != volume.get("title"):
            raise PackageLayerError(f"masterplan title drift for {ref}")
        gaps = binding.get("required_gap_texts")
        if not isinstance(gaps, list) or not gaps:
            raise PackageLayerError(f"{ref} requires gap bindings")
        for gap in gaps:
            if gap not in volume.get("gaps", []):
                raise PackageLayerError(f"masterplan gap drift for {ref}: {gap!r}")
    if seen_bindings != {"VOL-052", "VOL-053"}:
        raise PackageLayerError("package layers must remain bound to VOL-052 and VOL-053")

    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        raise PackageLayerError("policy must be an object")
    if policy.get("unclassified_internal_imports") != "allowed_but_reported":
        raise PackageLayerError("unclassified internal imports must remain report-only until coverage expands")

    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        raise PackageLayerError("layers must be non-empty")

    ids: set[str] = set()
    orders: set[int] = set()
    path_owners: dict[str, str] = {}
    prefixes: list[tuple[str, str]] = []
    layer_by_id: dict[str, dict[str, Any]] = {}

    for layer in layers:
        if not isinstance(layer, dict):
            raise PackageLayerError("layer must be an object")
        layer_id = layer.get("id")
        order = layer.get("order")
        if not isinstance(layer_id, str) or not layer_id:
            raise PackageLayerError("layer id must be non-empty")
        if layer_id in ids:
            raise PackageLayerError(f"duplicate layer id: {layer_id}")
        ids.add(layer_id)
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise PackageLayerError(f"{layer_id} has invalid order")
        if order in orders:
            raise PackageLayerError(f"duplicate layer order: {order}")
        orders.add(order)
        layer_by_id[layer_id] = layer

        paths = layer.get("paths")
        if not isinstance(paths, list) or not paths:
            raise PackageLayerError(f"{layer_id} paths must be non-empty")
        for raw in paths:
            rel = _normalize(raw)
            if rel in path_owners:
                raise PackageLayerError(f"package path {rel} owned by multiple layers")
            path_owners[rel] = layer_id
            target = root / rel
            if not target.exists():
                raise PackageLayerError(f"{layer_id} package path missing: {rel}")
            if not rel.startswith("skeleton/"):
                raise PackageLayerError(f"{layer_id} path must remain under skeleton/: {rel}")
            prefixes.append((_path_prefix_to_module(rel), layer_id))

    for layer_id, layer in layer_by_id.items():
        allowed = layer.get("allowed_layer_ids")
        if not isinstance(allowed, list) or layer_id not in allowed:
            raise PackageLayerError(f"{layer_id} must allow itself")
        if len(allowed) != len(set(allowed)):
            raise PackageLayerError(f"{layer_id} allowed_layer_ids contains duplicates")
        unknown = sorted(set(allowed) - ids)
        if unknown:
            raise PackageLayerError(f"{layer_id} references unknown layers: {unknown}")
        order = layer["order"]
        illegal = sorted(
            dep for dep in allowed if layer_by_id[dep]["order"] > order
        )
        if illegal:
            raise PackageLayerError(f"{layer_id} allows upward dependencies: {illegal}")

    violations: list[str] = []
    unclassified_internal: set[str] = set()
    checked_files = 0

    # Declared paths may overlap intentionally. A specific module can override
    # a broader package declaration; longest module-prefix classification wins
    # for both source and target edges.
    source_files: set[Path] = set()
    for rel in path_owners:
        source_files.update(_python_files(root / rel))

    for path in sorted(source_files):
        relative = path.relative_to(root).as_posix()
        source_module = _module_from_path(relative)
        if source_module is None:
            continue
        source_layer_id = _classify_module(source_module, prefixes)
        if source_layer_id is None:
            raise PackageLayerError(
                f"classified source file has no layer after longest-prefix resolution: {relative}"
            )
        source_layer = layer_by_id[source_layer_id]
        checked_files += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"{relative}: cannot parse: {type(exc).__name__}")
            continue

        if _has_path_hack(tree):
            violations.append(f"{relative}: runtime sys.path/PYTHONPATH mutation is forbidden")

        forbidden_external = set(source_layer.get("forbidden_external_roots", []))
        for module, line in _absolute_imports(tree):
            top = module.split(".", 1)[0]
            if top in forbidden_external:
                violations.append(
                    f"{relative}:{line}: {source_layer_id} imports forbidden external root {top}"
                )
            if top != "skeleton":
                continue
            target_layer_id = _classify_module(module, prefixes)
            if target_layer_id is None:
                unclassified_internal.add(module)
                continue
            if target_layer_id not in source_layer["allowed_layer_ids"]:
                violations.append(
                    f"{relative}:{line}: upward import {module} "
                    f"({source_layer_id} -> {target_layer_id})"
                )

    if violations:
        raise PackageLayerError("package layer violations:\n- " + "\n- ".join(sorted(violations)))

    return {
        "status": "valid",
        "layer_count": len(layers),
        "checked_files": checked_files,
        "classified_path_count": len(path_owners),
        "unclassified_internal_imports": sorted(unclassified_internal),
        "masterplan_bindings": sorted(seen_bindings),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except PackageLayerError as exc:
        print(f"python package layers: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "python package layers: OK "
            f"({result['layer_count']} layers, {result['checked_files']} files)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
