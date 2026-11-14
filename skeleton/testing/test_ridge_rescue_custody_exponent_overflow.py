"""Regression: custody must reject exponent-overflow before replay or digest checks."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.custody import CustodyError, _strict_json, verify_run


@pytest.mark.parametrize("token", ["1e9999", "-1e9999", "9.9e9999", "NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_numbers_are_rejected(token):
    with pytest.raises(CustodyError, match="nonfinite bundle JSON number"):
        _strict_json('{"number":' + token + '}')


def test_exponent_overflow_cannot_enter_portable_bundle():
    with pytest.raises(CustodyError, match="nonfinite bundle JSON number"):
        verify_run('{"payload":{"schema":"ridge.rescue.run.v1","world":1e9999,"actions":[],"state":{}},"sha256":"invalid"}')


def test_finite_fraction_remains_accepted_by_json_parser():
    assert _strict_json('{"fraction":1.25e2}') == {"fraction": 125.0}
