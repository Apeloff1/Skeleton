#!/usr/bin/env python3
"""Enforce the ContextCompiler/engine boundary for product AI surfaces.

Product routes and services may compile canonical context and submit work through
backend engine clients. They must not instantiate provider transports, provider
registries, provider-neutral requests directly, or the retired LlmChat
compatibility surface. Provider ownership belongs to the Skeleton engine.
"""

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

PROVIDER_RUNTIME_MODULES = {
    "skeleton.provider_runtime",
    "core.ai_provider",
    "core.ai_provider_compat",
    "backend.core.ai_provider",
    "backend.core.ai_provider_compat",
}
LEGACY_PROVIDER_MODULE = "emergentintegrations.llm.chat"
FORBIDDEN_PROVIDER_SYMBOLS = {
    "ProviderRequest",
    "ProviderRegistry",
    "ProviderAdapter",
    "OpenAIProviderAdapter",
    "OpenAISyncProviderAdapter",
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


def _module_is_provider_runtime(module: str) -> bool:
    return any(
        module == candidate or module.startswith(candidate + ".")
        for candidate in PROVIDER_RUNTIME_MODULES
    )


def audit_file(path: Path, *, root: Path = ROOT) -> list[str]:
    rel = path.relative_to(root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [
            f"{rel}: unable to audit Python source: "
            f"{type(exc).__name__}: {exc}"
        ]

    violations: list[str] = []
    provider_module_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == LEGACY_PROVIDER_MODULE or module.startswith(
                LEGACY_PROVIDER_MODULE + "."
            ):
                violations.append(
                    f"{rel}:{node.lineno}: legacy LlmChat provider surface "
                    "is forbidden in product code"
                )
                continue
            if not _module_is_provider_runtime(module):
                continue
            imported = {alias.name for alias in node.names}
            dangerous = sorted(imported & FORBIDDEN_PROVIDER_SYMBOLS)
            if dangerous:
                violations.append(
                    f"{rel}:{node.lineno}: direct provider runtime symbol "
                    f"import outside engine/core owner: {', '.join(dangerous)}"
                )
            elif module in {
                "core.ai_provider",
                "core.ai_provider_compat",
                "backend.core.ai_provider",
                "backend.core.ai_provider_compat",
            }:
                violations.append(
                    f"{rel}:{node.lineno}: direct provider compatibility "
                    "module import outside backend/core"
                )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module == LEGACY_PROVIDER_MODULE or module.startswith(
                    LEGACY_PROVIDER_MODULE + "."
                ):
                    violations.append(
                        f"{rel}:{node.lineno}: legacy LlmChat provider surface "
                        "is forbidden in product code"
                    )
                if _module_is_provider_runtime(module):
                    provider_module_aliases.add(
                        alias.asname or module.split(".")[-1]
                    )
                    violations.append(
                        f"{rel}:{node.lineno}: direct provider runtime module "
                        "import outside engine/core owner"
                    )

    if provider_module_aliases:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in provider_module_aliases:
                continue
            if node.attr in FORBIDDEN_PROVIDER_SYMBOLS:
                violations.append(
                    f"{rel}:{node.lineno}: direct provider runtime access "
                    f"{node.value.id}.{node.attr}"
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
        print("Context execution boundary violations:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Context execution boundary audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
