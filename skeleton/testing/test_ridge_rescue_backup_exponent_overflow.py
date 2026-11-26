"""Exponent overflow must not turn a replay-bound backup into infinity."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import BackupError, _strict_json, verify_backup


@pytest.mark.parametrize("number", ["1e999", "-1e999", "9.99e9999", "1E+309"])
def test_exponent_overflow_is_rejected_at_any_depth(number):
    with pytest.raises(BackupError, match="nonfinite|invalid"):
        _strict_json('{"payload":{"session":{"score":' + number + '}},"sha256":"x"}')


def test_overflow_is_rejected_before_campaign_source_parse():
    with pytest.raises(BackupError, match="nonfinite|invalid"):
        verify_backup('{"payload":{"history":[1e999]},"sha256":"x"}', b"not a campaign")


def test_finite_exponents_remain_supported():
    assert _strict_json('{"value":1e2}') == {"value": 100.0}
