"""Backup JSON input must not admit ambiguous or nonfinite representations."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import (
    BackupError, _strict_json, verify_backup,
)


@pytest.mark.parametrize("payload", [
    '{"payload": {}, "payload": {}, "sha256": "x"}',
    '{"payload": {"history": [], "history": []}, "sha256": "x"}',
    '{"payload": {"session": {"head": 1, "head": 2}}, "sha256": "x"}',
    '{"payload": {"history": [NaN]}, "sha256": "x"}',
    '{"payload": {"history": [Infinity]}, "sha256": "x"}',
    '{"payload": {"history": [-Infinity]}, "sha256": "x"}',
])
def test_strict_backup_json_rejects_ambiguous_members(payload):
    with pytest.raises(BackupError):
        _strict_json(payload)


def test_strict_backup_json_accepts_canonical_envelope_shape():
    assert _strict_json('{"payload":{},"sha256":"x"}') == {
        "payload": {}, "sha256": "x",
    }


def test_verify_backup_rejects_duplicate_before_campaign_parse():
    with pytest.raises(BackupError, match="duplicate"):
        verify_backup('{"payload":{},"payload":{},"sha256":"x"}', b"")
