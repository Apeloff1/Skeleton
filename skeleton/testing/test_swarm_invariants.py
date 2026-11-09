from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_invariants import audit
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.swarm_integrity_routes import assert_runtime, audit_runtime


def test_invariant_audit_accepts_consistent_runtime() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    runtime.lease("w")
    report = audit(runtime)
    assert report.ok is True
    assert report.errors == ()


def test_invariant_audit_detects_worker_ownership_corruption() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    runtime.lease("w")
    runtime.worker("w").active.clear()
    report = audit(runtime)
    assert report.ok is False
    assert any("absent from worker active set" in error for error in report.errors)


def test_integrity_api_projects_counts() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("t", {}))
    data = audit_runtime(runtime=runtime)
    assert data["ok"] is True
    assert data["task_count"] == 1
    assert assert_runtime(runtime=runtime)["ok"] is True
