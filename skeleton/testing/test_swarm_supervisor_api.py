import pytest
from fastapi import HTTPException
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.api.swarm_supervisor_routes import DispatchRequest, QuarantineRequest, dispatch_preview, quarantine, release


def test_dispatch_preview_selects_registered_worker() -> None:
    runtime = SwarmRuntime(); runtime.register_worker("w", capabilities=["gpu"])
    result = dispatch_preview(DispatchRequest(task_id="t", required_capabilities=["gpu"]), runtime=runtime)
    assert result["accepted"] is True and result["worker_id"] == "w"


def test_quarantine_removes_worker_from_dispatch() -> None:
    runtime = SwarmRuntime(); runtime.register_worker("isolated")
    quarantine("isolated", QuarantineRequest(reason="operator"), runtime=runtime)
    result = dispatch_preview(DispatchRequest(task_id="t"), runtime=runtime)
    assert result["worker_id"] != "isolated"
    assert release("isolated")["released"] is True


def test_quarantine_unknown_worker_returns_404() -> None:
    with pytest.raises(HTTPException) as exc:
        quarantine("missing", QuarantineRequest(reason="x"), runtime=SwarmRuntime())
    assert exc.value.status_code == 404
