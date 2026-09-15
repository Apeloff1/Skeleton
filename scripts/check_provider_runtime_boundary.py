#!/usr/bin/env python3
"""Fail closed when unaudited provider SDKs bypass the canonical runtime.

Issue #116 keeps model/provider execution behind ``skeleton.frontier.model_runtime``.
This gate makes two current migration facts executable policy:

* Google GenAI has no active runtime call site. Direct or dynamic Google model
  SDK imports are forbidden until a canonical adapter and shared contract tests
  are added deliberately.
* ``backend/server.py`` still carries a retired, local Emergent compatibility
  import for boot compatibility. Those symbols must remain unused; any real
  use, dynamic import, or import from another runtime module is a violation.

The frontier/agent core is additionally kept free of direct provider SDK imports.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ("backend", "skeleton")
SKIP_PARTS = {"tests", "test", "__pycache__", ".venv", "venv", "node_modules"}
GOOGLE_MODULES = ("google.genai", "google.generativeai")
RETIRED_EMERGENT_MODULE = "emergentintegrations.llm.chat"
LEGACY_EMERGENT_IMPORT = Path("backend/server.py")
CORE_PROVIDER_ROOTS = {"openai", "litellm", "google", "emergentintegrations"}
CORE_PREFIXES = (Path("skeleton/frontier"), Path("skeleton/agents"))


def _runtime_python_files(root: Path) -> Iterable[Path]:
    for runtime_root in RUNTIME_ROOTS:
        base = root / runtime_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            yield path


def _matches_prefix(module: str | None, prefixes: tuple[str, ...]) -> bool:
    if not module:
        return False
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _is_core_path(rel: Path) -> bool:
    return any(rel == prefix or prefix in rel.parents for prefix in CORE_PREFIXES)


def _loaded_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _dynamic_import_target(call: ast.Call) -> str | None:
    if not call.args or not isinstance(call.args[0], ast.Constant):
        return None
    target = call.args[0].value
    if not isinstance(target, str):
        return None

    func = call.func
    if isinstance(func, ast.Name) and func.id == "__import__":
        return target
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id == "importlib"
    ):
        return target
    return None


def audit_file(path: Path, *, root: Path = ROOT) -> list[str]:
    rel = path.relative_to(root)
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(rel))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{rel}: unable to audit Python source: {type(exc).__name__}: {exc}"]

    violations: list[str] = []
    loaded = _loaded_names(tree)
    legacy_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if _matches_prefix(module, GOOGLE_MODULES):
                    violations.append(
                        f"{rel}:{node.lineno}: direct Google model SDK import {module!r}"
                    )
                if module == RETIRED_EMERGENT_MODULE:
                    if rel != LEGACY_EMERGENT_IMPORT:
                        violations.append(
                            f"{rel}:{node.lineno}: retired Emergent model shim import"
                        )
                    else:
                        legacy_aliases.add(alias.asname or module.split(".")[0])
                if _is_core_path(rel) and module.split(".")[0] in CORE_PROVIDER_ROOTS:
                    violations.append(
                        f"{rel}:{node.lineno}: provider SDK import {module!r} in core runtime"
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            google_from_import = (
                _matches_prefix(module, GOOGLE_MODULES)
                or (module == "google" and any(alias.name == "genai" for alias in node.names))
            )
            if google_from_import:
                violations.append(
                    f"{rel}:{node.lineno}: direct Google model SDK import from {module!r}"
                )

            retired_from_import = module == RETIRED_EMERGENT_MODULE
            if retired_from_import:
                if rel != LEGACY_EMERGENT_IMPORT:
                    violations.append(
                        f"{rel}:{node.lineno}: retired Emergent model shim import"
                    )
                else:
                    for alias in node.names:
                        legacy_aliases.add(alias.asname or alias.name)

            root_name = module.split(".")[0] if module else ""
            if _is_core_path(rel) and root_name in CORE_PROVIDER_ROOTS:
                violations.append(
                    f"{rel}:{node.lineno}: provider SDK import from {module!r} in core runtime"
                )

        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if target is None:
                continue
            if _matches_prefix(target, GOOGLE_MODULES):
                violations.append(
                    f"{rel}:{node.lineno}: dynamic Google model SDK import {target!r}"
                )
            if target == RETIRED_EMERGENT_MODULE or target.startswith(
                RETIRED_EMERGENT_MODULE + "."
            ):
                violations.append(
                    f"{rel}:{node.lineno}: dynamic retired Emergent model shim import"
                )
            if _is_core_path(rel) and target.split(".")[0] in CORE_PROVIDER_ROOTS:
                violations.append(
                    f"{rel}:{node.lineno}: dynamic provider import {target!r} in core runtime"
                )

    if rel == LEGACY_EMERGENT_IMPORT:
        used = sorted(name for name in legacy_aliases if name in loaded)
        if used:
            violations.append(
                f"{rel}: retired Emergent compatibility symbols are active: {', '.join(used)}"
            )

    return violations


def audit_repository(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for path in _runtime_python_files(root):
        violations.extend(audit_file(path, root=root))
    return violations


def main() -> int:
    violations = audit_repository(ROOT)
    if violations:
        print("Provider runtime boundary violations:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Provider runtime boundary audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
