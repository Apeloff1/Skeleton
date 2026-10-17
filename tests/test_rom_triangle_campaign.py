"""ROM triangle campaign: fail-closed source reading, dedupe and page retry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.training import rom_triangle_campaign as campaign
from skeleton.ai.training.rom_study import RomStudyError


def test_campaign_receipt_reader_binds_bytes_and_rejects_duplicate_keys(tmp_path):
    source = tmp_path / "receipt.json"
    source.write_text('{"alpha":1,"beta":2}', encoding="utf-8")
    value, digest = campaign.read_receipt_document(source)
    assert value == {"alpha": 1, "beta": 2}
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text('{"alpha":1,"alpha":2}', encoding="utf-8")
    with pytest.raises(RomStudyError, match="duplicate"):
        campaign.read_receipt_document(source)


def test_campaign_receipt_reader_rejects_symlink_and_nonfinite(tmp_path):
    source = tmp_path / "evidence.json"
    source.write_text('{"evidence":NaN}', encoding="utf-8")
    with pytest.raises(RomStudyError, match="invalid"):
        campaign.read_receipt_document(source)
    source.write_text('{"good":true}', encoding="utf-8")
    redirected = tmp_path / "redirect.json"
    redirected.symlink_to(source)
    with pytest.raises(RomStudyError, match="symlink"):
        campaign.read_receipt_document(redirected)


def test_campaign_receipt_reader_rejects_oversized_document(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text('{"large":"abcdefgh"}', encoding="utf-8")
    with pytest.raises(RomStudyError, match="bounded"):
        campaign.read_receipt_document(path, max_bytes=8)


def test_review_name_stable_and_different_for_checkpoint_or_seed():
    base = campaign.review_receipt_name("a" * 64, "b" * 64, "c" * 64, 0, 160)
    assert base.startswith("triangle-review-" + "a" * 16 + "-")
    assert base.endswith(".json")
    assert base == campaign.review_receipt_name(
        "a" * 64, "b" * 64, "c" * 64, 0, 160
    )
    assert base != campaign.review_receipt_name(
        "a" * 64, "b" * 64, "d" * 64, 0, 160
    )
    assert base != campaign.review_receipt_name(
        "a" * 64, "b" * 64, "c" * 64, 1, 160
    )


def _page():
    return {
        "inventory_cursor": None, "next_cursor": "last.gba",
        "finished_inventory": False, "q_policy_training_completed": 1,
        "q_policy_runs_without_updates": 0, "blocked_or_unreviewed": 1,
        "page_results": [
            {
                "relative_path": "original.gb", "source_sha256": "a" * 64,
                "state": "q_policy_updated_with_receipt",
                "receipt_name": "rom-" + "a" * 16 + "-" + "b" * 16 + ".json",
            },
            {
                "relative_path": "unknown.gba", "source_sha256": "c" * 64,
                "state": "no_training_rights_review",
            },
        ],
    }


def test_campaign_runs_adversarial_review_only_on_rights_admitted_native_sources(
    monkeypatch, tmp_path,
):
    calls = []
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())

    def fake_review(path, *, expected_source_sha256, **kwargs):
        calls.append((path.name, expected_source_sha256))
        return {
            "state": "new_local_adversarial_review_executed",
            "review_receipt_name": "triangle-review-synthetic.json",
            "review_digest": "d" * 64,
            "structured_source_bound_passes": 2,
        }
    monkeypatch.setattr(campaign, "review_one_receipt", fake_review)
    result = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
    )
    assert len(calls) == 1
    assert calls[0][1] == "a" * 64
    assert result["model_review_executed_or_replayed"] == 1
    assert result["review_failures_needing_retry"] == 0
    assert result["blocked_or_unreviewed_gameplay"] == 1
    assert result["rows"][1]["adversarial_review_state"] == "not_eligible"
    assert result["production_jeeves_weight_updates"] == 0


def test_campaign_failure_keeps_same_cursor_retry_without_fake_review(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())

    def fail(*args, **kwargs):
        raise ValueError("model context exhausted")
    monkeypatch.setattr(campaign, "review_one_receipt", fail)
    result = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
    )
    assert result["cursor"] is None
    assert result["next_cursor"] == "last.gba"
    assert result["review_failures_needing_retry"] == 1
    assert result["model_review_executed_or_replayed"] == 0
    assert result["rows"][0]["adversarial_review_state"] == "blocked_retry_required"


def test_campaign_rejects_path_smuggling_from_a_training_page(monkeypatch, tmp_path):
    page = _page()
    page["page_results"][0]["receipt_name"] = "../../not-a-real-receipt.json"
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: page)
    with pytest.raises(RomStudyError, match="unsafe receipt"):
        campaign.triangle_campaign_page(
            tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
        )


def test_campaign_rejects_critic_that_did_not_produce_three_grounded_findings(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())

    def incomplete(path, *, expected_source_sha256, **kwargs):
        return {
            "state": "critic_output_incomplete_requires_new_review_configuration",
            "review_receipt_name": "triangle-review-no-grounding.json",
            "review_digest": "e" * 64,
            "structured_source_bound_passes": 0,
        }
    monkeypatch.setattr(campaign, "review_one_receipt", incomplete)
    page = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
    )
    assert page["model_review_executed_or_replayed"] == 0
    assert page["review_failures_needing_retry"] == 1
    assert page["rows"][0]["adversarial_review_state"].startswith("critic_output_incomplete")
