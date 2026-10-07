from __future__ import annotations

from pathlib import Path

from scripts.check_tool_runtime_boundary import audit_file, audit_repository


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_application_route_cannot_import_tool_runtime(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "backend/routes/unsafe.py",
        "from skeleton.skills.tool_runtime import AsyncToolRuntime\n",
    )

    violations = audit_file(path, root=tmp_path)

    assert len(violations) == 1
    assert "direct canonical tool runtime import" in violations[0]


def test_application_route_cannot_import_tool_execution_request(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        "skeleton/api/unsafe.py",
        "from skeleton.skills.tool_contract import ToolExecutionRequest\n",
    )

    violations = audit_file(path, root=tmp_path)

    assert len(violations) == 1
    assert "execution request authority" in violations[0]


def test_declared_tool_registry_owner_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "backend/services/tool_registry.py",
        "from skeleton.skills.tool_runtime import AsyncToolRuntime\n"
        "from skeleton.skills.tool_contract import ToolExecutionRequest\n",
    )

    assert audit_file(path, root=tmp_path) == []


def test_current_repository_has_no_tool_runtime_boundary_violations() -> None:
    assert audit_repository() == []
