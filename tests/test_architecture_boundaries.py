from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_boundaries import collect_violations


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "skeleton" / "testing").mkdir(parents=True)
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    return tmp_path


def test_repository_respects_enforced_architecture_boundaries() -> None:
    assert collect_violations(REPO_ROOT, require_roots=True) == []


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


def test_deployment_harness_is_exact_api_composition_root(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/deploy/harness.py", "from skeleton.api import create_app\n")

    assert collect_violations(tmp_path) == []


def test_other_deployment_modules_cannot_import_api(tmp_path: Path) -> None:
    _write(tmp_path, "skeleton/deploy/worker.py", "from skeleton.api import create_app\n")

    violations = collect_violations(tmp_path)

    assert len(violations) == 1
    assert "must not depend upward on skeleton.api" in violations[0].message


def test_skeleton_production_rejects_backend_frontend_and_test_roots(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "skeleton/domain.py",
        "import backend.server\nfrom frontend.client import UI\nimport tests.fixtures\n",
    )

    messages = [item.message for item in collect_violations(root)]

    assert any("backend.server" in message for message in messages)
    assert any("frontend.client" in message for message in messages)
    assert any("tests.fixtures" in message for message in messages)


def test_backend_production_rejects_frontend_and_test_only_roots(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "backend/app.py",
        "from frontend.client import UI\nfrom skeleton.testing import helper\nimport tests.fixtures\n",
    )

    messages = [item.message for item in collect_violations(root)]

    assert any("frontend.client" in message for message in messages)
    assert any("skeleton.testing" in message for message in messages)
    assert any("tests.fixtures" in message for message in messages)


def test_test_trees_are_exempt_from_production_direction_rules(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/testing/probe.py", "import backend.server\nfrom skeleton.api import routes\n")
    _write(root, "backend/tests/probe.py", "from skeleton.testing import helper\nimport tests.fixtures\n")

    assert collect_violations(root) == []


def test_namespace_matching_does_not_reject_prefix_lookalikes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/domain.py", "import backendish\nimport testsmith\n")
    _write(root, "backend/app.py", "import frontendish\nimport skeleton.testingly\n")

    assert collect_violations(root) == []


def test_relative_imports_do_not_cross_repository_roots(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/pkg/module.py", "from . import helper\nfrom .. import architecture\n")

    assert collect_violations(root) == []


def test_parse_failure_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/broken.py", "def broken(:\n")

    violations = collect_violations(root)

    assert any("cannot validate Python module: SyntaxError" in item.message for item in violations)


def test_missing_canonical_root_fails_closed_when_required(tmp_path: Path) -> None:
    (tmp_path / "skeleton").mkdir()

    violations = collect_violations(tmp_path, require_roots=True)

    assert any(
        item.path == tmp_path / "backend" and item.message == "missing canonical source root"
        for item in violations
    )


def test_staged_exact_api_mirror_may_reference_legacy_api_until_cutover(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/api/routes.py", "VALUE = 1\n")
    _write(root, "skeleton/ai/runtime/api/routes.py", "from skeleton.api import routes\n")
    _write(
        root,
        "machine/ai_file_tree.json",
        """{
  "status": "staged_mirror",
  "mappings": [
    {
      "source": "skeleton/api",
      "destination": "skeleton/ai/runtime/api",
      "parity_mode": "exact"
    }
  ]
}
""",
    )

    assert collect_violations(root) == []


def test_completed_or_nonexact_api_mirror_does_not_bypass_boundary(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/api/routes.py", "VALUE = 1\n")
    _write(root, "skeleton/ai/runtime/api/routes.py", "from skeleton.api import routes\n")
    _write(
        root,
        "machine/ai_file_tree.json",
        """{
  "status": "cutover_complete",
  "mappings": [
    {
      "source": "skeleton/api",
      "destination": "skeleton/ai/runtime/api",
      "parity_mode": "exact"
    }
  ]
}
""",
    )

    violations = collect_violations(root)
    assert len(violations) == 1
    assert "must not depend upward on skeleton.api" in violations[0].message
