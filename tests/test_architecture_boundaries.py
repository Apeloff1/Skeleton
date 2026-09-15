from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_boundaries import collect_violations


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repository_respects_enforced_architecture_boundaries() -> None:
    assert collect_violations(REPO_ROOT) == []


def test_kernel_rejects_framework_and_io_dependencies(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/kernel/example.py", "import fastapi\nimport sqlalchemy\n")

    violations = collect_violations(tmp_path)

    assert len(violations) == 2
    assert all("kernel must not import framework/I/O dependency" in item.message for item in violations)


def test_domain_code_rejects_absolute_api_reverse_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/jeeves/example.py", "from skeleton.api import routes\n")

    violations = collect_violations(tmp_path)

    assert len(violations) == 1
    assert "must not depend upward on skeleton.api" in violations[0].message


def test_domain_code_rejects_relative_api_reverse_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/agents/example.py", "from ..api import routes\n")

    violations = collect_violations(tmp_path)

    assert len(violations) == 1
    assert "must not depend upward on skeleton.api" in violations[0].message


def test_api_adapter_may_depend_on_lower_level_contracts(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/api/routes.py", "from skeleton.kernel import events\n")

    assert collect_violations(tmp_path) == []


def test_cli_entry_may_wire_the_api_adapter(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/__main__.py", "from skeleton.api import create_app\n")

    assert collect_violations(tmp_path) == []
