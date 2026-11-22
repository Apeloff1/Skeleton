"""The numbered seams share one payload gate and all 200 of them load."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.local_ai.gap_filler import GapFiller
from skeleton.local_ai.seam_runtime import SeamRejected, apply


def _digest(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def test_accepted_record_keeps_the_caller_object():
    payload = {"b": 1, "a": [True, None, "kettle"]}
    record = apply(3, payload)
    assert record["seam"] == 3
    assert record["ok"] is True
    assert record["data"] is payload
    assert record["keys"] == 2
    assert record["digest"] == _digest(payload)
    assert apply(9, {"a": 1, "b": 2})["digest"] == apply(9, {"b": 2, "a": 1})["digest"]


def test_refusal_does_not_echo_the_payload():
    secret = "api_key=local-secret"
    record = apply(4, {"note": secret})
    assert record == {"seam": 4, "ok": False, "error": "payload refused"}
    assert secret not in json.dumps(record)
    assert apply(4, ["not", "a", "dict"])["ok"] is False
    assert apply(4, {1: "n"})["ok"] is False
    assert apply(4, {"": "n"})["ok"] is False
    assert apply(4, {"n": 10**12 + 1})["ok"] is False
    assert apply(4, {"n": float("nan")})["ok"] is False
    assert apply(4, {"n": "x" * 2001})["ok"] is False
    assert apply(4, {"n": "line\x00break"})["ok"] is False
    assert apply(4, {"n": ["x"] * 65})["ok"] is False
    assert apply(4, {f"k{i}": i for i in range(65)})["ok"] is False
    assert apply(4, {f"k{i}": "x" * 2000 for i in range(10)})["ok"] is False
    nested: dict = {"n": "leaf"}
    for _ in range(7):
        nested = {"n": nested}
    assert apply(4, nested)["ok"] is False


def test_seam_number_is_a_real_index():
    with pytest.raises(SeamRejected):
        apply(200, {})
    with pytest.raises(SeamRejected):
        apply(-1, {})
    with pytest.raises(SeamRejected):
        apply(True, {})  # type: ignore[arg-type]


def test_every_numbered_seam_is_wired():
    filler = GapFiller()
    names = filler.list()
    expected = [f"seam_{i:03d}" for i in range(200)]
    assert expected == [name for name in names if name.startswith("seam_")]
    for index in (0, 50, 179, 180, 199):
        name = f"seam_{index:03d}"
        payload = {"slot": index}
        record = filler.call(name, payload)
        assert record["ok"] is True
        assert record["seam"] == index
        assert record["data"] is payload
        assert record["digest"] == _digest(payload)
    refused = filler.call("seam_042", {"note": "password=nope"})
    assert refused == {"seam": 42, "ok": False, "error": "payload refused"}
    assert filler.call("seam_999", {}) == {"error": "seam not found", "name": "seam_999"}
