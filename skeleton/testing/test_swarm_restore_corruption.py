import math

import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_restore import validate_restore_state
from skeleton.agents.swarm_runtime import SwarmTask


def _queued_state() -> dict[str, object]:
    runtime = HardenedSwarmRuntime(max_tasks=8, max_workers=4)
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("t", {"x": 1}, max_attempts=3))
    return runtime.export_state()


def _leased_state() -> dict[str, object]:
    runtime = HardenedSwarmRuntime(max_tasks=8, max_workers=4)
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("t", {}))
    runtime.lease("w")
    return runtime.export_state()


def test_rejects_attempts_above_retry_budget() -> None:
    state = _queued_state()
    state["tasks"][0]["attempts"] = 4
    with pytest.raises(ValueError, match="invalid attempts"):
        validate_restore_state(state)


def test_rejects_negative_runtime_counter() -> None:
    state = _queued_state()
    state["counters"]["retries"] = -1
    with pytest.raises(ValueError, match="counter retries"):
        validate_restore_state(state)


def test_rejects_submitted_counter_below_resident_tasks() -> None:
    state = _queued_state()
    state["counters"]["submitted"] = 0
    with pytest.raises(ValueError, match="submitted counter"):
        validate_restore_state(state)


def test_rejects_negative_worker_counter() -> None:
    state = _queued_state()
    state["workers"][0]["completed"] = -1
    with pytest.raises(ValueError, match="worker completed"):
        validate_restore_state(state)


def test_rejects_nonfinite_lease_configuration() -> None:
    state = _queued_state()
    state["config"]["max_lease_seconds"] = math.inf
    with pytest.raises(ValueError, match="finite"):
        validate_restore_state(state)


def test_rejects_leased_task_without_deadline() -> None:
    state = _leased_state()
    state["tasks"][0]["lease_deadline"] = None
    with pytest.raises(ValueError, match="missing deadline"):
        validate_restore_state(state)


def test_rejects_non_leased_task_with_deadline() -> None:
    state = _queued_state()
    state["tasks"][0]["lease_deadline"] = 123.0
    with pytest.raises(ValueError, match="non-leased task has deadline"):
        validate_restore_state(state)


def test_rejects_duplicate_worker_active_task() -> None:
    state = _leased_state()
    state["workers"][0]["active"] = ["t", "t"]
    with pytest.raises(ValueError, match="duplicate active"):
        validate_restore_state(state)


def test_rejects_leased_task_missing_from_worker_active_set() -> None:
    state = _leased_state()
    state["workers"][0]["active"] = []
    with pytest.raises(ValueError, match="missing from worker active set"):
        validate_restore_state(state)


def test_rejects_non_mapping_payload() -> None:
    state = _queued_state()
    state["tasks"][0]["payload"] = ["not", "a", "mapping"]
    with pytest.raises(ValueError, match="payload"):
        validate_restore_state(state)


def test_restore_canonicalizes_identifiers_and_capabilities() -> None:
    state = _queued_state()
    state["tasks"][0]["id"] = "  t  "
    state["tasks"][0]["required_capabilities"] = [" gpu ", "", "gpu"]
    state["workers"][0]["id"] = "  w  "
    state["workers"][0]["capabilities"] = [" gpu ", "", "gpu"]

    clean = validate_restore_state(state)

    assert clean["tasks"][0]["id"] == "t"
    assert clean["tasks"][0]["required_capabilities"] == ["gpu"]
    assert clean["workers"][0]["id"] == "w"
    assert clean["workers"][0]["capabilities"] == ["gpu"]
