from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "backend-quality.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_backend_quality_has_fail_closed_plan_only_classifier() -> None:
    text = _workflow()
    assert "Classify backend-quality scope" in text
    assert 'BASE_REF: ${{ github.base_ref }}' in text
    assert 'git fetch --no-tags --depth=1 origin "$BASE_REF"' in text
    assert 'current_base="$(git rev-parse FETCH_HEAD)"' in text
    assert 'docs/plan/*|machine/ai_master_plan.json|scripts/check_ai_master_plan.py|skeleton/testing/test_ai_master_plan.py)' in text
    assert 'if [ "${#changed[@]}" -eq 0 ]; then' in text
    assert 'echo "full=true" >> "$GITHUB_OUTPUT"' in text
    assert 'echo "plan_only=true" >> "$GITHUB_OUTPUT"' in text


def test_plan_only_lane_runs_only_masterplan_validation() -> None:
    text = _workflow()
    assert "Install plan-only quality runtime" in text
    assert "Validate plan-only masterplan contract" in text
    assert "python scripts/check_ai_master_plan.py" in text
    assert "python -m pytest -q --noconftest skeleton/testing/test_ai_master_plan.py" in text


def test_heavy_backend_quality_steps_remain_full_scope_only() -> None:
    text = _workflow()
    heavy_steps = (
        "Ruff lint",
        "Syntax check (full backend)",
        "Canonical local/CI quality parity gate",
        "Canonical architecture boundary gate",
        "Provider runtime boundary gate",
        "Security scanner and capability fail-closed contracts",
        "Repository malware and IOC gate",
        "Security, provider-chaos, and developer-tooling adversarial regression tests",
    )
    for name in heavy_steps:
        marker = f"- name: {name}\n        if: steps.scope.outputs.full == 'true'"
        assert marker in text, name
