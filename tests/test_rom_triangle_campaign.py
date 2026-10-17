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



def _fake_semantic_route(episode, *, max_lenses=43):
    from skeleton.jeeves.game_emulator_triangle_semantics import SEMANTIC_LENS_BUDGET
    assert max_lenses == SEMANTIC_LENS_BUDGET
    return {
        "source_native_trace_sha256": episode["source_trace_sha256"],
        "canonical_catalog_sha256": "9" * 64,
        "route_digest": "8" * 64,
        "observation_fingerprints": ["7" * 64],
        "actually_routed_lenses": SEMANTIC_LENS_BUDGET,
        "routes": [{
            "lens_key": "authored_lens_" + str(i),
            "lens_family": "game", "activation_score": 0.7,
            "question": "Which source evidence could falsify this lens?",
        } for i in range(SEMANTIC_LENS_BUDGET)],
    }


def _synthetic_corpus_inputs():
    from skeleton.jeeves.game_emulator_triangle import LENSES
    evidence = {
        "report_digest": "a" * 64,
        "source_lineage": {
            "rights_acknowledged": True, "source_sha256": "b" * 64,
            "rights_review_id": "independent-review-example",
        },
    }
    triangle = {
        "triangle_digest": "c" * 64,
        "episode_lens_references": [{
            "source_trace_sha256": "d" * 64,
            "source_receipt_sha256": "e" * 64,
            "unique_source_transitions": 17,
            "grounded_lens_evidence": {
                name: {"measurement": i, "verified": True}
                for i, name in enumerate(LENSES)
            },
        }],
    }
    review = {
        "review_digest": "f" * 64,
        "structured_source_bound_passes": 3,
        "passes": [{
            "response": "UNTRUSTED_CRITIC_SENTINEL_NEVER_TRAIN_ON_ME",
        }],
    }
    return evidence, triangle, review


def test_weighted_eight_lens_candidate_corpus_never_multiplies_native_games(
    monkeypatch,
):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    from skeleton.jeeves.game_emulator_triangle import LENSES
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    evidence, triangle, review = _synthetic_corpus_inputs()
    result = corpus.compile_triangle_candidate_corpus(evidence, triangle, review)
    assert result["unique_independent_native_episodes"] == 1
    assert result["total_lens_candidate_views"] == len(LENSES) == 8
    assert result["canonical_semantic_lens_selection_budget"] == 43
    assert result["routed_semantic_lens_questions"] == 43
    assert len(result["semantic_routes_per_episode"][0]["semantic_questions"]) == 43
    assert all(question["factual_label_available"] is False
               for question in result["semantic_routes_per_episode"][0]["semantic_questions"])
    assert result["semantic_questions_are_not_supervised_labels"] is True
    assert result["additional_independent_gameplay_episodes_from_lenses"] == 0
    assert result["same_source_total_weight_per_episode"] == 1
    assert all(row["same_source_view_weight"] == {"numerator": 1, "denominator": 8}
               for row in result["candidate_rows"])
    assert all(row["not_for_heldout_evaluation"] for row in result["candidate_rows"])
    assert all("UNTRUSTED_CRITIC_SENTINEL" not in row["answer"]
               for row in result["candidate_rows"])
    assert result["production_jeeves_optimizer_steps"] == 0
    corpus.verify_triangle_candidate_corpus(evidence, triangle, review, result)


def test_corpus_cannot_train_on_unstructured_critic_or_unreviewed_rom(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    evidence, triangle, review = _synthetic_corpus_inputs()
    review["structured_source_bound_passes"] = 2
    with pytest.raises(corpus.TriangleCorpusError, match="three"):
        corpus.compile_triangle_candidate_corpus(evidence, triangle, review)
    review["structured_source_bound_passes"] = 3
    evidence["source_lineage"]["rights_acknowledged"] = False
    with pytest.raises(corpus.TriangleCorpusError, match="rights"):
        corpus.compile_triangle_candidate_corpus(evidence, triangle, review)


def test_corpus_rejects_corrupted_lens_or_falsified_candidate_output(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    evidence, triangle, review = _synthetic_corpus_inputs()
    candidate = corpus.compile_triangle_candidate_corpus(evidence, triangle, review)
    candidate["candidate_rows"][0]["answer"] = "Invented win and fake gameplay."
    with pytest.raises(corpus.TriangleCorpusError, match="digest"):
        corpus.verify_triangle_candidate_corpus(evidence, triangle, review, candidate)
    triangle["episode_lens_references"][0]["grounded_lens_evidence"].pop("visual_state")
    with pytest.raises(corpus.TriangleCorpusError, match="eight"):
        corpus.compile_triangle_candidate_corpus(evidence, triangle, review)


def test_operator_parser_exposes_unified_campaign_and_reviewed_corpus():
    from scripts.training.rom_study import parser
    root = parser()
    parsed = root.parse_args([
        "train-triangle", "--root", "/tmp/roms", "--approvals", "/tmp/approval.json",
        "--output-dir", "/tmp/receipts", "--reviewer-checkpoint", "/tmp/reviewer.json",
        "--snapshot", "/tmp/frozen.json",
    ])
    assert parsed.operation == "train-triangle"
    assert parsed.max_pages == 1
    second = root.parse_args([
        "export-triangle-corpus", "--receipt", "/tmp/rom.json",
        "--review-receipt", "/tmp/critic.json",
        "--source-sha256", "0" * 64, "--reviewer-checkpoint", "/tmp/model.json",
        "--output-dir", "/tmp/out",
    ])
    assert second.operation == "export-triangle-corpus"
