#!/usr/bin/env python3
"""Read-only static depth audit of pinned functional game-builder backlog items.

No imports, test execution, remote access, weights, artifacts, or task state mutations.
Source presence, syntax and forwarding are *not* functional qualification.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any

from scripts.reconcile_flgb_backlog_batch import BACKLOG, git_snapshot, reconcile

MAX_BLOB_BYTES = 2_000_000


def read_pinned(root: Path, head: str, path: str) -> str:
    """Read only an already-validated tree path at exactly the audited commit."""
    blob = subprocess.run(
        ["git", "-C", str(root), "show", f"{head}:{path}"],
        capture_output=True, check=True,
    ).stdout
    if len(blob) > MAX_BLOB_BYTES:
        raise ValueError("declared source exceeds static inspection limit")
    return blob.decode("utf-8")


def _relative_module_path(path: str, level: int, module: str) -> str | None:
    """Resolve only explicit relative module imports, without executing them."""
    parents = list(PurePosixPath(path).parts[:-1])
    if level < 1 or level > len(parents):
        return None
    prefix = parents[:len(parents) - (level - 1)]
    return "/".join(prefix + (module.split(".") if module else []))


def inspect_python(path: str, source: str, tracked: set[str], *, test: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path, "syntax_ok": False, "kind": "unknown",
        "declared_definitions": 0, "test_cases": 0, "assertion_sites": 0,
        "unresolved_relative_modules": [], "relative_owner_imports": [],
        "ambiguous_package_exports": [], "warnings": [],
    }
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        result["warnings"].append(f"python-syntax:{exc.lineno}:{exc.msg}")
        return result
    result["syntax_ok"] = True
    statement_nodes = [
        node for node in tree.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str))
        and not (isinstance(node, ast.Assign)
                 and all(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets))
    ]
    is_forwarder = bool(statement_nodes) and all(
        isinstance(node, (ast.Import, ast.ImportFrom)) for node in statement_nodes
    )
    definitions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    result["declared_definitions"] = len(definitions)
    result["kind"] = (
        "forwarding-module" if is_forwarder else
        "source-definitions" if definitions else
        "source-wiring-or-data" if statement_nodes else "empty-or-docstring-only"
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        location = _relative_module_path(path, node.level, node.module or "")
        if location is None:
            result["warnings"].append("relative-import-escapes-package")
            continue
        if node.module:
            module_file = (location + ".py" if location + ".py" in tracked else
                           location + "/__init__.py")
            if module_file not in tracked:
                result["unresolved_relative_modules"].append(location)
            else:
                result["relative_owner_imports"].append({
                    "path": module_file,
                    "symbols": [alias.name for alias in node.names],
                })
        else:
            # `from . import X` may refer to a sibling module or a symbol
            # re-exported by the package __init__. Never infer failure merely
            # because there is no X.py: package attributes may be intentional.
            for alias in node.names:
                if alias.name == "*":
                    result["warnings"].append("wildcard-package-import-needs-review")
                    continue
                sibling = location + "/" + alias.name
                module_file = (sibling + ".py" if sibling + ".py" in tracked else
                               sibling + "/__init__.py")
                if module_file in tracked:
                    result["relative_owner_imports"].append({
                        "path": module_file, "symbols": [],
                    })
                elif location + "/__init__.py" in tracked:
                    result["ambiguous_package_exports"].append({
                        "package": location, "symbol": alias.name,
                    })
                else:
                    result["unresolved_relative_modules"].append(sibling)
    result["unresolved_relative_modules"] = sorted(set(result["unresolved_relative_modules"]))
    result["relative_owner_imports"] = sorted(
        result["relative_owner_imports"], key=lambda item: (item["path"], item["symbols"]))
    result["ambiguous_package_exports"] = sorted(
        result["ambiguous_package_exports"], key=lambda item: (item["package"], item["symbol"]))
    if result["unresolved_relative_modules"]:
        result["warnings"].append("missing-relative-import-module")
    if result["kind"] in ("forwarding-module", "empty-or-docstring-only"):
        result["warnings"].append("no-local-executable-definition")
    if test:
        result["test_cases"] = sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
        result["assertion_sites"] = sum(
            isinstance(node, ast.Assert) or
            (isinstance(node, ast.Call) and
             (isinstance(node.func, ast.Attribute)
              and (node.func.attr.startswith("assert") or node.func.attr == "raises")))
            for node in ast.walk(tree)
        )
        if not result["test_cases"]:
            result["warnings"].append("no-test-function-declared")
        if not result["assertion_sites"]:
            result["warnings"].append("no-direct-assertion-site")
    return result


def inspect_contract(path: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path, "json_valid": False, "schema_shape": False, "warnings": [],
    }
    try:
        data = json.loads(source, object_pairs_hook=_reject_duplicate_keys,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (json.JSONDecodeError, ValueError) as exc:
        result["warnings"].append("invalid-contract-json:" + str(exc)[:160])
        return result
    result["json_valid"] = True
    result["schema_shape"] = (
        isinstance(data, dict) and
        (isinstance(data.get("type"), str)
         or isinstance(data.get("$ref"), str)
         or isinstance(data.get("oneOf"), list)
         or isinstance(data.get("allOf"), list))
    )
    if not result["schema_shape"]:
        result["warnings"].append("schema-structure-needs-review")
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key[:80])
        result[key] = value
    return result


def audit(manifest: dict[str, Any], tracked: set[str], head: str, root: Path,
          *, start: int, count: int, reader=read_pinned) -> dict[str, Any]:
    presence = reconcile(manifest, tracked, head, start=start, count=count)
    counts: Counter[str] = Counter()
    items = []
    for base in presence["items"]:
        details: dict[str, Any] = {"id": base["id"], "declared_state": base["declared_state"]}
        for kind, field in (
            ("implementation", "implementation_target"),
            ("contract", "contract_target"),
            ("test", "test_target"),
        ):
            path = base[field]
            if path not in tracked:
                details[kind] = {"path": path, "warnings": ["target-absent-from-head"]}
                counts["target-absent-from-head"] += 1
                continue
            try:
                source = reader(root, head, path)
                value = (inspect_contract(path, source) if kind == "contract" else
                         inspect_python(path, source, tracked, test=(kind == "test")))
            except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as exc:
                value = {"path": path, "warnings": ["static-read-failed:" + type(exc).__name__]}
            details[kind] = value
            if kind == "implementation":
                counts["implementation_" + value.get("kind", "unreadable")] += 1
            for warning in value.get("warnings", []):
                counts[warning.split(":")[0]] += 1
        items.append(details)
    return {
        "schema": "skeleton.flgb.static-depth-audit.v1",
        "source_sha": head, "start": start, "count": count,
        "manifest_task_count": presence["total_backlog_tasks"],
        "files_present_in_all_reviewed_tasks": presence["all_three_files_present"],
        "static_counts": dict(sorted(counts.items())),
        "completion_claim": False,
        "limitations": [
            "Python syntax and JSON structure only; imports not executed",
            "Forwarding modules may delegate substantive logic to other canonical owners",
            "No test, model inference, native engine, E2E, training or runtime evidence produced",
            "Findings are diagnostic leads, not automatically verified defects",
        ],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", type=int, default=100)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    head, tracked = git_snapshot(args.repo)
    manifest = json.loads(read_pinned(args.repo, head, BACKLOG))
    result = audit(manifest, tracked, head, args.repo,
                   start=args.start, count=args.count)
    if args.summary_only:
        result.pop("items")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["files_present_in_all_reviewed_tasks"] != args.count else 0


if __name__ == "__main__":
    raise SystemExit(main())
