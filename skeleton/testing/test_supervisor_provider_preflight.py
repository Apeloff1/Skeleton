"""Fail-closed configuration admission for repository Supervisor workers."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "supervisor.yml"
MODEL = ROOT / "skeleton" / "automation" / "free_model.py"


def test_secretary_requires_model_provider_before_any_worker_dispatch() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    secretary = text.split("\n  secretary:\n", 1)[1]
    preflight = secretary.index(
        "- name: Require configured repository automation provider"
    )
    checkout = secretary.index("- name: Checkout immutable admitted commit")
    dispatch = secretary.index("- name: Admit delegation and dispatch bounded workers")
    assert preflight < checkout < dispatch
    assert "set -euo pipefail" in secretary[preflight:checkout]
    assert "configuration_required:" in secretary[preflight:checkout]
    for name in ("MODEL_API_URL", "MODEL_NAME", "MODEL_API_KEY"):
        assert f'-z "${{{name}:-}}"' in secretary[preflight:checkout]


def test_preflight_does_not_disclose_credentials_or_disable_read_only_plan() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    plan, secretary = text.split("\n  secretary:\n", 1)
    assert "permissions: {}" in plan
    assert "contents: read" in plan
    assert "MODEL_API_KEY: ${{ secrets.MODEL_API_KEY }}" in secretary
    preflight = secretary.split(
        "- name: Require configured repository automation provider", 1
    )[1].split("- name: Checkout immutable admitted commit", 1)[0]
    assert "echo \"$MODEL_API_KEY\"" not in preflight
    assert "printenv" not in preflight
    assert "exit 1" in preflight


def test_automation_model_provider_requires_all_three_fields() -> None:
    source = MODEL.read_text(encoding="utf-8")
    for name in ("MODEL_API_URL", "MODEL_NAME", "MODEL_API_KEY"):
        assert name in source
    assert "MODEL_API_URL, MODEL_API_KEY and MODEL_NAME are required" in source
