from __future__ import annotations

import ast
from pathlib import Path


TOOL_REGISTRY = Path("backend/services/tool_registry.py")


def test_tool_registry_avoids_in_process_exec() -> None:
    source = TOOL_REGISTRY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "exec":
            forbidden.append(node.lineno)
        elif isinstance(func, ast.Attribute) and func.attr == "exec":
            forbidden.append(node.lineno)

    assert forbidden == []


def test_python_tool_run_uses_isolated_child_interpreter() -> None:
    source = TOOL_REGISTRY.read_text(encoding="utf-8")

    assert "[sys.executable, \"-I\", src]" in source
    assert "timeout=30" in source
    assert "capture_output=True" in source
