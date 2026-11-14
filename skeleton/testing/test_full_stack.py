"""Source-only legacy facade qualification; never fabricate model output."""
import pytest

from skeleton.local_ai.full_stack import get_stack
from skeleton.local_ai.operational_engine import LocalInferenceNotActivated


def test_full_stack_run_requires_activated_native_inference():
    stack = get_stack()
    with pytest.raises(LocalInferenceNotActivated) as denied:
        stack.run("operational test", "valid_cas_string_16+")
    assert denied.value.code == "LOCAL_GGUF_NOT_ACTIVATED"
    assert stack.engine.status()["inference_ready"] is False


def test_full_stack_denial_never_caches_fabricated_output():
    stack = get_stack()
    for _ in range(2):
        with pytest.raises(LocalInferenceNotActivated):
            stack.run("cached prompt", "valid_cas_string_16+")
    assert not stack.cache.get("cached prompt", "valid_cas_string_16+")
