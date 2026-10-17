"""Read-only source-linked Dragon follow-up priorities; mock quality checks only."""
from __future__ import annotations

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer import jeeves_game_production as production
from skeleton.testing.test_jeeves_dragon_observer import workspace, cli


def test_queue_identifies_missing_independent_quality_evaluators(tmp_path):
    root = workspace(tmp_path)
    cli(root, "dragon-observe-start", "--consent")
    queue = cli(root, "dragon-observe-review-queue")
    assert queue["ok"], queue
    assert queue["total"] == len(production.REQUIRED_GATES)
    assert queue["source_gate_count"] == len(production.REQUIRED_GATES)
    assert queue["actual_screen_capture"] is False
    assert queue["model_weights_updated"] is False
    assert all(not item["training_promotion_eligible"] for item in queue["items"])
    assert queue["next_page"] is None


def test_missing_witness_receipt_has_safe_reconcile_instruction(tmp_path, monkeypatch):
    root = workspace(tmp_path)
    cli(root, "dragon-observe-start", "--consent")
    monkeypatch.setattr(production, "_probe", lambda *args:
        ("failed", "f" * 64, "canonical_source", "simulated failure"))
    production.cycle(root, passes=1, gate="source_integrity")
    queue = cli(root, "dragon-observe-review-queue", "--page-size", "2")
    assert queue["ok"], queue
    assert queue["unwitnessed_canonical_checks"] == 1
    items = []
    page = 0
    while True:
        batch = cli(root, "dragon-observe-review-queue",
                    "--page", str(page), "--page-size", "2")
        items.extend(batch["items"])
        if batch["next_page"] is None:
            break
        page = batch["next_page"]
    source = next(item for item in items if item["gate"] == "source_integrity")
    assert source["missed_witness_receipts"] == 1
    assert "reconcile" in source["next_action"]
    assert not source["gate_completed_by_this_queue"]
    cli(root, "dragon-observe-sync")
    current = cli(root, "dragon-observe-review-queue")
    assert current["unwitnessed_canonical_checks"] == 0


def test_queue_fails_closed_without_consent_or_on_bad_bounds(tmp_path):
    root = workspace(tmp_path)
    assert not cli(root, "dragon-observe-review-queue")["ok"]
    cli(root, "dragon-observe-start", "--consent")
    assert not cli(root, "dragon-observe-review-queue", "--page-size", "129")["ok"]
    assert not cli(root, "dragon-observe-review-queue", "--page", "-1")["ok"]
    assert cli(root, "dragon-observe-review-queue", "--page", "100")["items"] == []
