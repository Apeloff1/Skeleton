"""Regression contract: canonical AI-tree admission runs before costly suites."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ai_tree_preflight_runs_once_before_provider_and_architecture() -> None:
    script = (ROOT / "scripts/quality-gates.sh").read_text(encoding="utf-8")
    ai_tree = "python scripts/check_ai_file_tree.py"
    provider = "python scripts/check_provider_runtime_boundary.py"
    architecture = "python scripts/check_architecture_boundaries.py"
    assert script.count(ai_tree) == 1
    assert script.count(provider) == 1
    assert script.count(architecture) == 1
    assert (
        script.index("python scripts/check_toolchain_contract.py")
        < script.index("python scripts/check_quality_gate_parity.py")
        < script.index(ai_tree)
        < script.index(provider)
        < script.index(architecture)
    )
    # Both fail-closed validator and parity suite still execute exactly once.
    assert script.count("skeleton/testing/test_ai_file_tree.py") == 1
    assert script.count("skeleton/testing/test_ci_ai_tree_failfast.py") == 1
