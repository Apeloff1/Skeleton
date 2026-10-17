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



def _fake_semantic_route(episode, *, max_lenses=43, requested_keys=()):
    from skeleton.jeeves.game_emulator_triangle_semantics import SEMANTIC_LENS_BUDGET
    assert max_lenses == SEMANTIC_LENS_BUDGET
    return {
        "source_native_trace_sha256": episode["source_trace_sha256"],
        "canonical_catalog_sha256": "9" * 64,
        "route_digest": "8" * 64,
        "observation_fingerprints": ["7" * 64],
        "actually_routed_lenses": SEMANTIC_LENS_BUDGET,
        "governance_fingerprint": "a" * 64,
        "selection_mode": "operator_exact_43" if requested_keys else "canonical_dynamic_router",
        "routes": [{
            "lens_key": "authored_lens_" + str(i),
            "lens_family": "game", "activation_score": 0.7,
            "question": "Which source evidence could falsify this lens?",
            "governance_grade": "heuristic",
            "governance_fingerprint": "f" * 64,
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



def test_strict_43_key_operator_manifest(tmp_path):
    from skeleton.ai.training.rom_triangle_campaign import load_operator_semantic_lens_set
    source = tmp_path / "semantic-keys.json"
    keys = ["lens_" + str(i) for i in range(43)]
    source.write_text(json.dumps({
        "schema_version": "skeleton.jeeves.semantic_lens_set.v1",
        "lens_keys": keys,
    }), encoding="utf-8")
    assert load_operator_semantic_lens_set(source) == tuple(keys)
    source.write_text(json.dumps({
        "schema_version": "skeleton.jeeves.semantic_lens_set.v1",
        "lens_keys": keys[:-1] + [keys[0]],
    }), encoding="utf-8")
    with pytest.raises(RomStudyError, match="43 or 200"):
        load_operator_semantic_lens_set(source)


def test_candidate_corpus_pins_requested_semantic_lens_keys(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    evidence, triangle, review = _synthetic_corpus_inputs()
    keys = tuple("authored_lens_" + str(i) for i in range(43))
    result = corpus.compile_triangle_candidate_corpus(
        evidence, triangle, review,
        requested_semantic_lens_keys=keys,
    )
    assert result["operator_requested_semantic_lens_keys"] == list(keys)
    assert result["semantic_routes_per_episode"][0]["selection_mode"] == "operator_exact_43"
    assert len(result["semantic_lens_selection_digest"]) == 64
    assert all(not item["factual_claims_allowed"]
               for item in result["semantic_routes_per_episode"][0]["semantic_questions"])
    corpus.verify_triangle_candidate_corpus(evidence, triangle, review, result)


def test_corpus_v3_tracks_real_43_lens_receipt_as_provenance_only(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    from skeleton.jeeves import game_emulator_triangle_semantic_inference as infer
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    monkeypatch.setattr(infer, "verify_native_semantic_lenses", lambda *a: None)
    evidence, triangle, critic = _synthetic_corpus_inputs()
    semantic = {
        "source_native_trace_sha256": "d" * 64,
        "canonical_route_sha256": _fake_semantic_route(
            triangle["episode_lens_references"][0],
        )["route_digest"],
        "semantic_review_digest": "1" * 64,
        "model_sha256": "2" * 64,
        "source_bound_interpretations": 43,
        "all_semantic_interpretations_valid": True,
        "native_model_generations_executed": 43,
        "requested_lens_keys": [],
        "entries": [{
            "response": "UNTRUSTED_SEMANTIC_HYPOTHESIS_NOT_A_TARGET_LABEL",
        }],
    }
    result = corpus.compile_triangle_candidate_corpus(
        evidence, triangle, critic, semantic_inference_review=semantic,
    )
    assert result["schema_version"].endswith("candidate_corpus.v3")
    assert result["native_semantic_inference_reference"]["source_bound_hypotheses"] == 43
    assert result["semantic_model_hypotheses_added_to_supervised_labels"] == 0
    assert result["additional_independent_gameplay_episodes_from_lenses"] == 0
    assert all("UNTRUSTED_SEMANTIC_HYPOTHESIS" not in row["answer"]
               for row in result["candidate_rows"])
    corpus.verify_triangle_candidate_corpus(
        evidence, triangle, critic, result, semantic_inference_review=semantic,
    )
    with pytest.raises(corpus.TriangleCorpusError):
        corpus.verify_triangle_candidate_corpus(evidence, triangle, critic, result)


def test_cli_corpus_review_receipt_requires_checkpoint_pair():
    from scripts.training.rom_study import parser
    args = parser().parse_args([
        "export-triangle-corpus",
        "--receipt", "/tmp/gameplay.json",
        "--review-receipt", "/tmp/critic.json",
        "--source-sha256", "a" * 64,
        "--reviewer-checkpoint", "/tmp/critic-model.json",
        "--semantic-review-receipt", "/tmp/semantic.json",
        "--semantic-checkpoint", "/tmp/semantic-model.json",
        "--output-dir", "/tmp/private",
    ])
    assert [path.name for path in args.semantic_review_receipt] == ["semantic.json"]
    assert args.semantic_checkpoint.name == "semantic-model.json"



def test_full_triangle_campaign_executes_43_per_source_episode(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())
    monkeypatch.setattr(campaign, "review_one_receipt", lambda *a, **k: {
        "state": "new_local_adversarial_review_executed",
        "review_receipt_name": "triangle-review-a.json",
        "review_digest": "f" * 64,
        "structured_source_bound_passes": 3,
    })
    monkeypatch.setattr(campaign, "read_receipt_document", lambda *a, **k: ({
        "training_triangle": {
            "episode_lens_references": [
                {"source_trace_sha256": "a" * 64},
                {"source_trace_sha256": "b" * 64},
            ],
        },
    }, "c" * 64))
    seen = []

    def fake_semantic(*a, run_index, requested_keys, seed, **kw):
        seen.append((run_index, tuple(requested_keys), seed))
        return {
            "filename": "semantic-43-" + str(run_index) + ".json",
            "semantic_review_digest": f"{run_index + 1:064x}",
            "native_model_lens_generations": 43,
            "cue_supported_lenses": 20,
            "hypothesis_only_lenses": 23,
            "source_referenced_interpretations": 43,
            "all_lens_interpretations_valid": True,
        }

    monkeypatch.setattr(campaign, "execute_native_43_lens_review", fake_semantic)
    result = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
        semantic_runtime=object(), semantic_all_runs=True, semantic_seed=110,
        semantic_lens_keys=tuple("lens_" + str(i) for i in range(43)),
    )
    assert seen == [(0, tuple("lens_" + str(i) for i in range(43)), 110),
                    (1, tuple("lens_" + str(i) for i in range(43)), 153)]
    assert result["semantic_model_generations_executed_or_replayed"] == 86
    assert result["review_failures_needing_retry"] == 0
    assert result["rows"][0]["semantic_episode_count"] == 2
    assert result["rows"][0]["semantic_lens_review_state"] == "43_lenses_native_executed_or_replayed"
    assert result["rows"][1]["semantic_model_generations"] == 0
    assert result["production_jeeves_weight_updates"] == 0


def test_semantic_campaign_failure_blocks_page_advancement(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())
    monkeypatch.setattr(campaign, "review_one_receipt", lambda *a, **k: {
        "state": "prior_local_adversarial_review_replayed",
        "review_receipt_name": "triangle-review-a.json",
        "review_digest": "f" * 64,
        "structured_source_bound_passes": 3,
    })
    monkeypatch.setattr(campaign, "read_receipt_document", lambda *a, **k: ({
        "training_triangle": {"episode_lens_references": [{}]},
    }, "c" * 64))

    def fail(*a, **k):
        raise ValueError("native semantic model timed out")

    monkeypatch.setattr(campaign, "execute_native_43_lens_review", fail)
    page = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
        semantic_runtime=object(),
    )
    assert page["review_failures_needing_retry"] == 1
    assert page["semantic_lens_review_failures_needing_retry"] == 1
    assert page["rows"][0]["semantic_lens_review_state"] == "blocked_retry_required"
    assert page["semantic_model_generations_executed_or_replayed"] == 0


def test_campaign_cli_accepts_semantic_model_and_all_episode_mode():
    from scripts.training.rom_study import parser
    flags = parser().parse_args([
        "train-triangle", "--root", "/tmp/roms", "--approvals", "/tmp/rights",
        "--output-dir", "/tmp/receipts", "--snapshot", "/tmp/snapshot",
        "--reviewer-checkpoint", "/tmp/critic",
        "--semantic-checkpoint", "/tmp/semantic",
        "--semantic-all-runs", "--semantic-seed", "112",
    ])
    assert flags.semantic_all_runs is True
    assert flags.semantic_seed == 112
    assert flags.semantic_checkpoint.name == "semantic"


def test_semantic_corpus_requires_all_43_source_linked_interpretations(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    from skeleton.jeeves import game_emulator_triangle_semantic_inference as infer
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    monkeypatch.setattr(infer, "verify_native_semantic_lenses", lambda *a: None)
    evidence, triangle, critic = _synthetic_corpus_inputs()
    semantic = {
        "source_native_trace_sha256": "d" * 64,
        "canonical_route_sha256": _fake_semantic_route(
            triangle["episode_lens_references"][0]
        )["route_digest"],
        "semantic_review_digest": "1" * 64,
        "model_sha256": "2" * 64,
        "requested_lens_keys": [],
        "native_model_generations_executed": 43,
        "source_bound_interpretations": 42,
        "all_semantic_interpretations_valid": False,
    }
    with pytest.raises(corpus.TriangleCorpusError, match="all 43"):
        corpus.compile_triangle_candidate_corpus(
            evidence, triangle, critic, semantic_inference_review=semantic,
        )
    semantic["source_bound_interpretations"] = 43
    semantic["all_semantic_interpretations_valid"] = True
    semantic["native_model_generations_executed"] = 42
    with pytest.raises(corpus.TriangleCorpusError, match="all 43"):
        corpus.compile_triangle_candidate_corpus(
            evidence, triangle, critic, semantic_inference_review=semantic,
        )


def test_campaign_retries_partial_43_lens_interpretations(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())
    monkeypatch.setattr(campaign, "review_one_receipt", lambda *a, **k: {
        "state": "new_local_adversarial_review_executed",
        "review_receipt_name": "triangle-review-a.json",
        "review_digest": "f" * 64,
        "structured_source_bound_passes": 3,
    })
    monkeypatch.setattr(campaign, "read_receipt_document", lambda *a, **k: ({
        "training_triangle": {"episode_lens_references": [{}]},
    }, "c" * 64))
    monkeypatch.setattr(campaign, "execute_native_43_lens_review", lambda *a, **k: {
        "filename": "semantic-43-one-incomplete.json",
        "semantic_review_digest": "e" * 64,
        "native_model_lens_generations": 43,
        "cue_supported_lenses": 10,
        "hypothesis_only_lenses": 33,
        "source_referenced_interpretations": 42,
        "all_lens_interpretations_valid": False,
    })
    page = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
        semantic_runtime=object(),
    )
    assert page["review_failures_needing_retry"] == 1
    assert page["semantic_lens_review_failures_needing_retry"] == 1
    assert page["semantic_model_generations_executed_or_replayed"] == 43
    assert page["rows"][0]["semantic_lens_review_state"] == (
        "incomplete_semantic_interpretations_retry_required"
    )
    assert page["rows"][0]["structured_semantic_interpretations"] == 42


def test_campaign_rejects_fake_43_lens_count(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "train_page", lambda *a, **k: _page())
    monkeypatch.setattr(campaign, "review_one_receipt", lambda *a, **k: {
        "state": "prior_local_adversarial_review_replayed",
        "review_receipt_name": "triangle-review-a.json",
        "review_digest": "f" * 64,
        "structured_source_bound_passes": 3,
    })
    monkeypatch.setattr(campaign, "read_receipt_document", lambda *a, **k: ({
        "training_triangle": {"episode_lens_references": [{}]},
    }, "c" * 64))
    monkeypatch.setattr(campaign, "execute_native_43_lens_review", lambda *a, **k: {
        "filename": "bad-semantic.json",
        "semantic_review_digest": "e" * 64,
        "native_model_lens_generations": 40,
        "cue_supported_lenses": 15,
        "hypothesis_only_lenses": 28,
        "source_referenced_interpretations": 43,
        "all_lens_interpretations_valid": True,
    })
    page = campaign.triangle_campaign_page(
        tmp_path, tmp_path / "approvals.json", tmp_path / "receipts", object(),
        semantic_runtime=object(),
    )
    assert page["review_failures_needing_retry"] == 1
    assert page["rows"][0]["semantic_lens_review_state"] == "blocked_retry_required"


def test_all_episode_semantic_corpus_v4_is_source_ordered_and_weight_stable(
    monkeypatch,
):
    from copy import deepcopy
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    from skeleton.jeeves import game_emulator_triangle_semantic_inference as infer
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    monkeypatch.setattr(infer, "verify_native_semantic_lenses", lambda *a: None)
    evidence, triangle, critic = _synthetic_corpus_inputs()
    second = deepcopy(triangle["episode_lens_references"][0])
    second["source_trace_sha256"] = "1" * 64
    second["source_receipt_sha256"] = "2" * 64
    triangle["episode_lens_references"].append(second)
    first_review = {
        "source_native_trace_sha256": "d" * 64,
        "canonical_route_sha256": "8" * 64,
        "semantic_review_digest": "3" * 64,
        "model_sha256": "9" * 64,
        "source_bound_interpretations": 43,
        "all_semantic_interpretations_valid": True,
        "native_model_generations_executed": 43,
        "requested_lens_keys": [],
    }
    second_review = {
        **first_review,
        "source_native_trace_sha256": "1" * 64,
        "semantic_review_digest": "4" * 64,
    }
    multi = (second_review, first_review)
    corpus_result = corpus.compile_triangle_candidate_corpus(
        evidence, triangle, critic, semantic_inference_reviews=multi,
    )
    assert corpus_result["schema_version"].endswith("candidate_corpus.v4")
    assert corpus_result["unique_independent_native_episodes"] == 2
    assert corpus_result["total_lens_candidate_views"] == 16
    assert corpus_result["same_source_total_weight_per_episode"] == 1.0
    assert corpus_result["additional_independent_gameplay_episodes_from_lenses"] == 0
    assert [
        item["native_trace_sha256"]
        for item in corpus_result["native_semantic_inference_references"]
    ] == ["d" * 64, "1" * 64]
    assert corpus_result["semantic_model_hypotheses_added_to_supervised_labels"] == 0
    corpus.verify_triangle_candidate_corpus(
        evidence, triangle, critic, corpus_result, semantic_inference_reviews=multi,
    )
    with pytest.raises(corpus.TriangleCorpusError, match="duplicate"):
        corpus.compile_triangle_candidate_corpus(
            evidence, triangle, critic,
            semantic_inference_reviews=(first_review, first_review),
        )


def test_multi_episode_semantic_corpus_rejects_missing_or_incomplete_reviews(
    monkeypatch,
):
    from copy import deepcopy
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    from skeleton.jeeves import game_emulator_triangle_semantic_inference as infer
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", _fake_semantic_route)
    monkeypatch.setattr(infer, "verify_native_semantic_lenses", lambda *a: None)
    evidence, triangle, critic = _synthetic_corpus_inputs()
    other = deepcopy(triangle["episode_lens_references"][0])
    other["source_trace_sha256"] = "1" * 64
    triangle["episode_lens_references"].append(other)
    review = {
        "source_native_trace_sha256": "d" * 64,
        "canonical_route_sha256": "8" * 64,
        "semantic_review_digest": "3" * 64,
        "model_sha256": "9" * 64,
        "source_bound_interpretations": 43,
        "all_semantic_interpretations_valid": True,
        "native_model_generations_executed": 43,
        "requested_lens_keys": [],
    }
    with pytest.raises(corpus.TriangleCorpusError, match="one review"):
        corpus.compile_triangle_candidate_corpus(
            evidence, triangle, critic, semantic_inference_reviews=(review,),
        )
    bad = {**review, "source_native_trace_sha256": "1" * 64,
           "source_bound_interpretations": 42,
           "all_semantic_interpretations_valid": False}
    with pytest.raises(corpus.TriangleCorpusError, match="all canonical"):
        corpus.compile_triangle_candidate_corpus(
            evidence, triangle, critic, semantic_inference_reviews=(review, bad),
        )


def test_cli_repeats_one_semantic_receipt_per_native_episode():
    from scripts.training.rom_study import parser
    args = parser().parse_args([
        "export-triangle-corpus", "--receipt", "/tmp/game.json",
        "--review-receipt", "/tmp/critic.json", "--source-sha256", "f" * 64,
        "--reviewer-checkpoint", "/tmp/critic-model",
        "--semantic-review-receipt", "/tmp/semantic-episode-0.json",
        "--semantic-review-receipt", "/tmp/semantic-episode-1.json",
        "--semantic-checkpoint", "/tmp/semantic-model",
        "--output-dir", "/tmp/out",
    ])
    assert len(args.semantic_review_receipt) == 2
    assert args.semantic_review_receipt[1].name == "semantic-episode-1.json"


def test_200_semantic_questions_are_corpus_metadata_not_1600_supervised_samples(monkeypatch):
    from skeleton.jeeves import game_emulator_triangle_corpus as corpus
    monkeypatch.setattr(corpus, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(corpus, "verify_native_adversarial_review", lambda *a: None)

    def two_hundred_route(episode, *, max_lenses=43, requested_keys=()):
        assert max_lenses == 200
        assert not requested_keys
        base = _fake_semantic_route(episode)
        item = base["routes"][0]
        base["routes"] = [
            {**item, "lens_key": "author_canonical_" + str(i)}
            for i in range(200)
        ]
        base["actually_routed_lenses"] = 200
        return base

    monkeypatch.setattr(corpus, "route_episode_semantic_lenses", two_hundred_route)
    source, triangle, review = _synthetic_corpus_inputs()
    candidate = corpus.compile_triangle_candidate_corpus(
        source, triangle, review, semantic_lens_budget=200,
    )
    assert candidate["canonical_semantic_lens_selection_budget"] == 200
    assert candidate["routed_semantic_lens_questions"] == 200
    assert len(candidate["semantic_routes_per_episode"][0]["semantic_questions"]) == 200
    assert candidate["total_lens_candidate_views"] == 8
    assert candidate["unique_independent_native_episodes"] == 1
    assert candidate["additional_independent_gameplay_episodes_from_lenses"] == 0
    assert candidate["semantic_questions_are_not_supervised_labels"] is True
    assert candidate["production_jeeves_optimizer_steps"] == 0
    corpus.verify_triangle_candidate_corpus(source, triangle, review, candidate)
