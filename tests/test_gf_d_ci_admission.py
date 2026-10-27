"""Fail-closed CI admission contracts for GF-D native Godot certification."""
from pathlib import Path

from scripts.check_ci_workflow_tiers import events, independently_triggered

ROOT = Path(__file__).resolve().parents[1]


def test_reusable_native_engine_stays_attached_to_existing_pr_validation() -> None:
    native = (ROOT / ".github/workflows/game-frontier-native-smoke.yml").read_text()
    focused = (ROOT / ".github/workflows/game-frontier-validation.yml").read_text()
    assert events(native) == {"workflow_call", "workflow_dispatch"}
    assert "  pull_request:" not in native
    assert "    uses: ./.github/workflows/game-frontier-native-smoke.yml" in focused
    for path in (
        "scripts/certify_game_frontier_godot_import.py",
        "scripts/run_game_frontier_gfd_native_checks.py",
        "tests/test_gf_d_godot_import_cert.py",
        "tests/test_game_frontier_gfd_native_checks.py",
        ".github/workflows/game-frontier-native-smoke.yml",
    ):
        assert path in focused
    assert "Fetch official pinned Godot 4.7.2 standard Linux archive" in native
    assert "GF-D headless import + RigidBody3D/SoftBody3D native probe" in native


def test_independent_admission_cap_does_not_ignore_event_subscribers() -> None:
    assert not independently_triggered({"workflow_call", "workflow_dispatch"})
    assert not independently_triggered({"workflow_dispatch"})
    assert independently_triggered({"pull_request", "workflow_dispatch"})
    assert independently_triggered({"push"})
    assert independently_triggered({"schedule", "workflow_call"})
