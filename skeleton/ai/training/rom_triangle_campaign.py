"""Foreground ROM -> native gameplay -> Dragon -> independent model review campaign.

Reuses the existing source/rights/core gate and independently-validated
training triangle. No new emulator or provider is created. Per-source receipts
are create-only; a resumed source replays the installed reviewer model before
claiming a previously recorded critique is reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .rom_study import (
    RomStudyError, _private_output, _regular_identity, _safe_path,
    _save_new, _stat_tuple, train_page, verified_rom_receipt,
)
from skeleton.jeeves.game_emulator_triangle import verify_training_triangle
from skeleton.jeeves.game_emulator_triangle_native_reviewer import (
    replay_native_adversarial_review,
    run_native_adversarial_review,
    verify_native_adversarial_review,
)

MAX_RECEIPT_BYTES = 32 * 1024 * 1024


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RomStudyError("duplicate ROM triangle receipt property")
        value[key] = item
    return value


def read_receipt_document(path: Path, *, max_bytes: int = MAX_RECEIPT_BYTES
                          ) -> tuple[dict[str, Any], str]:
    """No-symlink bounded read tied to an unchanged file identity and byte SHA."""
    source = _safe_path(path)
    before = _regular_identity(source)
    if before[2] > max_bytes:
        raise RomStudyError("triangle receipt exceeds bounded input size")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(source, flags)
    try:
        if _stat_tuple(os.fstat(fd)) != before:
            raise RomStudyError("triangle receipt changed before loading")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) != before[2] or _stat_tuple(os.fstat(fd)) != before:
            raise RomStudyError("triangle receipt changed while loading")
    finally:
        os.close(fd)
    if _regular_identity(source) != before:
        raise RomStudyError("triangle receipt changed after loading")
    try:
        value = json.loads(
            raw, object_pairs_hook=_no_duplicates,
            parse_constant=lambda _: (_ for _ in ()).throw(
                RomStudyError("nonfinite triangle JSON value")
            ),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RomStudyError("triangle receipt JSON is invalid") from exc
    if type(value) is not dict:
        raise RomStudyError("triangle receipt requires a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def review_receipt_name(source_sha: str, source_receipt_sha: str,
                        model_sha: str, seed: int, tokens: int) -> str:
    if not all(type(v) is str and len(v) == 64 and
               all(ch in "0123456789abcdef" for ch in v)
               for v in (source_sha, source_receipt_sha, model_sha)):
        raise RomStudyError("triangle review identity needs exact SHA-256 fingerprints")
    fingerprint = hashlib.sha256(json.dumps({
        "receipt": source_receipt_sha, "model": model_sha,
        "seed": seed, "tokens": tokens,
    }, sort_keys=True).encode()).hexdigest()
    return "triangle-review-" + source_sha[:16] + "-" + fingerprint[:24] + ".json"


def review_one_receipt(
    receipt_file: Path, *, expected_source_sha256: str,
    output_dir: Path, runtime: Any, seed: int = 0, max_new_tokens: int = 160,
) -> dict[str, Any]:
    """Actual local model review; no receipt is accepted by a digest-only shortcut."""
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    if not isinstance(runtime, NativeLLMRuntime):
        raise RomStudyError("real native reviewer checkpoint is required")
    checked = verified_rom_receipt(
        receipt_file, expected_source_sha256=expected_source_sha256,
    )
    document, read_sha = read_receipt_document(receipt_file)
    if read_sha != checked["receipt_sha256"]:
        raise RomStudyError("source ROM evidence changed since the independent audit")
    evidence, triangle = document.get("candidate_evidence"), document.get("training_triangle")
    verify_training_triangle(evidence, triangle)
    output_dir = _private_output(output_dir)
    runtime.assert_model_unchanged()
    name = review_receipt_name(
        expected_source_sha256, checked["receipt_sha256"], runtime.model_digest,
        seed, max_new_tokens,
    )
    destination = output_dir / name
    if destination.exists() or destination.is_symlink():
        prior, _ = read_receipt_document(destination)
        verify_native_adversarial_review(evidence, triangle, prior)
        if (prior.get("independent_local_transformer_sha256") != runtime.model_digest
                or prior.get("requested_seed") != seed
                or prior.get("requested_max_new_tokens") != max_new_tokens):
            raise RomStudyError("stored reviewer model or config differs")
        replay = replay_native_adversarial_review(evidence, triangle, prior, runtime)
        state = "prior_local_adversarial_review_replayed"
        replayed = replay["native_generations_replayed"]
        digest = prior["review_digest"]
        structured = prior["structured_source_bound_passes"]
    else:
        result = run_native_adversarial_review(
            evidence, triangle, runtime, seed=seed,
            max_new_tokens=max_new_tokens,
        )
        verify_native_adversarial_review(evidence, triangle, result)
        _save_new(destination, result)
        state = "new_local_adversarial_review_executed"
        replayed = 0
        digest = result["review_digest"]
        structured = result["structured_source_bound_passes"]
    if structured != 3:
        # A model that emitted unparsable, ungrounded or partial prose has
        # executed tokens, but has NOT completed independent adversarial
        # scrutiny. Keep the create-only receipt so reseeding/model changes
        # are explicit and no historical attempt is overwritten.
        state = "critic_output_incomplete_requires_new_review_configuration"
    return {
        "state": state,
        "review_receipt_name": name,
        "review_digest": digest,
        "structured_source_bound_passes": structured,
        "native_critic_generations_replayed": replayed,
        "manual_adjudication_required": True,
        "source_native_gameplay_verified": True,
        "dragon_pixel_observation_is_not_semantic_vision": True,
        "production_jeeves_weights_modified": False,
    }


def triangle_campaign_page(
    root: Path, approvals: Path, output_dir: Path, runtime: Any, *,
    cursor: str | None = None, limit: int = 32, runs: int = 12,
    steps: int = 24, seed: int = 0, neural_world: bool = False,
    neural_epochs: int = 4, neural_width: int = 8,
    inventory_snapshot: dict[str, Any] | None = None,
    review_seed: int = 0, review_tokens: int = 160,
    semantic_runtime: Any | None = None,
    semantic_lens_keys: tuple[str, ...] = (),
    semantic_all_runs: bool = False,
    semantic_seed: int = 0,
    semantic_tokens: int = 192,
) -> dict[str, Any]:
    """One bounded foreground page, with an independent review for eligible ROMs.

    A failure does not erase actual gameplay receipts, fabricate a critic
    verdict or advance a source's review status. Source-level failures are
    reportable for retry on the SAME cursor without duplicate training.
    """
    page = train_page(
        root, approvals, output_dir, cursor=cursor, limit=limit,
        runs=runs, steps=steps, seed=seed, neural_world=neural_world,
        neural_epochs=neural_epochs, neural_width=neural_width,
        inventory_snapshot=inventory_snapshot,
    )
    accepted = {
        "q_policy_updated_with_receipt",
        "q_policy_executed_no_updates",
        "previous_verified_receipt_no_reexecution",
    }
    rows: list[dict[str, Any]] = []
    for row in page["page_results"]:
        item = {
            "relative_path": row["relative_path"],
            "source_sha256": row.get("source_sha256"),
            "gameplay_state": row["state"],
            "adversarial_review_state": "not_eligible",
            "semantic_lens_review_state": (
                "not_requested" if semantic_runtime is None else "not_eligible"
            ),
            "semantic_model_generations": 0,
        }
        if row["state"] in accepted:
            identity, filename = row.get("source_sha256"), row.get("receipt_name")
            if (type(identity) is not str or type(filename) is not str
                    or "/" in filename or "\\" in filename or not filename.startswith(
                        "rom-" + identity[:16] + "-"
                    ) or not filename.endswith(".json")):
                raise RomStudyError("ROM training page returned unsafe receipt identity")
            try:
                reviewed = review_one_receipt(
                    output_dir / filename, expected_source_sha256=identity,
                    output_dir=output_dir, runtime=runtime,
                    seed=review_seed, max_new_tokens=review_tokens,
                )
            except (ValueError, RuntimeError, OSError, ImportError) as exc:
                item["adversarial_review_state"] = "blocked_retry_required"
                item["failure_type"] = type(exc).__name__
                item["failure_reason"] = str(exc)[:240]
            else:
                item["adversarial_review_state"] = reviewed["state"]
                item["review_receipt_name"] = reviewed["review_receipt_name"]
                item["review_digest"] = reviewed["review_digest"]
                item["structured_source_bound_passes"] = reviewed[
                    "structured_source_bound_passes"
                ]
                if semantic_runtime is not None:
                    if reviewed["structured_source_bound_passes"] != 3:
                        item["semantic_lens_review_state"] = "critic_incomplete_retry_required"
                    else:
                        try:
                            recorded, _ = read_receipt_document(output_dir / filename)
                            episode_count = len(
                                recorded["training_triangle"]["episode_lens_references"]
                            )
                            indices = (
                                range(episode_count) if semantic_all_runs else (0,)
                            )
                            receipts = []
                            for i in indices:
                                examined = execute_native_43_lens_review(
                                    output_dir / filename,
                                    output_dir / reviewed["review_receipt_name"],
                                    source_sha256=identity, output_dir=output_dir,
                                    critic_runtime=runtime,
                                    semantic_runtime=semantic_runtime,
                                    run_index=i, requested_keys=semantic_lens_keys,
                                    seed=semantic_seed + i * 43,
                                    max_new_tokens=semantic_tokens,
                                )
                                receipts.append([
                                    i, examined["filename"], examined["semantic_review_digest"],
                                ])
                        except (ValueError, RuntimeError, OSError, ImportError, KeyError) as exc:
                            item["semantic_lens_review_state"] = "blocked_retry_required"
                            item["semantic_failure_type"] = type(exc).__name__
                            item["semantic_failure_reason"] = str(exc)[:240]
                        else:
                            item["semantic_lens_review_state"] = "43_lenses_native_executed_or_replayed"
                            item["semantic_model_generations"] = 43 * len(receipts)
                            item["semantic_episode_count"] = len(receipts)
                            item["semantic_receipts_digest"] = hashlib.sha256(
                                json.dumps(receipts, sort_keys=True).encode()
                            ).hexdigest()
                            item["semantic_review_receipt_preview"] = [
                                row[1] for row in receipts[:3]
                            ]
        rows.append(item)
    return {
        "schema_version": "skeleton.jeeves.rom_training_triangle_campaign.v1",
        "cursor": page["inventory_cursor"],
        "next_cursor": page["next_cursor"],
        "finished_inventory": page["finished_inventory"],
        "rom_candidates_on_page": len(rows),
        "new_q_policies_updated": page["q_policy_training_completed"],
        "gameplay_executed_without_updates": page["q_policy_runs_without_updates"],
        "blocked_or_unreviewed_gameplay": page["blocked_or_unreviewed"],
        "model_review_executed_or_replayed": sum(
            row["adversarial_review_state"] in (
                "new_local_adversarial_review_executed",
                "prior_local_adversarial_review_replayed",
            ) for row in rows
        ),
        "review_failures_needing_retry": sum(
            row["adversarial_review_state"] in (
                "blocked_retry_required",
                "critic_output_incomplete_requires_new_review_configuration",
            ) or row["semantic_lens_review_state"] in (
                "blocked_retry_required", "critic_incomplete_retry_required",
            )
            for row in rows
        ),
        "semantic_model_generations_executed_or_replayed": sum(
            row["semantic_model_generations"] for row in rows
        ),
        "semantic_lens_review_failures_needing_retry": sum(
            row["semantic_lens_review_state"] in (
                "blocked_retry_required", "critic_incomplete_retry_required",
            ) for row in rows
        ),
        "semantic_model_interpretations_are_training_labels": False,
        "rows": rows,
        "production_jeeves_weight_updates": 0,
        "automatic_training_promotion": False,
        "independent_model_review_requires_human_adjudication": True,
    }


def export_reviewed_candidate_corpus(
    rom_receipt: Path, reviewer_receipt: Path, *,
    source_sha256: str, output_dir: Path, runtime: Any,
    requested_semantic_lens_keys: tuple[str, ...] = (),
    semantic_review_receipt: Path | None = None,
    semantic_runtime: Any | None = None,
) -> dict[str, Any]:
    """Replay the critic's real local checkpoint BEFORE exporting lens examples.

    Exports candidate-only, correlated view labels. It never invokes a
    production Jeeves optimizer and refuses unstructured reviewer passes.
    """
    from skeleton.jeeves.game_emulator_triangle_corpus import (
        compile_triangle_candidate_corpus, verify_triangle_candidate_corpus,
    )
    original = verified_rom_receipt(
        rom_receipt, expected_source_sha256=source_sha256,
    )
    document, digest = read_receipt_document(rom_receipt)
    if digest != original["receipt_sha256"]:
        raise RomStudyError("ROM evidence changed between source audits")
    evidence, triangle = document.get("candidate_evidence"), document.get("training_triangle")
    verify_training_triangle(evidence, triangle)
    review, _ = read_receipt_document(reviewer_receipt)
    verify_native_adversarial_review(evidence, triangle, review)
    replay = replay_native_adversarial_review(evidence, triangle, review, runtime)
    if replay["native_generations_replayed"] != 3:
        raise RomStudyError("all independent model passes must replay before corpus export")
    native_semantic_review = None
    if semantic_review_receipt is not None:
        if semantic_runtime is None:
            raise RomStudyError("semantic checkpoint required for model-backed 43-lens candidate corpus")
        from skeleton.jeeves.game_emulator_triangle_semantic_inference import (
            verify_native_semantic_lenses, replay_native_semantic_lenses,
        )
        native_semantic_review, _ = read_receipt_document(semantic_review_receipt)
        verify_native_semantic_lenses(
            evidence, triangle, review, native_semantic_review,
        )
        replayed_semantic = replay_native_semantic_lenses(
            evidence, triangle, review, native_semantic_review, semantic_runtime,
        )
        if replayed_semantic["native_jeeves_semantic_model_generations_replayed"] != 43:
            raise RomStudyError("43 native semantic checkpoint generations were not reproduced")
    elif semantic_runtime is not None:
        raise RomStudyError("semantic checkpoint must accompany a saved 43-lens review")
    candidate = compile_triangle_candidate_corpus(
        evidence, triangle, review,
        requested_semantic_lens_keys=requested_semantic_lens_keys,
        semantic_inference_review=native_semantic_review,
    )
    out = _private_output(output_dir)
    name = (
        ("triangle-corpus-v3-" if native_semantic_review is not None
         else "triangle-corpus-v2-")
        + source_sha256[:16] + "-"
        + review["review_digest"][:16] + "-"
        + candidate["semantic_lens_selection_digest"][:16]
        + (("-" + native_semantic_review["semantic_review_digest"][:16])
           if native_semantic_review is not None else "") + ".json"
    )
    target = out / name
    if target.exists() or target.is_symlink():
        saved, _ = read_receipt_document(target)
        verify_triangle_candidate_corpus(
            evidence, triangle, review, saved,
            semantic_inference_review=native_semantic_review,
        )
        state = "prior_verified_candidate_corpus"
    else:
        _save_new(target, candidate)
        state = "new_reviewed_candidate_corpus_create_only"
    return {
        "state": state,
        "filename": name,
        "candidate_corpus_digest": candidate["candidate_corpus_digest"],
        "verified_43_lens_native_inference_receipt": (
            native_semantic_review["semantic_review_digest"]
            if native_semantic_review is not None else None
        ),
        "replayed_semantic_model_generations": (
            43 if native_semantic_review is not None else 0
        ),
        "semantic_generated_hypotheses_used_as_labels": False,
        "unique_native_episodes": candidate["unique_independent_native_episodes"],
        "correlated_lens_views": candidate["total_lens_candidate_views"],
        "canonical_semantic_lens_selection_budget": candidate["canonical_semantic_lens_selection_budget"],
        "routed_semantic_lens_questions": candidate["routed_semantic_lens_questions"],
        "semantic_questions_are_supervised_labels": False,
        "canonical_semantic_questions": candidate["routed_semantic_lens_questions"],
        "semantic_questions_are_not_training_labels": True,
        "semantic_catalog": candidate["native_semantic_catalog"],
        "semantic_lens_selection_digest": candidate["semantic_lens_selection_digest"],
        "same_source_total_weight_per_episode": 1.0,
        "native_reviewer_generations_replayed": 3,
        "source_rom_training_rights_acknowledged": True,
        "candidate_still_requires_jeeves_corpus_admission": True,
        "production_jeeves_optimizer_steps": 0,
    }


def load_operator_semantic_lens_set(path: Path) -> tuple[str, ...]:
    """Read an exact 43-key selection; absent files never cause fallback routing.

    This is a human-authored selection of canonical Jeeves lens *keys*, not
    executable code, training evidence, a model checkpoint or an override
    of scientific governance.
    """
    document, _ = read_receipt_document(path, max_bytes=32768)
    from skeleton.jeeves.game_emulator_triangle_semantics import SEMANTIC_LENS_BUDGET
    keys = document.get("lens_keys")
    if (set(document) != {"schema_version", "lens_keys"}
            or document.get("schema_version") != "skeleton.jeeves.semantic_lens_set.v1"
            or type(keys) is not list or len(keys) != SEMANTIC_LENS_BUDGET
            or any(type(key) is not str or key != key.casefold().strip() or not key
                   for key in keys)
            or len(set(keys)) != SEMANTIC_LENS_BUDGET):
        raise RomStudyError("operator lens-set manifest must name exactly 43 distinct canonical keys")
    return tuple(keys)



def inspect_native_episode_lenses(
    rom_receipt: Path, *, source_sha256: str, run_index: int = 0,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Inspect and optionally freeze 43 actual canonical Jeeves lens keys.

    Source and triangle are verified independently first. Manifest creation is
    operator-selected, create-only, and cannot change governance or infer game
    semantics. A saved lens set may be passed to export-triangle-corpus.
    """
    from skeleton.jeeves.game_emulator_triangle_semantics import (
        SEMANTIC_LENS_BUDGET, route_episode_semantic_lenses,
    )
    verified = verified_rom_receipt(
        rom_receipt, expected_source_sha256=source_sha256,
    )
    original, digest = read_receipt_document(rom_receipt)
    if verified["receipt_sha256"] != digest:
        raise RomStudyError("native lens inspection source changed after audit")
    evidence = original.get("candidate_evidence")
    triangle = original.get("training_triangle")
    verify_training_triangle(evidence, triangle)
    episodes = triangle["episode_lens_references"]
    if type(run_index) is not int or not 0 <= run_index < len(episodes):
        raise RomStudyError("episode lens selection index is outside source runs")
    source = episodes[run_index]
    route = route_episode_semantic_lenses(
        source, max_lenses=SEMANTIC_LENS_BUDGET,
    )
    keys = [item["lens_key"] for item in route["routes"]]
    if len(keys) != SEMANTIC_LENS_BUDGET or len(set(keys)) != len(keys):
        raise RomStudyError("actual canonical Jeeves router did not select 43 unique lenses")
    result = {
        "state": "verified_43_canonical_jeeves_lens_questions",
        "source_sha256": source_sha256,
        "native_trace_sha256": source["source_trace_sha256"],
        "canonical_registry": route["canonical_registry"],
        "canonical_registry_lens_count": route["canonical_catalog_lens_count"],
        "catalog_sha256": route["canonical_catalog_sha256"],
        "governance_fingerprint": route["governance_fingerprint"],
        "router_selection_sha256": route["route_digest"],
        "selected_lenses": [{
            "key": item["lens_key"],
            "family": item["lens_family"],
            "governance_grade": item["governance_grade"],
            "question": item["question"],
            "factual_claims_allowed": False,
        } for item in route["routes"]],
        "independent_new_gameplay_episodes_from_semantic_lenses": 0,
        "semantic_model_inferences_executed": False,
        "new_jeeves_weight_updates": 0,
    }
    if output_dir is not None:
        target = _private_output(output_dir)
        manifest = {
            "schema_version": "skeleton.jeeves.semantic_lens_set.v1",
            "lens_keys": keys,
        }
        name = (
            "semantic-lens-set-" + source_sha256[:16] + "-"
            + route["route_digest"][:16] + ".json"
        )
        path = target / name
        if path.exists() or path.is_symlink():
            saved, _ = read_receipt_document(path, max_bytes=32768)
            if saved != manifest:
                raise RomStudyError("prior lens-selection manifest differs")
        else:
            _save_new(path, manifest)
        result["operator_manifest_name"] = name
    return result


