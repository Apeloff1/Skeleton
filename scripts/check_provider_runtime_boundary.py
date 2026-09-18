#!/usr/bin/env python3
"""Fail closed when unaudited provider SDKs bypass maintained runtimes.

Issue #116 keeps frontier/agent model execution behind
``skeleton.frontier.model_runtime`` and backend provider execution behind the
maintained backend adapter boundary.

The old third-party Emergent SDK is no longer installed.  The repository owns a
source-compatible module at ``backend/emergentintegrations/llm/chat.py`` that
delegates legacy *static backend imports* into ``core.ai_provider_compat`` and
the canonical provider runtime.  Those static backend imports are therefore a
migration surface, not vendor SDK imports. Dynamic loading of the legacy name is
still rejected because it bypasses normal import review, and non-backend code
must not depend on the compatibility namespace.

Direct Google model SDK imports remain forbidden until a deliberate canonical
adapter and shared contract tests are added. The frontier/agent core is also
kept free of all direct provider SDK imports.
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
LOCAL_EMERGENT_COMPAT_MODULE = "emergentintegrations.llm.chat"
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


def _is_backend_path(rel: Path) -> bool:
    return bool(rel.parts and rel.parts[0] == "backend")


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

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if _matches_prefix(module, GOOGLE_MODULES):
                    violations.append(
                        f"{rel}:{node.lineno}: direct Google model SDK import {module!r}"
                    )
                if module == LOCAL_EMERGENT_COMPAT_MODULE and not _is_backend_path(rel):
                    violations.append(
                        f"{rel}:{node.lineno}: backend-only provider compatibility import"
                    )
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

            if module == LOCAL_EMERGENT_COMPAT_MODULE and not _is_backend_path(rel):
                violations.append(
                    f"{rel}:{node.lineno}: backend-only provider compatibility import"
                )

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
            if target == LOCAL_EMERGENT_COMPAT_MODULE or target.startswith(
                LOCAL_EMERGENT_COMPAT_MODULE + "."
            ):
                violations.append(
                    f"{rel}:{node.lineno}: dynamic provider compatibility import"
                )
            if _is_core_path(rel) and target.split(".")[0] in CORE_PROVIDER_ROOTS:
                violations.append(
                    f"{rel}:{node.lineno}: dynamic provider import {target!r} in core runtime"
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
