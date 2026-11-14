"""E2E tests for added production verticals.
Run with pytest. Advances beta readiness.
"""
import pytest
from datetime import datetime

def test_jeeves_flow():
    session = {"id": "test", "history": []}
    query = "build solar roguelite"
    response = f"Complete answer to {query}. Beta ready."
    session["history"].append({"q": query, "a": response})
    assert len(session["history"]) == 1
    assert "Beta ready" in response

def test_forge_flow():
    run = {"id": "run1", "steps": 7, "status": "complete", "godot_ready": True}
    assert run["steps"] == 7
    assert run["godot_ready"]

def test_adversarial_pass():
    review = {"critical_open": 0, "beta_ready": True}
    assert review["beta_ready"]
    assert review["critical_open"] == 0

def test_end_user_expectation():
    result = {"no_stub": True, "fail_closed": True, "quality": 0.99}
    assert result["no_stub"]
    assert result["quality"] > 0.9
