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
            )
            for row in rows
        ),
        "rows": rows,
        "production_jeeves_weight_updates": 0,
        "automatic_training_promotion": False,
        "independent_model_review_requires_human_adjudication": True,
    }
