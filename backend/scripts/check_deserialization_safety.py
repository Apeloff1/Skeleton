"""Fail CI on unsafe Python deserialization primitives.

The scanner is dependency-free and intentionally conservative. It rejects
pickle/dill/marshal/joblib/pandas pickle loading, unsafe PyYAML loaders, NumPy
pickle-enabled loads, and torch.load calls that do not explicitly request
weights-only mode. These formats may execute constructors or code when fed
attacker-controlled bytes and therefore must not appear in production backend
paths by accident.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
UNSAFE_OBJECT_LOADERS = {
    "pickle.load",
    "pickle.loads",
    "_pickle.load",
    "_pickle.loads",
    "dill.load",
    "dill.loads",
    "marshal.load",
    "marshal.loads",
    "joblib.load",
    "joblib.numpy_pickle.load",
    "pandas.read_pickle",
    "yaml.unsafe_load",
    "yaml.unsafe_load_all",
}
TRACKED_MODULES = {
    "pickle",
    "_pickle",
    "dill",
    "marshal",
    "joblib",
    "pandas",
    "yaml",
    "numpy",
    "torch",
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


def keyword_value(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def has_keyword(node: ast.Call, name: str) -> bool:
    return any(keyword.arg == name for keyword in node.keywords)


def is_literal_true(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def is_literal_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def is_safe_yaml_loader(node: ast.AST | None, aliases: dict[str, str]) -> bool:
    if node is None:
        return False
    name = canonical_name(node, aliases)
    return name in {"yaml.SafeLoader", "yaml.CSafeLoader", "SafeLoader", "CSafeLoader"}


def call_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    name = canonical_name(node.func, aliases)
    if name in UNSAFE_OBJECT_LOADERS:
        return f"{name}() is forbidden for repository code"

    if name in {"yaml.load", "yaml.load_all"}:
        loader = keyword_value(node, "Loader")
        if not is_safe_yaml_loader(loader, aliases):
            return f"{name}() requires literal SafeLoader/CSafeLoader"

    if name == "numpy.load":
        if has_keyword(node, "allow_pickle"):
            allow_pickle = keyword_value(node, "allow_pickle")
            if not is_literal_false(allow_pickle):
                return "numpy.load() allow_pickle override must be literal False"

    if name == "torch.load":
        weights_only = keyword_value(node, "weights_only")
        if not is_literal_true(weights_only):
            return "torch.load() requires literal weights_only=True"

    return None


def star_import_violations(tree: ast.AST, label: Path) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module.split(".", 1)[0] not in TRACKED_MODULES:
            continue
        if any(item.name == "*" for item in node.names):
            findings.append(
                f"{label}:{node.lineno}: star import from {node.module} is forbidden because deserializer provenance cannot be proven"
            )
    return findings


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = import_aliases(tree)
    findings = star_import_violations(tree, label)
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
        print("Unsafe deserialization patterns detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Deserialization safety gate passed: no unsafe object loaders found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
