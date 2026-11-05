"""CI native-AI acceptance fixtures must use an existing private temp root.

The test preserves OS-controlled private TemporaryDirectory permissions while
avoiding assumptions about a developer's home directory in hosted runners.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "skeleton/testing/test_ai_flight_http.py",
    "skeleton/testing/test_ai_knowledge_plane.py",
    "skeleton/testing/test_ai_flight_context_admission.py",
    "skeleton/testing/test_ai_git_knowledge.py",
    "skeleton/testing/test_ai_native_daemon.py",
)


def test_native_fixture_temp_roots_are_portable_and_private() -> None:
    for rel in FILES:
        source = (ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
        found = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "TemporaryDirectory"
                and isinstance(func.value, ast.Name)
                and func.value.id == "tempfile"
            ):
                continue
            found += 1
            # Source tests use an existing per-runner home rather than
            # /tmp: the production descriptor guard rejects group-writable
            # parents, even when a child has mode 0700.
            directories = [kw.value for kw in node.keywords if kw.arg == "dir"]
            assert len(directories) == 1, rel
            requested = directories[0]
            assert (
                isinstance(requested, ast.Call)
                and isinstance(requested.func, ast.Attribute)
                and requested.func.attr == "home"
                and isinstance(requested.func.value, ast.Name)
                and requested.func.value.id == "Path"
                and not requested.args and not requested.keywords
            ), rel
            assert any(kw.arg == "prefix" for kw in node.keywords), rel
        assert found >= 1, rel
