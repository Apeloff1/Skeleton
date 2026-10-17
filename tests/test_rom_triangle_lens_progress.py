"""200-lens progress is source-bound and never mistaken for replayed inference."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.ai.training import rom_triangle_lens_progress as status
from skeleton.jeeves.game_learning import _digest


def _arrange(monkeypatch, tmp_path, *, journal_size=3):
    from skeleton.ai.model_runtime import native_llm_runtime

    class Native:
        model_digest = "d" * 64
        def assert_model_unchanged(self):
            pass

    monkeypatch.setattr(native_llm_runtime, "NativeLLMRuntime", Native)
    trace = "e" * 64
    triangle = {
        "episode_lens_references": [{"source_trace_sha256": trace}],
        "triangle_digest": "f" * 64,
    }
    critic = {
        "review_digest": "b" * 64, "structured_source_bound_passes": 3,
    }
    monkeypatch.setattr(status, "verified_rom_receipt", lambda *a, **kw: {
        "receipt_sha256": "c" * 64,
    })

    def read(path):
        if str(path).endswith("rom.json"):
            return {"candidate_evidence": {"report_digest": "a" * 64},
                    "training_triangle": triangle}, "c" * 64
        return critic, "x" * 64

    monkeypatch.setattr(status, "read_receipt_document", read)
    monkeypatch.setattr(status, "verify_training_triangle", lambda *a: None)
    monkeypatch.setattr(status, "verify_native_adversarial_review", lambda *a: None)
    monkeypatch.setattr(status, "_private_output", lambda path: tmp_path)
    route = {
        "actually_routed_lenses": 200,
        "canonical_catalog_sha256": "1" * 64,
        "route_digest": "2" * 64,
        "routes": [{
            "lens_key": f"canonical.authored.{index}",
            "native_evidence_support_class": (
                "measured_native_cue_present" if index % 2 == 0
                else "hypothesis_only_without_matching_native_cue"
            ),
        } for index in range(200)],
    }
    monkeypatch.setattr(status, "route_episode_semantic_lenses",
                        lambda *a, **kw: route)
    monkeypatch.setattr(status, "read_native_lens_progress",
                        lambda *a, **kw: tuple({"index": i} for i in range(journal_size)))
    return Native(), triangle, critic, route


def test_status_exposes_all_200_canonical_lenses_without_extra_model_calls(
    monkeypatch, tmp_path,
):
    runtime, _, _, _ = _arrange(monkeypatch, tmp_path)
    result = status.native_lens_progress(
        tmp_path / "rom.json", tmp_path / "critic.json",
        source_sha256="a" * 64,
        output_dir=tmp_path, semantic_runtime=runtime,
    )
    assert result["lens_count"] == 200
    assert len(result["lenses"]) == 200
    assert result["journal_entries_source_bound"] == 3
    assert result["remaining_native_generations"] == 197
    assert result["next_lens_index"] == 3
    assert result["lenses"][2]["state"] == "saved_native_generation_requires_model_replay"
    assert result["lenses"][3]["state"] == "pending_native_model_generation"
    assert result["native_model_generations_replayed_by_status_inspection"] == 0
    assert result["production_jeeves_weights_modified"] is False


def test_status_rejects_corrupted_source_or_missing_critic(monkeypatch, tmp_path):
    runtime, _, critic, route = _arrange(monkeypatch, tmp_path)
    critic["structured_source_bound_passes"] = 2
    with pytest.raises(ValueError, match="three"):
        status.native_lens_progress(
            tmp_path / "rom.json", tmp_path / "critic.json",
            source_sha256="a" * 64, output_dir=tmp_path,
            semantic_runtime=runtime,
        )


def test_status_rejects_bad_seed_even_with_verified_checkpoint(monkeypatch, tmp_path):
    runtime, _, _, _ = _arrange(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="configuration"):
        status.native_lens_progress(
            tmp_path / "rom.json", tmp_path / "critic.json",
            source_sha256="a" * 64, output_dir=tmp_path,
            semantic_runtime=runtime, seed=-1,
        )


def test_operator_cli_has_200_lens_progress_command():
    from scripts.training.rom_study import parser
    args = parser().parse_args([
        "triangle-lens-progress",
        "--receipt", "/private/rom.json",
        "--review-receipt", "/private/critic.json",
        "--source-sha256", "f" * 64,
        "--semantic-checkpoint", "/private/checkpoint.json",
        "--output-dir", "/private/receipts",
        "--run-index", "7",
    ])
    assert args.operation == "triangle-lens-progress"
    assert args.run_index == 7
    assert args.max_new_tokens == 192
