"""Dependency-free high-confidence Python SAST gate.

This scanner intentionally targets dangerous primitives with a low false-positive
rate. Broader lint/security tooling can layer on top, but these patterns should
never silently enter backend production code.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
TRACKED_MODULES = {"requests", "httpx", "ssl", "tempfile", "jwt"}
NETWORK_CALLS = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.head",
    "requests.options",
    "requests.request",
    "requests.Session.request",
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
    "httpx.head",
    "httpx.options",
    "httpx.request",
}


def python_files() -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in TRACKED_MODULES:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root not in TRACKED_MODULES:
                continue
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _literal_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _dict_disables_signature_verification(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    for key, value in zip(node.keys, node.values):
        if (
            isinstance(key, ast.Constant)
            and key.value in {"verify_signature", "verify"}
            and _literal_false(value)
        ):
            return True
    return False


def call_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    name = canonical_name(node.func, aliases)

    if name in {"eval", "exec"}:
        return f"{name}() is forbidden in backend production code"

    if name == "tempfile.mktemp":
        return "tempfile.mktemp() is race-prone; use NamedTemporaryFile or mkstemp"

    if name == "ssl._create_unverified_context":
        return "ssl._create_unverified_context() disables certificate verification"

    if name in NETWORK_CALLS and _literal_false(_keyword(node, "verify")):
        return f"{name}(..., verify=False) is forbidden"

    if name in {"httpx.Client", "httpx.AsyncClient"} and _literal_false(_keyword(node, "verify")):
        return f"{name}(..., verify=False) is forbidden"

    if name in {"jwt.decode", "jwt.api_jwt.decode_complete"}:
        if _dict_disables_signature_verification(_keyword(node, "options")):
            return f"{name}() must not disable signature verification"

    return None


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = import_aliases(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        violation = call_violation(node, aliases)
        if violation:
            findings.append(f"{label}:{node.lineno}: {violation}")
    return findings


def main() -> int:
    findings: list[str] = []
    for path in python_files():
        findings.extend(violations(path))
    if findings:
        print("High-confidence SAST violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("High-confidence SAST gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
