"""Immutable per-lens progress journal for long 200-lens native review sessions.

A 200-generation run can be interrupted after any lens without discarding
completed *actual* checkpoint inferences. Journal records are create-only,
source/model/route/seed-pinned, and all resumed entries MUST undergo native
model replay before completion. They are never training labels.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .game_learning import _digest
from .game_emulator_triangle_semantics import EXTENDED_SEMANTIC_LENS_BUDGET

SCHEMA = "skeleton.jeeves.native_semantic_lens_resume_journal.v1"


class NativeLensJournalError(ValueError):
    pass


def _sha(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


def _label(identity: str, index: int) -> str:
    if not _sha(identity) or type(index) is not int or not 0 <= index < 200:
        raise NativeLensJournalError("journal requires a pinned semantic route and index")
    return "semantic-lens-progress-" + identity[:32] + "-" + f"{index:03d}.json"


def _payload(identity: str, source_trace: str, route_digest: str,
             model_sha: str, index: int, count: int, seed: int, tokens: int,
             entry: dict[str, Any]) -> dict[str, Any]:
    if (not all(map(_sha, (identity, source_trace, route_digest, model_sha)))
            or type(index) is not int or type(count) is not int
            or not 0 <= index < count == EXTENDED_SEMANTIC_LENS_BUDGET
            or type(seed) is not int or seed < 0 or seed > 2**63 - 1 - count
            or type(tokens) is not int or not 32 <= tokens <= 512
            or type(entry) is not dict):
        raise NativeLensJournalError("native lens progress journal identity is invalid")
    data = {
        "schema_version": SCHEMA,
        "journal_session_sha256": identity,
        "native_trace_sha256": source_trace,
        "canonical_route_sha256": route_digest,
        "native_model_sha256": model_sha,
        "native_lens_index": index,
        "lens_budget": count,
        "requested_seed": seed,
        "requested_max_new_tokens": tokens,
        "entry": entry,
        "real_native_model_call_executed": True,
        "replayed_before_training_corpus_export": False,
        "production_jeeves_weights_modified": False,
    }
    data["journal_receipt_sha256"] = _digest(data)
    return data


def read_native_lens_progress(
    output_dir: Path, *,
    identity: str, source_trace: str, route_digest: str,
    model_sha: str, count: int, seed: int, tokens: int,
) -> tuple[dict[str, Any], ...]:
    """Reject missing-middle journals, symlink swaps and rehashed cross-run entries.

    A contiguous prefix is the only legal resume source. Never silently
    accept step 199 if step 87 is missing or carried another source identity.
    """
    from skeleton.ai.training.rom_triangle_campaign import (
        _private_output, read_receipt_document,
    )
    output = _private_output(output_dir)
    prefix = []
    encountered_gap = False
    for index in range(count):
        file = output / _label(identity, index)
        if not file.exists() and not file.is_symlink():
            encountered_gap = True
            continue
        if encountered_gap:
            raise NativeLensJournalError(
                "semantic lens journal has a noncontiguous or foreign resume history"
            )
        actual, _ = read_receipt_document(file, max_bytes=256 * 1024)
        entry = actual.get("entry")
        expected = _payload(identity, source_trace, route_digest, model_sha,
                            index, count, seed, tokens, entry)
        if actual != expected:
            raise NativeLensJournalError(
                "persisted semantic generation changed source, config or checkpoint"
            )
        prefix.append(entry)
    return tuple(prefix)


def save_native_lens_progress(
    output_dir: Path, *,
    identity: str, source_trace: str, route_digest: str,
    model_sha: str, index: int, count: int, seed: int, tokens: int,
    entry: dict[str, Any],
) -> str:
    """Commit one real inference result after model generation has returned."""
    from skeleton.ai.training.rom_triangle_campaign import (
        _private_output, _save_new,
    )
    output = _private_output(output_dir)
    row = _payload(identity, source_trace, route_digest, model_sha,
                   index, count, seed, tokens, entry)
    _save_new(output / _label(identity, index), row)
    return row["journal_receipt_sha256"]
