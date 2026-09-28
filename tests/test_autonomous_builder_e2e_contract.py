from __future__ import annotations

from pathlib import Path

from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.secretary import route

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC = ROOT / ".github" / "workflows" / "automation-traffic-manager.yml"
SUPERVISOR = ROOT / ".github" / "workflows" / "supervisor.yml"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scheduled_admission_reaches_exact_head_supervisor() -> None:
    traffic = _source(TRAFFIC)
    supervisor = _source(SUPERVISOR)
    assert 'cron: "*/10 * * * *"' in traffic
    assert '[[ "$live_sha" != "$TRAFFIC_ADMITTED_BASE_SHA" ]]' in traffic
    assert '-f "expected_base_sha=$TRAFFIC_ADMITTED_BASE_SHA"' in traffic
    assert "SUPERVISOR_CALLER_BASE_SHA: ${{ inputs.expected_base_sha }}" in supervisor
    assert 'test "$SUPERVISOR_BASE_SHA" = "$SUPERVISOR_CALLER_BASE_SHA"' in supervisor


def test_authorized_build_cannot_be_suppressed_by_model_wording() -> None:
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route(
        "no feature or implementation keywords are required here",
        due,
        build_authorization=object(),
    )
    assert "feature-builder" in selected


def test_execution_chain_preserves_fail_closed_authority_boundary() -> None:
    supervisor = _source(SUPERVISOR)
    assert "permissions: {}" in supervisor.split("jobs:", 1)[0]
    assert "contents: write" not in supervisor.split("  plan:", 1)[1].split("  secretary:", 1)[0]
    secretary = supervisor.split("  secretary:", 1)[1]
    assert "contents: write" in secretary
    assert "SUPERVISOR_DELEGATION_B64" in secretary
    assert "python -m skeleton.automation.secretary" in secretary


def test_operator_contract_documents_terminal_and_recovery_states() -> None:
    source = (ROOT / "docs" / "AUTONOMOUS_BUILDER_OPERATIONS.md").read_text(encoding="utf-8")
    for marker in (
        "capacity-suppressed",
        "missing-demand",
        "provider-failure",
        "stale-custody",
        "validation-failure",
        "publication-failure",
        "pull-request-created",
        "existing-pr",
    ):
        assert marker in source
