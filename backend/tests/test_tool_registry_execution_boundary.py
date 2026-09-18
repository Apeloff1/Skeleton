from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_REGISTRY = ROOT / "backend" / "services" / "tool_registry.py"


def _tool_run_node() -> tuple[str, ast.AsyncFunctionDef]:
    source = TOOL_REGISTRY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_tool_run_code":
            return source, node
    raise AssertionError("_tool_run_code not found")


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def test_tool_run_code_never_executes_in_process() -> None:
    _, node = _tool_run_node()
    calls = {_call_name(item) for item in ast.walk(node) if isinstance(item, ast.Call)}

    assert "exec" not in calls
    assert "builtins.exec" not in calls
    assert "eval" not in calls
    assert "builtins.eval" not in calls


def test_tool_run_code_uses_bounded_isolated_subprocess() -> None:
    source, node = _tool_run_node()
    body = ast.get_source_segment(source, node) or ""

    assert "asyncio.create_subprocess_exec" in body
    assert "asyncio.wait_for" in body
    assert "TemporaryDirectory" in body
    assert '"-I"' in body
    assert '"-S"' in body
    assert "timeout_seconds" in body
    assert "process.kill()" in body
