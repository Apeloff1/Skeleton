"""Fail-closed checks for the repository's canonical dependency boundaries.

This gate is intentionally narrow. It protects high-confidence layer boundaries that
should never be crossed by production code while leaving finer-grained package
relationships to normal review. Keep it dependency-free so it can run early in CI.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

RULES = (
    {
        "root": "skeleton",
        "excluded_prefixes": ("skeleton/testing/",),
        "forbidden_modules": ("backend", "frontend", "tests"),
    },
    {
        "root": "backend",
        "excluded_prefixes": ("backend/tests/",),
        "forbidden_modules": ("frontend", "tests", "skeleton.testing"),
    },
)


def _matches_module(module: str, forbidden: str) -> bool:
    """Match one module namespace exactly or below it, never a lookalike prefix."""
    return module == forbidden or module.startswith(forbidden + ".")


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def violations_for_file(path: Path, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return architectural import violations for one production Python file."""
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        return [f"{path}: source path is outside repository root"]

    rule = next(
        (
            candidate
            for candidate in RULES
            if rel == candidate["root"] or rel.startswith(candidate["root"] + "/")
        ),
        None,
    )
    if rule is None or any(
        rel.startswith(prefix) for prefix in rule["excluded_prefixes"]
    ):
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{rel}: read failure: {type(exc).__name__}"]

    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return [f"{rel}:{exc.lineno or 0}: parse failure: SyntaxError"]

    findings: list[str] = []
    for line_number, module in _iter_imports(tree):
        for forbidden in rule["forbidden_modules"]:
            if _matches_module(module, forbidden):
                findings.append(
                    f"{rel}:{line_number}: forbidden import {module!r} "
                    f"from {rule['root']} production code"
                )
                break
    return findings


def scan_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    """Scan canonical Python source roots and fail closed on missing roots."""
    findings: list[str] = []
    for rule in RULES:
        source_root = repo_root / rule["root"]
        if not source_root.is_dir():
            findings.append(f"{rule['root']}: missing canonical source root")
            continue

        for path in sorted(source_root.rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if "__pycache__" in path.parts:
                continue
            if any(rel.startswith(prefix) for prefix in rule["excluded_prefixes"]):
                continue
            findings.extend(violations_for_file(path, repo_root))
    return findings


def main() -> int:
    findings = scan_repository()
    if findings:
        print("Architecture boundary violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Architecture boundary gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
