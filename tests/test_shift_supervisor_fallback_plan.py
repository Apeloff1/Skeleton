from core.shift_supervisor.fallback_plan import compile_fallback_state


def test_failover_is_issue_backed_bounded_and_deterministic():
    context = {
        "issues": [
            {"number": 1685, "title": "Advance autonomous repository builder", "body": "Preserve custody.", "labels": [{"name": "bug"}]},
            {"number": 540, "title": "Security hardening", "body": "Fail closed.", "labels": [{"name": "security-approved"}]},
            {"number": 1, "title": "[Shift Supervisor] Canonical Night + Idle Plan", "body": "state"},
        ]
    }
    first = compile_fallback_state(context)
    second = compile_fallback_state(context)
    assert len(first["plan_items"]) == 2
    assert [item["source_issue"] for item in first["plan_items"]] == [540, 1685]
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert all(item["planner"] == "deterministic-failover-v1" for item in first["plan_items"])


def test_failover_preserves_unfinished_prior_custody():
    prior = {"plan_items": [{"id": "existing", "title": "Existing", "description": "Keep", "status": "assigned", "target_team": "night"}], "workers": []}
    result = compile_fallback_state({"issues": [{"number": 2, "title": "New", "body": "Work", "labels": [{"name": "build-approved"}]}]}, prior)
    assert result["plan_items"][0]["id"] == "existing"


def test_failover_refuses_to_invent_work():
    import pytest
    with pytest.raises(RuntimeError, match="no authorized open issue"):
        compile_fallback_state({"issues": []})
