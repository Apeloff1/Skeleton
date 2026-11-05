"""Untrusted JSON numeric overflow must fail closed at all authoring seams."""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError, strict_json
from skeleton.jeeves.worlds.portals_cli import run


@pytest.mark.parametrize("raw,code", [
    (b'{"value":1e9999}', "nonfinite_number"),
    (b'{"value":-1e9999}', "nonfinite_number"),
    (b'{"value":NaN}', "nonfinite_number"),
    (b'{"value":Infinity}', "nonfinite_number"),
    (b'{"value":-Infinity}', "nonfinite_number"),
    (b'{"value":1e9999,"value":2}', "nonfinite_number"),
    (b'{"a":1,"a":2}', "duplicate_json_key"),
    (b'{"a":', "invalid_json"),
    (b'{"a":1} trailing', "invalid_json"),
    (b'\xff', "invalid_json"),
])
def test_strict_json_rejects_malformed_or_nonfinite(raw, code):
    with pytest.raises(CanonError) as error:
        strict_json(raw)
    assert error.value.code == code


def test_finite_fraction_preserved_and_duplicate_detection():
    assert strict_json(b'{"a":1.25,"b":-2.5e2}') == {
        "a": 1.25, "b": -250.0,
    }


def test_cli_returns_typed_error_instead_of_traceback(tmp_path, capsys):
    assert run([
        "--store", str(tmp_path), "record-session",
        "--network-id", "journey", "--slot", "slot1",
        "--expected-network-digest", "0" * 64,
        "--session-json", '{"value":1e9999}',
    ]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response == {"ok": False, "error": "nonfinite_number"}
