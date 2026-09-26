#!/usr/bin/env python3
"""Fail closed when application code bypasses the canonical tool runtime.

Application routes, backend services, API handlers, Jeeves, and agents may call
provider-neutral compatibility surfaces, but direct ownership of canonical tool
execution or privileged adapters is restricted to declared runtime owners.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ROOTS = (
    Path("backend/routes"),
    Path("backend/services"),
    Path("skeleton/api"),
    Path("skeleton/jeeves"),
    Path("skeleton/agents"),
)
SKIP_PARTS = {"tests", "test", "__pycache__", ".venv", "venv", "node_modules"}
ALLOWED_DIRECT_OWNERS = {
    Path("backend/services/tool_registry.py"),
    Path("skeleton/api/engine_runtime.py"),
    Path("skeleton/api/engine_service.py"),
}
FORBIDDEN_RUNTIME_PREFIXES = (
    "skeleton.skills.tool_runtime",
    "skeleton.skills.tool_adapters",
    "skeleton.ai.runtime.skills.tool_runtime",
    "skeleton.ai.runtime.skills.tool_adapters",
)
TOOL_CONTRACT_MODULES = (
    "skeleton.skills.tool_contract",
    "skeleton.ai.runtime.skills.tool_contract",
)
FORBIDDEN_CONTRACT_SYMBOLS = {"ToolExecutionRequest"}


def _application_python_files(root: Path) -> Iterable[Path]:
    for relative_root in APPLICATION_ROOTS:
        base = root / relative_root
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
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in prefixes
    )


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
    if rel in ALLOWED_DIRECT_OWNERS:
        return []
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(rel))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [
            f"{rel}: unable to audit Python source: "
            f"{type(exc).__name__}: {exc}"
        ]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_prefix(alias.name, FORBIDDEN_RUNTIME_PREFIXES):
                    violations.append(
                        f"{rel}:{node.lineno}: direct canonical tool runtime "
                        f"import {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _matches_prefix(module, FORBIDDEN_RUNTIME_PREFIXES):
                violations.append(
                    f"{rel}:{node.lineno}: direct canonical tool runtime "
                    f"import from {module!r}"
                )
            if module in TOOL_CONTRACT_MODULES:
                imported = {alias.name for alias in node.names}
                forbidden = sorted(imported & FORBIDDEN_CONTRACT_SYMBOLS)
                if forbidden:
                    violations.append(
                        f"{rel}:{node.lineno}: application surface imports "
                        f"execution request authority {forbidden!r}"
                    )
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if target and (
                _matches_prefix(target, FORBIDDEN_RUNTIME_PREFIXES)
                or target in TOOL_CONTRACT_MODULES
            ):
                violations.append(
                    f"{rel}:{node.lineno}: dynamic canonical tool import "
                    f"{target!r}"
                )
    return violations


def audit_repository(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for path in _application_python_files(root):
        violations.extend(audit_file(path, root=root))
    return violations


def main() -> int:
    violations = audit_repository(ROOT)
    if violations:
        print("Tool runtime boundary violations:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Tool runtime boundary audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
