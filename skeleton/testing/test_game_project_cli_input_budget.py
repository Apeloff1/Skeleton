"""Installed game-project CLI input budget and receipt-reading regressions."""
from __future__ import annotations

import json

import pytest

from skeleton.ai.runtime.game_project_cli import (
    MAX_INPUT_BYTES, MAX_RESULT_BYTES, _read_json,
)
from skeleton.ai.runtime.game_project_capsule import GameCapsuleError


def test_signed_result_receipt_may_exceed_original_project_input_budget(tmp_path):
    # Existing portable receipts are allowed to be 160 KiB; source projects
    # retain the smaller 96-KiB budget unless the caller opts in explicitly.
    document = {"receipt": "x" * (MAX_INPUT_BYTES + 32)}
    source = tmp_path / "portable-receipt.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    assert MAX_INPUT_BYTES < source.stat().st_size < MAX_RESULT_BYTES

    assert _read_json(source, max_bytes=MAX_RESULT_BYTES) == document
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(source)


@pytest.mark.parametrize("invalid", [0, -1, 1.5, True, MAX_RESULT_BYTES + 1])
def test_game_project_read_rejects_invalid_or_unbounded_budgets(tmp_path, invalid):
    source = tmp_path / "valid.json"
    source.write_text('{"ok":true}', encoding="utf-8")
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(source, max_bytes=invalid)


def test_explicit_receipt_budget_still_rejects_oversized_input(tmp_path):
    source = tmp_path / "oversized.json"
    source.write_text(json.dumps({"receipt": "x" * MAX_RESULT_BYTES}), encoding="utf-8")
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(source, max_bytes=MAX_RESULT_BYTES)
