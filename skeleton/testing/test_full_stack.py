"""Legacy full-stack facade must never fabricate local AI inference.

Real user chat is qualified through the guarded canonical provider runtime.
A compatibility facade without a model/tokenizer/guard must refuse generation
rather than return mock text or cache an unverified response.
"""
import pytest

from skeleton.local_ai.full_stack import get_stack
from skeleton.local_ai.operational_engine import LocalInferenceNotActivated


def test_full_stack_run_requires_activated_canonical_provider():
    stack = get_stack()
    with pytest.raises(LocalInferenceNotActivated) as error:
        stack.run("operational test", "valid_cas_string_16+")
    assert error.value.code == "LOCAL_GGUF_NOT_ACTIVATED"
    assert stack.engine.status()["inference_ready"] is False
    assert stack.cache.get("operational test", "valid_cas_string_16+") is None


def test_full_stack_cache_never_stores_unqualified_generation():
    stack = get_stack()
    for _ in range(2):
        with pytest.raises(LocalInferenceNotActivated):
            stack.run("cached prompt", "valid_cas_string_16+")
    assert stack.cache.get("cached prompt", "valid_cas_string_16+") is None
