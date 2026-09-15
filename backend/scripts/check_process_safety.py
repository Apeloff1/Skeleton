"""Fail CI on unsafe process invocation patterns in backend Python code.

Dependency-free by design so it can run before application imports. The scanner
tracks common import, assignment, destructuring, walrus, getattr, module
__getattribute__, namespace-mapping, mapping-get, and functools.partial aliases
to prevent trivial process policy bypasses. Statically obvious subprocess
command strings are rejected in favor of explicit argument vectors.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output", "Popen"}
TRACKED_MODULES = {"asyncio", "os", "subprocess"}
KNOWN_MODULES = TRACKED_MODULES | {"functools"}
ALIASABLE_HELPERS = {"getattr", "vars", "functools.partial"}
UNSAFE_CALLS = {
    "os.system": "os.system() is forbidden",
    "os.popen": "os.popen() is forbidden",
    "asyncio.create_subprocess_shell": "asyncio.create_subprocess_shell() is forbidden",
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


def literal_false(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def obvious_command_string(node: ast.AST) -> bool:
    """Return True when an argv expression is statically string-shaped.

    This intentionally handles only cases that are safe to classify without
    data-flow guessing: string literals, f-strings, concatenations containing a
    string-shaped operand, and common string-building methods. Unknown names
    remain allowed so legitimate dynamically assembled argument vectors are not
    falsely rejected by this lightweight gate.
    """
    if literal_string(node) is not None or isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return obvious_command_string(node.left) or obvious_command_string(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"format", "join"}:
            return True
    return False


def command_argument(node: ast.Call) -> ast.AST | None:
    """Return the subprocess argv argument from positional or keyword form."""
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "args":
            return keyword.value
    return None


def star_import_violations(tree: ast.AST, label: Path) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in TRACKED_MODULES:
            continue
        if any(item.name == "*" for item in node.names):
            findings.append(
                f"{label}:{node.lineno}: star import from {node.module} is forbidden because process call provenance cannot be statically proven"
            )
    return findings


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in KNOWN_MODULES:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module in KNOWN_MODULES:
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def namespace_mapping_owner(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        mapped = aliases.get(node.id)
        if mapped and mapped.endswith(".__dict__"):
            owner = mapped.removesuffix(".__dict__")
            return owner if owner in TRACKED_MODULES else None
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        owner = canonical_name(node.value, aliases)
        return owner if owner in TRACKED_MODULES else None
    if (
        isinstance(node, ast.Call)
        and canonical_name(node.func, aliases) == "vars"
        and len(node.args) == 1
        and not node.keywords
    ):
        owner = canonical_name(node.args[0], aliases)
        return owner if owner in TRACKED_MODULES else None
    return None


def namespace_mapping_get_owner(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if not isinstance(node, ast.Attribute) or node.attr != "get":
        return None
    owner = namespace_mapping_owner(node.value, aliases)
    return owner if owner in TRACKED_MODULES else None


def module_getattribute_owner(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if not isinstance(node, ast.Attribute) or node.attr != "__getattribute__":
        return None
    owner = canonical_name(node.value, aliases)
    return owner if owner in TRACKED_MODULES else None


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Call):
        wrapper = canonical_name(node.func, aliases)
        if wrapper == "functools.partial" and node.args:
            return canonical_name(node.args[0], aliases)
        if wrapper == "getattr" and len(node.args) >= 2:
            owner = canonical_name(node.args[0], aliases)
            attribute = literal_string(node.args[1])
            if owner in TRACKED_MODULES and attribute is not None:
                return f"{owner}.{attribute}"
            return None
        if wrapper == "vars" and len(node.args) == 1 and not node.keywords:
            owner = canonical_name(node.args[0], aliases)
            if owner in TRACKED_MODULES:
                return f"{owner}.__dict__"
            return None

        direct_owner = module_getattribute_owner(node.func, aliases)
        if direct_owner is not None and node.args:
            attribute = literal_string(node.args[0])
            if attribute is not None:
                return f"{direct_owner}.{attribute}"
            return None

        mapping_owner = namespace_mapping_get_owner(node.func, aliases)
        if mapping_owner is not None and node.args:
            attribute = literal_string(node.args[0])
            if attribute is not None:
                return f"{mapping_owner}.{attribute}"
            return None

    if isinstance(node, ast.Subscript):
        owner = namespace_mapping_owner(node.value, aliases)
        attribute = literal_string(node.slice)
        if owner in TRACKED_MODULES and attribute is not None:
            return f"{owner}.{attribute}"
        return None

    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def destructured_assignments(target: ast.AST, value: ast.AST) -> list[tuple[str, ast.AST]]:
    """Pair exact positional tuple/list destructuring targets with source nodes."""
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if isinstance(target, ast.Starred):
        return []
    if not isinstance(target, (ast.Tuple, ast.List)) or not isinstance(value, (ast.Tuple, ast.List)):
        return []
    if len(target.elts) != len(value.elts):
        return []
    pairs: list[tuple[str, ast.AST]] = []
    for target_item, value_item in zip(target.elts, value.elts):
        pairs.extend(destructured_assignments(target_item, value_item))
    return pairs


def assignment_aliases(tree: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Resolve aliases assigned from tracked process callables or policy helpers."""
    resolved = dict(aliases)
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assignments.extend(destructured_assignments(target, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assignments.append((node.target.id, node.value))
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            assignments.append((node.target.id, node.value))
    tracked_names = (
        UNSAFE_CALLS.keys()
        | {f"subprocess.{call}" for call in SUBPROCESS_CALLS}
        | {f"{module}.__dict__" for module in TRACKED_MODULES}
        | ALIASABLE_HELPERS
    )
    changed = True
    while changed:
        changed = False
        for target, value in assignments:
            source = canonical_name(value, resolved)
            if source in tracked_names and resolved.get(target) != source:
                resolved[target] = source
                changed = True
    return resolved


def dynamic_getattr_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    if canonical_name(node.func, aliases) != "getattr" or len(node.args) < 2:
        return None
    owner = canonical_name(node.args[0], aliases)
    attribute = node.args[1]
    if owner not in TRACKED_MODULES or literal_string(attribute) is not None:
        return None
    return f"dynamic getattr() on {owner} is forbidden because process policy cannot be statically proven"


def dynamic_getattribute_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    owner = module_getattribute_owner(node.func, aliases)
    if owner not in TRACKED_MODULES or not node.args:
        return None
    if literal_string(node.args[0]) is not None:
        return None
    return f"dynamic __getattribute__() on {owner} is forbidden because process policy cannot be statically proven"


def dynamic_namespace_mapping_violation(node: ast.Subscript, aliases: dict[str, str]) -> str | None:
    owner = namespace_mapping_owner(node.value, aliases)
    if owner not in TRACKED_MODULES or literal_string(node.slice) is not None:
        return None
    return f"dynamic namespace lookup on {owner} is forbidden because process policy cannot be statically proven"


def dynamic_namespace_get_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    owner = namespace_mapping_get_owner(node.func, aliases)
    if owner not in TRACKED_MODULES or not node.args or literal_string(node.args[0]) is not None:
        return None
    return f"dynamic namespace get() on {owner} is forbidden because process policy cannot be statically proven"


def partial_policy_violations(node: ast.Call, aliases: dict[str, str]) -> list[str]:
    """Validate process-sensitive arguments pre-bound through functools.partial."""
    if canonical_name(node.func, aliases) != "functools.partial" or not node.args:
        return []
    target = canonical_name(node.args[0], aliases)
    if target not in {f"subprocess.{call}" for call in SUBPROCESS_CALLS}:
        return []
    findings: list[str] = []
    if len(node.args) > 1 and obvious_command_string(node.args[1]):
        findings.append(
            f"{target} partial command must be an argument vector, not a string-shaped command"
        )
    for keyword in node.keywords:
        if keyword.arg is None:
            findings.append(f"{target} partial(..., **kwargs) is forbidden because shell policy cannot be statically proven")
        elif keyword.arg == "shell" and not literal_false(keyword.value):
            findings.append(f"{target} partial(..., shell=...) is forbidden unless shell=False is literal")
        elif keyword.arg == "args" and obvious_command_string(keyword.value):
            findings.append(
                f"{target} partial args= must be an argument vector, not a string-shaped command"
            )
    return findings


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = assignment_aliases(tree, import_aliases(tree))
    findings = star_import_violations(tree, label)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            dynamic_mapping_violation = dynamic_namespace_mapping_violation(node, aliases)
            if dynamic_mapping_violation:
                findings.append(f"{label}:{node.lineno}: {dynamic_mapping_violation}")
        if not isinstance(node, ast.Call):
            continue

        for dynamic_check in (
            dynamic_namespace_get_violation(node, aliases),
            dynamic_getattribute_violation(node, aliases),
            dynamic_getattr_violation(node, aliases),
        ):
            if dynamic_check:
                findings.append(f"{label}:{node.lineno}: {dynamic_check}")

        for partial_violation in partial_policy_violations(node, aliases):
            findings.append(f"{label}:{node.lineno}: {partial_violation}")

        name = canonical_name(node.func, aliases)
        if name in UNSAFE_CALLS:
            findings.append(f"{label}:{node.lineno}: {UNSAFE_CALLS[name]}")
            continue
        if name in {f"subprocess.{call}" for call in SUBPROCESS_CALLS}:
            argv = command_argument(node)
            if argv is not None and obvious_command_string(argv):
                findings.append(
                    f"{label}:{node.lineno}: {name} command must be an argument vector, not a string-shaped command"
                )
            for keyword in node.keywords:
                if keyword.arg is None:
                    findings.append(f"{label}:{node.lineno}: {name}(..., **kwargs) is forbidden because shell policy cannot be statically proven")
                    continue
                if keyword.arg == "shell" and not literal_false(keyword.value):
                    findings.append(f"{label}:{node.lineno}: {name}(..., shell=...) is forbidden unless shell=False is literal")
    return findings


def main() -> int:
    findings: list[str] = []
    for path in python_files():
        findings.extend(violations(path))
    if findings:
        print("Unsafe process invocation patterns detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(
        "Process safety gate passed: no unsafe shell execution, statically obvious string-shaped subprocess commands, "
        "opaque subprocess kwargs, dynamic process lookup, process-sensitive star imports, unsafe process partials, "
        "unsafe process namespace get()/__getattribute__(), os.system(), or os.popen() calls found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
