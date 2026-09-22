from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CACHE_SHA = "0057852bfaa89a56745cba8c7296529d2fc39830"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_mutating_bot_workflows_do_not_persist_checkout_credentials() -> None:
    for name in ("repo-bots.yml", "secretary.yml"):
        text = _text(name)
        assert "persist-credentials: false" in text
        assert "persist-credentials: true" not in text


def test_bot_state_restore_and_failure_safe_save_are_pinned() -> None:
    for name in ("repo-bots.yml", "secretary.yml"):
        text = _text(name)
        assert f"actions/cache/restore@{CACHE_SHA}" in text
        assert f"actions/cache/save@{CACHE_SHA}" in text
        assert "if: always()" in text
        assert "path: .skeleton-bot-state.json" in text
        assert "skeleton-bot-state-${{ github.repository_id }}-" in text


def test_manager_is_restore_only_and_read_only() -> None:
    text = _text("bot-manager.yml")
    assert f"actions/cache/restore@{CACHE_SHA}" in text
    assert "actions/cache/save@" not in text
    assert "contents: read" in text
    assert "contents: write" not in text


def test_repo_bot_workflow_uses_single_bounded_dispatch_lane() -> None:
    text = _text("repo-bots.yml")
    assert "matrix:" not in text
    assert 'python -m skeleton.automation.repo_bots --mode "$BOT_MODE"' in text
    assert "cancel-in-progress: true" in text
    assert "actions: read" in text
    assert "issues: read" in text
    assert "pull-requests: write" in text