def execute_native_43_lens_review(
    rom_receipt: Path, critic_receipt: Path, *,
    source_sha256: str, output_dir: Path,
    critic_runtime: Any, semantic_runtime: Any,
    run_index: int = 0, requested_keys: tuple[str, ...] = (),
    seed: int = 0, max_new_tokens: int = 192,
) -> dict[str, Any]:
    """Actual, independently replayable 43-lens native LLM interpretation pass.

    Before permitting interpretive model execution, the critic's prior three
    native generations are independently reproduced from its own checkpoint.
    Source and catalog identity stay pinned; generated hypotheses remain
    unaudited until separate adjudication and are never supervised labels.
    """
    from skeleton.jeeves.game_emulator_triangle_semantic_inference import (
        run_native_semantic_lenses, verify_native_semantic_lenses,
        replay_native_semantic_lenses,
    )
    from skeleton.jeeves.game_emulator_triangle_semantics import (
        route_episode_semantic_lenses, SEMANTIC_LENS_BUDGET,
    )
    checked = verified_rom_receipt(
        rom_receipt, expected_source_sha256=source_sha256,
    )
    document, read_sha = read_receipt_document(rom_receipt)
    if checked["receipt_sha256"] != read_sha:
        raise RomStudyError("43-lens native training evidence changed after source audit")
    evidence, triangle = document.get("candidate_evidence"), document.get("training_triangle")
    verify_training_triangle(evidence, triangle)
    review, _ = read_receipt_document(critic_receipt)
    verify_native_adversarial_review(evidence, triangle, review)
    if review["structured_source_bound_passes"] != 3:
        raise RomStudyError("cannot execute 43 lenses against an incomplete adversarial review")
    replayed_critic = replay_native_adversarial_review(
        evidence, triangle, review, critic_runtime,
    )
    if replayed_critic["native_generations_replayed"] != 3:
        raise RomStudyError("independent adversarial reviewer checkpoint did not reproduce")
    episodes = triangle["episode_lens_references"]
    if type(run_index) is not int or not 0 <= run_index < len(episodes):
        raise RomStudyError("43-lens review index outside native evidence")
    source = episodes[run_index]
    route = route_episode_semantic_lenses(
        source, max_lenses=SEMANTIC_LENS_BUDGET, requested_keys=requested_keys,
    )
    semantic_runtime.assert_model_unchanged()
    identity = hashlib.sha256(json.dumps({
        "source": checked["receipt_sha256"],
        "critic": review["review_digest"],
        "native_trace": source["source_trace_sha256"],
        "canonical_route": route["route_digest"],
        "semantic_model": semantic_runtime.model_digest,
        "seed": seed, "max_new_tokens": max_new_tokens,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    name = (
        "semantic-43-native-" + source_sha256[:16] + "-"
        + identity[:32] + ".json"
    )
    target = _private_output(output_dir) / name
    if target.exists() or target.is_symlink():
        prior, _ = read_receipt_document(target)
        verify_native_semantic_lenses(evidence, triangle, review, prior)
        if (prior["model_sha256"] != semantic_runtime.model_digest
                or prior["requested_seed"] != seed
                or prior["requested_max_new_tokens"] != max_new_tokens
                or prior["canonical_route_sha256"] != route["route_digest"]):
            raise RomStudyError("saved 43-lens native model or routing identity differs")
        replayed = replay_native_semantic_lenses(
            evidence, triangle, review, prior, semantic_runtime,
        )
        digest = prior["semantic_review_digest"]
        count = replayed["native_jeeves_semantic_model_generations_replayed"]
        structured = prior["source_bound_interpretations"]
        state = ("verified_43_native_lens_generations_replayed"
                 if prior["all_semantic_interpretations_valid"]
                 else "replayed_43_native_generations_incomplete_interpretations")
    else:
        fresh = run_native_semantic_lenses(
            evidence, triangle, review, semantic_runtime,
            run_index=run_index, requested_keys=requested_keys,
            seed=seed, max_new_tokens=max_new_tokens,
        )
        verify_native_semantic_lenses(evidence, triangle, review, fresh)
        _save_new(target, fresh)
        digest = fresh["semantic_review_digest"]
        count = fresh["native_model_generations_executed"]
        structured = fresh["source_bound_interpretations"]
        state = ("executed_43_native_lens_generations_requires_adjudication"
                 if fresh["all_semantic_interpretations_valid"]
                 else "executed_43_native_generations_incomplete_interpretations")
    return {
        "state": state,
        "filename": name,
        "source_sha256": source_sha256,
        "native_trace_sha256": source["source_trace_sha256"],
        "canonical_catalog_sha256": route["canonical_catalog_sha256"],
        "native_semantic_model_sha256": semantic_runtime.model_digest,
        "independent_adversarial_model_sha256": critic_runtime.model_digest,
        "native_model_lens_generations": count,
        "source_referenced_interpretations": structured,
        "lens_interpretations_incomplete": SEMANTIC_LENS_BUDGET - structured,
        "all_lens_interpretations_valid": structured == SEMANTIC_LENS_BUDGET,
        "semantic_review_digest": digest,
        "reviewed_source_trace_count": 1,
        "new_independent_gameplay_episodes": 0,
        "production_jeeves_weights_modified": False,
        "semantic_findings_are_training_labels": False,
        "operator_adjudication_required": True,
    }
