"""Static security contracts around server-side program execution.

These tests deliberately parse ``server.py`` instead of importing it so the
security gate stays fast and dependency-independent in CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server.py"
EXECUTOR_CLASSES = {"PythonExecutor", "CppExecutor", "CExecutor"}


def _tree() -> ast.Module:
    return ast.parse(SERVER.read_text(encoding="utf-8"), filename=str(SERVER))


def _qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def test_server_never_uses_shell_subprocess_api():
    forbidden = {
        "asyncio.create_subprocess_shell",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    }
    violations: list[str] = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_name(node.func)
        if name in forbidden:
            violations.append(f"{name}@{node.lineno}")
        if name in {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
        }:
            for keyword in node.keywords:
                if keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ):
                    violations.append(f"{name}(shell=...)@{node.lineno}")
    assert not violations, "shell-backed subprocess execution is forbidden: " + ", ".join(violations)


def test_executors_fail_closed_before_spawning_children():
    tree = _tree()
    seen: set[str] = set()
    failures: list[str] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in EXECUTOR_CLASSES:
            continue
        seen.add(node.name)
        execute = next(
            (
                item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "execute"
            ),
            None,
        )
        assert execute is not None, f"{node.name}.execute is missing"
        guard_lines = [
            call.lineno
            for call in ast.walk(execute)
            if isinstance(call, ast.Call) and _qualified_name(call.func) == "code_execution_enabled"
        ]
        spawn_lines = [
            call.lineno
            for call in ast.walk(execute)
            if isinstance(call, ast.Call)
            and _qualified_name(call.func) in {
                "asyncio.create_subprocess_exec",
                "asyncio.create_subprocess_shell",
            }
        ]
        if spawn_lines and (not guard_lines or min(guard_lines) > min(spawn_lines)):
            failures.append(node.name)

    assert seen == EXECUTOR_CLASSES
    assert not failures, "executors spawn before checking the fail-closed guard: " + ", ".join(failures)


def test_execution_opt_in_is_not_hardcoded_in_source():
    source = SERVER.read_text(encoding="utf-8")
    assert "ALLOW_UNSAFE_CODE_EXECUTION=true" not in source
    assert "os.environ['ALLOW_UNSAFE_CODE_EXECUTION']" not in source
    assert 'os.environ["ALLOW_UNSAFE_CODE_EXECUTION"]' not in source
