"""
Operational tests for full stack. Covers run, cache, health, and safety.
"""
import pytest
from skeleton.local_ai.full_stack import get_stack

def test_full_stack_run():
    stack = get_stack()
    out = stack.run("operational test", "valid_cas_string_16+")
    assert "out" in out
    assert out["safe"]["safe"] is True
    assert out["health"]["healthy"] is True

def test_full_stack_cache():
    stack = get_stack()
    first = stack.run("cached prompt", "valid_cas_string_16+")
    second = stack.run("cached prompt", "valid_cas_string_16+")
    assert second.get("cached") is True
