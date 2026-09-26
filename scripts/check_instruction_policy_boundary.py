#!/usr/bin/env python3
"""Enforce versioned instruction-policy ownership for product AI chat surfaces."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROOTS = (
    Path("backend/routes"),
    Path("backend/services"),
    Path("backend/gameforge"),
)
SKIP_PARTS = {"tests", "test", "__pycache__", ".venv", "venv", "node_modules"}
ENGINE_CHAT_MODULES = {
    "core.engine_chat",
    "backend.core.engine_chat",
}


def _product_python_files(root: Path) -> Iterable[Path]:
    for relative_root in PRODUCT_ROOTS:
        base = root / relative_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            yield path


def _engine_chat_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if (node.module or "") not in ENGINE_CHAT_MODULES:
            continue
        for imported in node.names:
            if imported.name == "EngineChat":
                aliases.add(imported.asname or imported.name)
    return aliases


def audit_file(path: Path, *, root: Path = ROOT) -> list[str]:
    rel = path.relative_to(root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [
            f"{rel}: unable to audit Python source: "
            f"{type(exc).__name__}: {exc}"
        ]

    aliases = _engine_chat_aliases(tree)
    if not aliases:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in aliases:
            continue

        keywords = {
            keyword.arg: keyword.value
            for keyword in node.keywords
            if keyword.arg is not None
        }
        policy = keywords.get("instruction_policy")
        if policy is None or (
            isinstance(policy, ast.Constant) and policy.value is None
        ):
            violations.append(
                f"{rel}:{node.lineno}: EngineChat product construction "
                "must bind instruction_policy"
            )
        if "system_message" in keywords:
            violations.append(
                f"{rel}:{node.lineno}: product EngineChat must not own "
                "anonymous system_message alongside instruction policy"
            )

    return sorted(set(violations))


def audit_repository(root: Path = ROOT) -> list[str]:
    violations: list[str] = []
    for path in _product_python_files(root):
        violations.extend(audit_file(path, root=root))
    return violations


def main() -> int:
    violations = audit_repository(ROOT)
    if violations:
        print("Instruction policy boundary violations:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Instruction policy boundary audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
