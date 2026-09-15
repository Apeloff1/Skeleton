"""Adversarial validation for Jeeves Cortex tract interchange."""

import math

import pytest

from skeleton.cortex import JeevesCortex
from skeleton.kernel.errors import CortexError


def _valid_payload():
    source = JeevesCortex()
    source.think("compile ttk hp dps recipe sim")
    source.acquire("left")
    return source.export_tract("left")


def test_legitimate_exported_tract_still_imports():
    payload = _valid_payload()
    target = JeevesCortex()

    out = target.import_tract(payload)

    assert out["copied"] >= 1
    assert out["slot"] == "left"


def test_unknown_tract_slot_fails_closed():
    payload = _valid_payload()
    payload["slot"] = "root-shell"

    with pytest.raises(CortexError, match="unknown slot"):
        JeevesCortex().import_tract(payload)


def test_declared_size_must_match_exemplars():
    payload = _valid_payload()
    payload["size"] = len(payload["exemplars"]) + 1

    with pytest.raises(CortexError, match="size"):
        JeevesCortex().import_tract(payload)


def test_boolean_declared_size_is_rejected():
    payload = _valid_payload()
    payload["exemplars"] = payload["exemplars"][:1]
    payload["size"] = True

    with pytest.raises(CortexError, match="size"):
        JeevesCortex().import_tract(payload)


def test_non_finite_exemplar_confidence_is_rejected():
    payload = _valid_payload()
    payload["exemplars"][0]["confidence"] = math.nan

    with pytest.raises(CortexError, match="confidence"):
        JeevesCortex().import_tract(payload)


def test_non_finite_exemplar_number_is_rejected():
    payload = _valid_payload()
    payload["exemplars"][0]["numbers"] = [math.inf]

    with pytest.raises(CortexError, match="number"):
        JeevesCortex().import_tract(payload)


def test_oversized_exemplar_text_is_rejected():
    payload = _valid_payload()
    payload["exemplars"][0]["text"] = "x" * 16_385

    with pytest.raises(CortexError, match="text limit"):
        JeevesCortex().import_tract(payload)


def test_exemplar_count_is_bounded_before_restore():
    payload = {
        "slot": "left",
        "backend": "test",
        "scale": "hemisphere",
        "exemplars": [{}] * 4097,
        "capabilities": [],
    }

    with pytest.raises(CortexError, match="exemplar limit"):
        JeevesCortex().import_tract(payload)


def test_model_state_sections_must_be_objects():
    payload = _valid_payload()
    payload["weights"] = ["not", "a", "snapshot"]

    with pytest.raises(CortexError, match="model state"):
        JeevesCortex().import_tract(payload)


def test_capability_fanout_is_bounded():
    payload = _valid_payload()
    payload["capabilities"] = [f"cap-{i}" for i in range(257)]

    with pytest.raises(CortexError, match="capability limit"):
        JeevesCortex().import_tract(payload)


def test_payload_must_be_json_shaped():
    payload = _valid_payload()
    payload["weights"] = {"bad": object()}

    with pytest.raises(CortexError, match="unsupported value type"):
        JeevesCortex().import_tract(payload)
