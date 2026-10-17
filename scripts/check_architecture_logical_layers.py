#!/usr/bin/env python3
"""Fail closed when selected packages violate domain/application/infrastructure/interface."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/logical_layers.json")
LAYER_ORDER = ("domain", "infrastructure", "application", "interface")


class LogicalLayerError(RuntimeError):
    pass


def _load(root: Path) -> dict[str, Any]:
    path = root / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LogicalLayerError(f"missing required file: {MANIFEST}") from exc
    except json.JSONDecodeError as exc:
        raise LogicalLayerError(f"invalid JSON in {MANIFEST}: {exc}") from exc
    if not isinstance(data, dict):
        raise LogicalLayerError(f"{MANIFEST} must contain an object")
    return data


def _normalize(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise LogicalLayerError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise LogicalLayerError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise LogicalLayerError(f"non-canonical repository path: {value!r}")
    return value


def _python_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        return (path,) if path.suffix == ".py" else ()
    if not path.is_dir():
        return ()
    return sorted(item for item in path.rglob("*.py") if "__pycache__" not in item.parts)


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
        module = _module_from_path(prefix)
        if module is None:
            raise LogicalLayerError(f"cannot derive module from {prefix}")
        return module
    return prefix.replace("/", ".")


def _classify(module: str, prefixes: list[tuple[str, str]]) -> str | None:
    matches = [
        (prefix, layer_id)
        for prefix, layer_id in prefixes
        if module == prefix or module.startswith(prefix + ".")
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def _package_name(relative: str) -> str:
    """Package used to resolve relative imports in ``relative``."""
    module = _module_from_path(relative)
    if module is None:
        return ""
    if relative.endswith("/__init__.py"):
        return module
    if "." not in module:
        return ""
    return module.rsplit(".", 1)[0]


def _resolve_relative(package: str, level: int, module: str | None) -> str | None:
    if level < 1:
        return None
    parts = [part for part in package.split(".") if part]
    drop = level - 1
    if drop > len(parts):
        return None
    base = parts[: len(parts) - drop]
    if module:
        base.extend(part for part in module.split(".") if part)
    if not base:
        return None
    return ".".join(base)


def _string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_string(node: ast.Call, index: int, keyword: str) -> str | None:
    if len(node.args) > index:
        return _string_constant(node.args[index])
    for item in node.keywords:
        if item.arg == keyword:
            return _string_constant(item.value)
    return None


def _dynamic_importer_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to the importlib module and to importlib.import_module."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "importlib":
                    modules.add(bound)
                elif alias.name == "importlib.import_module":
                    functions.add(alias.asname or "import_module")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module in {"importlib", "importlib.machinery"}
        ):
            for alias in node.names:
                if alias.name == "import_module":
                    functions.add(alias.asname or alias.name)
    return modules, functions


def _dynamic_import_module(
    node: ast.Call,
    *,
    importlib_modules: set[str],
    import_module_names: set[str],
    package: str,
) -> str | None:
    func = node.func
    is_import_module = False
    is_builtin = False
    if isinstance(func, ast.Name):
        if func.id == "__import__":
            is_builtin = True
        elif func.id in import_module_names:
            is_import_module = True
    elif (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id in importlib_modules
    ):
        is_import_module = True
    if not is_import_module and not is_builtin:
        return None
    raw = _call_string(node, 0, "name")
    if raw is None or not raw:
        return None
    if not raw.startswith("."):
        return raw
    if not is_import_module:
        return None
    anchor = _call_string(node, 1, "package") or package
    level = len(raw) - len(raw.lstrip("."))
    remainder = raw[level:] or None
    return _resolve_relative(anchor, level, remainder)


def _layer_imports(tree: ast.AST, relative: str) -> tuple[list[tuple[str, int]], list[str]]:
    """Return classified import targets and local resolution failures.

    Absolute imports, ``from skeleton import name`` (as ``skeleton.name``),
    relative imports that climb into another package (level >= 2), and
    string literals passed to ``importlib.import_module`` or ``__import__``
    are visible. A level-1 relative import stays inside the current package.
    Non-literal dynamic targets are not guessed.
    """
    package = _package_name(relative)
    importlib_modules, import_module_names = _dynamic_importer_names(tree)
    imports: list[tuple[str, int]] = []
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                if node.module == "skeleton":
                    if any(alias.name == "*" for alias in node.names):
                        failures.append(
                            f"{relative}:{node.lineno}: star import from skeleton hides the target layer"
                        )
                    imports.extend(
                        (f"skeleton.{alias.name}", node.lineno)
                        for alias in node.names
                        if alias.name != "*"
                    )
                else:
                    imports.append((node.module, node.lineno))
                continue
            if node.level < 2:
                continue
            if node.module:
                resolved = _resolve_relative(package, node.level, node.module)
                if resolved is None:
                    failures.append(
                        f"{relative}:{node.lineno}: relative import climbs out of the package graph"
                    )
                else:
                    imports.append((resolved, node.lineno))
                continue
            if any(alias.name == "*" for alias in node.names):
                failures.append(
                    f"{relative}:{node.lineno}: star relative import hides the target layer"
                )
            parent = _resolve_relative(package, node.level, None)
            if parent is None:
                failures.append(
                    f"{relative}:{node.lineno}: relative import climbs out of the package graph"
                )
                continue
            imports.extend(
                (f"{parent}.{alias.name}", node.lineno)
                for alias in node.names
                if alias.name != "*"
            )
            continue
        if isinstance(node, ast.Call):
            resolved = _dynamic_import_module(
                node,
                importlib_modules=importlib_modules,
                import_module_names=import_module_names,
                package=package,
            )
            if resolved:
                imports.append((resolved, node.lineno))
    return imports, failures


def _has_path_hack(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if func.attr in {"append", "insert", "extend"}:
                value = func.value
                if (
                    isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "sys"
                    and value.attr == "path"
                ):
                    return True
    return False


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load(root)
    if manifest.get("schema_version") != "skeleton.architecture.logical_layers.v1":
        raise LogicalLayerError("logical layer schema_version mismatch")
    if manifest.get("status") != "active":
        raise LogicalLayerError("logical layer manifest must be active")

    layers = manifest.get("layers")
    if not isinstance(layers, list) or [item.get("id") for item in layers] != list(LAYER_ORDER):
        raise LogicalLayerError("layers must be domain, infrastructure, application, interface")

    layer_by_id: dict[str, dict[str, Any]] = {}
    prefixes: list[tuple[str, str]] = []
    path_owners: dict[str, str] = {}
    for expected_order, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise LogicalLayerError("layer must be an object")
        layer_id = layer.get("id")
        if layer.get("order") != expected_order:
            raise LogicalLayerError(f"{layer_id} order must be {expected_order}")
        paths = layer.get("paths")
        if not isinstance(paths, list) or not paths:
            raise LogicalLayerError(f"{layer_id} paths must be non-empty")
        forbidden = layer.get("forbidden_external_roots")
        if not isinstance(forbidden, list) or any(not isinstance(item, str) or not item for item in forbidden):
            raise LogicalLayerError(f"{layer_id} forbidden_external_roots must be a list of names")
        layer_by_id[str(layer_id)] = layer
        for raw in paths:
            rel = _normalize(raw)
            if rel in path_owners:
                raise LogicalLayerError(f"package path {rel} owned by multiple layers")
            if not rel.startswith("skeleton/"):
                raise LogicalLayerError(f"{layer_id} path must stay under skeleton/: {rel}")
            if not (root / rel).exists():
                raise LogicalLayerError(f"{layer_id} package path missing: {rel}")
            path_owners[rel] = str(layer_id)
            prefixes.append((_path_prefix_to_module(rel), str(layer_id)))

    declared: set[tuple[str, str]] = set()
    raw_edges = manifest.get("known_upward_edges")
    if not isinstance(raw_edges, list):
        raise LogicalLayerError("known_upward_edges must be a list")
    for item in raw_edges:
        if not isinstance(item, dict):
            raise LogicalLayerError("known upward edge must be an object")
        source = _normalize(item.get("source"))
        module = item.get("module")
        if not isinstance(module, str) or not module.startswith("skeleton."):
            raise LogicalLayerError(f"known upward edge has invalid module: {module!r}")
        edge = (source, module)
        if edge in declared:
            raise LogicalLayerError(f"duplicate known upward edge: {source} -> {module}")
        if not (root / source).is_file():
            raise LogicalLayerError(f"known upward edge source missing: {source}")
        declared.add(edge)

    found: set[tuple[str, str]] = set()
    violations: list[str] = []
    unclassified: set[str] = set()
    checked = 0
    files: set[Path] = set()
    for rel in path_owners:
        files.update(_python_files(root / rel))

    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        source_module = _module_from_path(relative)
        if source_module is None:
            continue
        source_layer_id = _classify(source_module, prefixes)
        if source_layer_id is None:
            raise LogicalLayerError(f"classified file lost its layer: {relative}")
        source_layer = layer_by_id[source_layer_id]
        checked += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"{relative}: cannot parse: {type(exc).__name__}")
            continue
        if _has_path_hack(tree):
            violations.append(f"{relative}: runtime sys.path mutation is forbidden")
        imported, import_failures = _layer_imports(tree, relative)
        violations.extend(import_failures)
        forbidden = set(source_layer.get("forbidden_external_roots", []))
        for module, line in imported:
            top = module.split(".", 1)[0]
            if top in forbidden:
                violations.append(
                    f"{relative}:{line}: {source_layer_id} imports forbidden external root {top}"
                )
            if top != "skeleton":
                continue
            target_layer_id = _classify(module, prefixes)
            if target_layer_id is None:
                unclassified.add(module)
                continue
            target_order = layer_by_id[target_layer_id]["order"]
            source_order = source_layer["order"]
            if target_layer_id == source_layer_id or target_order < source_order:
                continue
            edge = (relative, module)
            found.add(edge)
            if edge not in declared:
                violations.append(
                    f"{relative}:{line}: upward import {module} "
                    f"({source_layer_id} -> {target_layer_id})"
                )

    stale = sorted(declared - found)
    if stale:
        rendered = ", ".join(f"{source} -> {module}" for source, module in stale)
        violations.append(f"stale known upward edges: {rendered}")
    if violations:
        raise LogicalLayerError("logical layer violations:\n- " + "\n- ".join(sorted(violations)))

    return {
        "status": "valid",
        "layer_count": len(layers),
        "checked_files": checked,
        "known_upward_edge_count": len(declared),
        "unclassified_internal_import_count": len(unclassified),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except LogicalLayerError as exc:
        print(f"logical layers: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "logical layers: OK "
            f"({result['layer_count']} layers, {result['checked_files']} files, "
            f"{result['known_upward_edge_count']} known upward edges)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
