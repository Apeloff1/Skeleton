"""Fail-closed contract for the legacy operational local-AI facade.

Only the guarded canonical provider runtime can attest native inference.
"""
import pytest

from skeleton.local_ai.operational_engine import (
    LocalInferenceNotActivated,
    get_engine,
)
from skeleton.local_ai.gap_filler import GapFiller


def test_operational_generate_requires_canonical_activation():
    eng = get_engine()
    with pytest.raises(LocalInferenceNotActivated) as error:
        eng.generate("test prompt", "valid_cas_string_16+")
    assert error.value.code == "LOCAL_GGUF_NOT_ACTIVATED"


def test_cas_rejection_precedes_activation():
    with pytest.raises(PermissionError):
        get_engine().generate("x", "short")


@pytest.mark.parametrize(
    "prompt,max_tokens,error",
    [
        ("", 128, ValueError),
        ("prompt", 0, ValueError),
        ("prompt", 8193, ValueError),
        ("prompt", True, ValueError),
    ],
)
def test_invalid_generation_inputs_fail_before_activation(prompt, max_tokens, error):
    with pytest.raises(error):
        get_engine().generate(prompt, "valid_cas_string_16+", max_tokens=max_tokens)


def test_gap_filler_wires_seams():
    filler = GapFiller()
    seams = filler.list()
    assert len(seams) > 50
    if "seam_000" in seams:
        assert filler.call("seam_000", {"k": 1}).get("ok") is True


def test_status_does_not_claim_native_inference():
    st = get_engine().status()
    assert st["operational"] is False
    assert st["inference_ready"] is False
    assert st["readiness_code"] == LocalInferenceNotActivated.code
    assert st["provider_boundary"] == "skeleton.provider_runtime"
