"""Crash-safe, source-bound persistence of 200 real native semantic generations."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_emulator_triangle_lens_journal import (
    NativeLensJournalError,
    read_native_lens_progress, save_native_lens_progress,
)
from skeleton.ai.training.rom_triangle_campaign import read_receipt_document

PINNED = {
    "identity": "a" * 64,
    "source_trace": "b" * 64,
    "route_digest": "c" * 64,
    "model_sha": "d" * 64,
    "count": 200, "seed": 40, "tokens": 192,
}


def _entry(index):
    return {
        "lens_key": f"jeeves.authored.lens_{index:03}",
        "response": f"original model-generated hypothesis {index}",
        "native_inference_receipt": {
            "model_digest": "d" * 64, "seed": 40 + index,
        },
        "native_inference_record": {
            "generated_token_ids": [index + 1],
        },
    }


def _private(tmp_path):
    output = tmp_path / "private"
    output.mkdir(mode=0o700)
    output.chmod(0o700)
    return output


def test_contiguous_200_lens_journal_can_resume_without_duplicates(tmp_path):
    output = _private(tmp_path)
    assert read_native_lens_progress(output, **PINNED) == ()
    for i in range(3):
        digest = save_native_lens_progress(
            output, index=i, entry=_entry(i), **PINNED,
        )
        assert len(digest) == 64
    saved = read_native_lens_progress(output, **PINNED)
    assert len(saved) == 3
    assert saved == tuple(_entry(i) for i in range(3))
    with pytest.raises(FileExistsError):
        save_native_lens_progress(output, index=0, entry=_entry(0), **PINNED)


def test_missing_middle_of_200_progress_cannot_skip_to_later_generated_lens(tmp_path):
    output = _private(tmp_path)
    save_native_lens_progress(output, index=0, entry=_entry(0), **PINNED)
    save_native_lens_progress(output, index=2, entry=_entry(2), **PINNED)
    with pytest.raises(NativeLensJournalError, match="noncontiguous"):
        read_native_lens_progress(output, **PINNED)


def test_journal_rejects_foreign_checkpoint_even_if_record_is_self_rehashed(tmp_path):
    output = _private(tmp_path)
    save_native_lens_progress(output, index=0, entry=_entry(0), **PINNED)
    file = next(output.iterdir())
    row, _ = read_receipt_document(file)
    from skeleton.jeeves.game_learning import _digest
    row["native_model_sha256"] = "f" * 64
    row["journal_receipt_sha256"] = _digest({
        key: value for key, value in row.items()
        if key != "journal_receipt_sha256"
    })
    file.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(NativeLensJournalError, match="checkpoint"):
        read_native_lens_progress(output, **PINNED)


def test_journal_rejects_forged_source_route_and_seed(tmp_path):
    output = _private(tmp_path)
    save_native_lens_progress(output, index=0, entry=_entry(0), **PINNED)
    for override in (
        {"source_trace": "e" * 64},
        {"route_digest": "e" * 64},
        {"model_sha": "e" * 64},
        {"seed": 99},
        {"tokens": 64},
    ):
        # Distinct session IDs choose separate immutable histories. Same
        # journal identity with altered parent authority must never verify.
        with pytest.raises(NativeLensJournalError):
            read_native_lens_progress(output, **{**PINNED, **override})


def test_journal_does_not_accept_symlink_or_tampered_json(tmp_path):
    output = _private(tmp_path)
    save_native_lens_progress(output, index=0, entry=_entry(0), **PINNED)
    file = next(output.iterdir())
    target = output / "backup.json"
    file.rename(target)
    file.symlink_to(target)
    with pytest.raises(ValueError):
        read_native_lens_progress(output, **PINNED)


def test_journal_rejects_non_200_budget_and_bogus_inference_entry(tmp_path):
    output = _private(tmp_path)
    with pytest.raises(NativeLensJournalError, match="invalid"):
        save_native_lens_progress(
            output, index=0, entry=_entry(0),
            **{**PINNED, "count": 43},
        )
    with pytest.raises(NativeLensJournalError, match="invalid"):
        save_native_lens_progress(
            output, index=200, entry=_entry(200), **PINNED,
        )
