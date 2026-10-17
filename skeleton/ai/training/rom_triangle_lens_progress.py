"""Read-only, custody-verified progress audit for a 200-lens Jeeves session.

Progress is NOT proof that the installed model reproduced its old outputs:
the actual resumed generation path performs that replay. This status view
reports precisely which canonical questions have durable, source-matched
journal entries and where the next legitimate generation must begin.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .rom_study import RomStudyError, _private_output, verified_rom_receipt
from .rom_triangle_campaign import read_receipt_document
from skeleton.jeeves.game_learning import _digest
from skeleton.jeeves.game_emulator_triangle import verify_training_triangle
from skeleton.jeeves.game_emulator_triangle_semantics import route_episode_semantic_lenses
from skeleton.jeeves.game_emulator_triangle_native_reviewer import verify_native_adversarial_review
from skeleton.jeeves.game_emulator_triangle_semantic_inference import (
    verify_native_semantic_lenses,
)
from skeleton.jeeves.game_emulator_triangle_lens_journal import (
    read_native_lens_progress,
)


def native_lens_progress(
    rom_receipt: Path, critic_receipt: Path, *, source_sha256: str,
    output_dir: Path, semantic_runtime: Any, run_index: int = 0,
    seed: int = 0, max_new_tokens: int = 192,
) -> dict[str, Any]:
    """Report every canonical lens state without generating or replaying tokens."""
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    if not isinstance(semantic_runtime, NativeLLMRuntime):
        raise RomStudyError("installed native semantic checkpoint required for progress audit")
    original = verified_rom_receipt(
        rom_receipt, expected_source_sha256=source_sha256,
    )
    document, digest = read_receipt_document(rom_receipt)
    if digest != original["receipt_sha256"]:
        raise RomStudyError("ROM evidence changed before 200-lens progress inspection")
    evidence, triangle = document["candidate_evidence"], document["training_triangle"]
    verify_training_triangle(evidence, triangle)
    critic, _ = read_receipt_document(critic_receipt)
    verify_native_adversarial_review(evidence, triangle, critic)
    if critic.get("structured_source_bound_passes") != 3:
        raise RomStudyError("independent reviewer has not grounded all three challenges")
    episodes = triangle["episode_lens_references"]
    if type(run_index) is not int or not 0 <= run_index < len(episodes):
        raise RomStudyError("native training episode index invalid")
    if (type(seed) is not int or not 0 <= seed <= 2**63 - 201
            or type(max_new_tokens) is not int or not 32 <= max_new_tokens <= 512):
        raise RomStudyError("200-lens generation configuration invalid")
    runtime = semantic_runtime
    runtime.assert_model_unchanged()
    source = episodes[run_index]
    route = route_episode_semantic_lenses(source, max_lenses=200)
    if route["actually_routed_lenses"] != 200:
        raise RomStudyError("canonical maximal router returned less than 200 actual lenses")
    identity = _digest({
        "source": original["receipt_sha256"],
        "critic": critic["review_digest"],
        "native_trace": source["source_trace_sha256"],
        "canonical_route": route["route_digest"],
        "semantic_model": runtime.model_digest,
        "seed": seed, "max_new_tokens": max_new_tokens,
    })
    directory = _private_output(output_dir)
    progress = read_native_lens_progress(
        directory, identity=identity,
        source_trace=source["source_trace_sha256"],
        route_digest=route["route_digest"],
        model_sha=runtime.model_digest,
        count=200, seed=seed, tokens=max_new_tokens,
    )
    final_name = (
        "semantic-200-native-" + source_sha256[:16] + "-"
        + identity[:32] + ".json"
    )
    final_path = directory / final_name
    complete = final_path.exists() or final_path.is_symlink()
    final_digest = None
    if complete:
        receipt, _ = read_receipt_document(final_path)
        verify_native_semantic_lenses(evidence, triangle, critic, receipt)
        if (receipt["canonical_route_sha256"] != route["route_digest"]
                or receipt["requested_seed"] != seed
                or receipt["requested_max_new_tokens"] != max_new_tokens
                or receipt["model_sha256"] != runtime.model_digest
                or receipt["native_model_generations_executed"] != 200):
            raise RomStudyError("finished 200-lens model review has another source or checkpoint")
        final_digest = receipt["semantic_review_digest"]
        if len(progress) != 200:
            raise RomStudyError(
                "final 200-lens receipt cannot omit its immutable per-lens source journal"
            )
    questions = []
    for i, lens in enumerate(route["routes"]):
        questions.append({
            "lens_index": i,
            "lens_key": lens["lens_key"],
            "native_evidence_support_class": lens["native_evidence_support_class"],
            "state": (
                "complete_receipt_verified_not_replayed" if complete
                else "saved_native_generation_requires_model_replay"
                if i < len(progress) else "pending_native_model_generation"
            ),
            "independent_training_example_added": False,
        })
    runtime.assert_model_unchanged()
    report = {
        "schema_version": "skeleton.jeeves.native_200_lens_progress.v1",
        "source_rom_sha256": source_sha256,
        "source_native_trace_sha256": source["source_trace_sha256"],
        "canonical_catalog_sha256": route["canonical_catalog_sha256"],
        "canonical_route_sha256": route["route_digest"],
        "session_identity_sha256": identity,
        "local_semantic_model_sha256": runtime.model_digest,
        "lens_count": 200,
        "journal_entries_source_bound": len(progress),
        "remaining_native_generations": 200 - len(progress),
        "next_lens_index": len(progress) if len(progress) < 200 else None,
        "final_receipt_filename": final_name if complete else None,
        "final_receipt_sha256": final_digest,
        "progress_not_proof_of_native_model_replay": True,
        "native_model_generations_replayed_by_status_inspection": 0,
        "hypotheses_not_admitted_as_training_ground_truth": True,
        "production_jeeves_weights_modified": False,
        "lenses": questions,
    }
    report["progress_digest"] = _digest(report)
    return report
