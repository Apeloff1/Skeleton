"""#4109/#4104: contract checkers follow .github/CI_SLIM_POLICY.md.

Archived workflows must not crash a checker; inert archived definitions stay
contract-checked, and moved coverage is enforced on the active replacement.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_slim_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_v2_checks_archived_workflow_when_inactive(tmp_path: Path, monkeypatch) -> None:
    runner = _load("check_runner_v2_contract")
    assert runner.check() == ()
    archived = runner.ARCHIVED_WORKFLOW
    monkeypatch.setattr(runner, "WORKFLOW", tmp_path / "absent.yml")
    assert runner.check() == ()  # validated via the archived definition
    monkeypatch.setattr(runner, "ARCHIVED_WORKFLOW", tmp_path / "also-absent.yml")
    assert any("missing PR automation workflow" in item for item in runner.check())
    assert archived.is_file()


def test_toolchain_requires_active_dependency_review_replacement() -> None:
    toolchain = _load("check_toolchain_contract")
    assert toolchain.main() == 0
    review = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")
    for marker in toolchain.DEPENDENCY_REVIEW_MARKERS:
        assert marker in review
