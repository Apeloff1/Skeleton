"""Tests for the repository's immutable GitHub Actions reference policy."""
from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_github_actions_pinning.py"
_spec = importlib.util.spec_from_file_location("check_github_actions_pinning", _SCRIPT)
assert _spec and _spec.loader
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


def test_accepts_full_commit_sha() -> None:
    assert module.validate_target("actions/checkout@11d5960a326750d5838078e36cf38b85af677262") is None


def test_rejects_mutable_tag() -> None:
    assert module.validate_target("actions/checkout@v4") is not None


def test_rejects_branch_ref() -> None:
    assert module.validate_target("owner/action@main") is not None


def test_rejects_missing_ref() -> None:
    assert module.validate_target("owner/action") is not None


def test_scanner_ignores_local_and_docker_actions(tmp_path: Path) -> None:
    workflow = tmp_path / "local.yml"
    workflow.write_text(
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - uses: ./local-action\n"
        "      - uses: docker://alpine:3.20\n",
        encoding="utf-8",
    )

    assert module.scan_workflows(tmp_path) == []


def test_scanner_reports_mutable_external_ref(tmp_path: Path) -> None:
    workflow = tmp_path / "bad.yml"
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )

    violations = module.scan_workflows(tmp_path)
    assert len(violations) == 1
    assert "actions/checkout@v4" in violations[0]


def test_repository_workflows_are_all_immutable() -> None:
    assert module.scan_workflows() == []
