"""ProjectsClient end to end through the REAL create_app + install_gate seal path.

Uses Internal Systems' ``tests.app_services.conftest::gated_client`` (#4097). Skips
when that fixture module or ``skeleton.api.projects_routes`` is not on the branch.
The client mints its own seal with ``skeleton.client.seal`` (stdlib HMAC) and sends
the session as ``Authorization: Bearer``; requests go through the TestClient's
in-process ASGI transport.
"""

from __future__ import annotations

import importlib.util

import pytest


def _present(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:
        return False


if not (_present("skeleton.api.projects_routes") and _present("tests.app_services.conftest")):
    pytest.skip(
        "needs #4097 (skeleton.api.projects_routes + tests.app_services.conftest)",
        allow_module_level=True,
    )

from tests.app_services.conftest import app_services, gated_client  # noqa: E402, F401

from skeleton.client import (  # noqa: E402
    GatewayClient,
    ProjectsClient,
    RequestSealer,
    SkeletonHTTPError,
)
from skeleton.client import projects as projects_mod  # noqa: E402


class _CountingSealer(RequestSealer):
    __slots__ = ("mints",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.mints = 0

    def _mint(self, now):
        self.mints += 1
        return super()._mint(now)


def _session(gated):
    return gated.headers["Authorization"].removeprefix("Bearer ")


def _pc(gated, *, seal=None, token=None, hits=None):
    tc = gated.client
    if hits is not None:
        tc.event_hooks["request"] = [lambda req: hits.append(req.url.path)]
    gw = GatewayClient(str(tc.base_url), client=tc, seal=seal)
    return ProjectsClient(gw, session_token=token or _session(gated))


def test_good_seal_and_session_full_flow(gated_client):  # noqa: F811
    sealer = _CountingSealer("test-sdk")
    pc = _pc(gated_client, seal=sealer)
    proj = pc.create("Gated SDK game", idempotency_key="create-1")
    assert proj.project_id
    again = pc.create("Gated SDK game", idempotency_key="create-1")
    assert again.project_id == proj.project_id
    assert any(p.project_id == proj.project_id for p in pc.list(limit=10))
    assert pc.get(proj.project_id).project_id == proj.project_id
    build = pc.start_build(proj.project_id, target="gb", idempotency_key="build-1")
    assert build.status == "queued" and build.execution_id == build.build_id
    replay = pc.start_build(proj.project_id, target="gb", idempotency_key="build-1")
    assert replay.build_id == build.build_id and replay.replayed is True
    page = pc.list_builds(proj.project_id, limit=1)
    assert [b.build_id for b in page] == [build.build_id]
    assert pc.get_build(proj.project_id, build.build_id).build_id == build.build_id
    assert sealer.mints == 1  # cached seal reused


def test_missing_seal_401_invalid_seal(gated_client):  # noqa: F811
    hits = []
    pc = _pc(gated_client, seal=None, hits=hits)
    with pytest.raises(SkeletonHTTPError) as ei:
        pc.list()
    assert ei.value.status_code == 401 and ei.value.code == "invalid_seal"
    assert len(hits) == 1  # no sealer -> nothing to re-mint


def test_bad_seal_remints_once_then_raises(gated_client):  # noqa: F811
    hits = []
    sealer = _CountingSealer("test-sdk", seal_secret="not-the-server-secret")
    pc = _pc(gated_client, seal=sealer, hits=hits)
    with pytest.raises(SkeletonHTTPError) as ei:
        pc.list()
    assert ei.value.status_code == 401 and ei.value.code == "invalid_seal"
    assert sealer.mints == 2 and len(hits) == 2  # exactly one re-mint + one retry


def test_seal_only_no_session_401_unauthenticated(gated_client):  # noqa: F811
    pc = _pc(gated_client, seal=RequestSealer("test-sdk"), token="not-a-session")
    with pytest.raises(SkeletonHTTPError) as ei:
        pc.list()
    assert ei.value.status_code == 401
    assert ei.value.code == projects_mod.PROJECT_ERROR_UNAUTHENTICATED


def test_idempotency_mismatch_409(gated_client):  # noqa: F811
    pc = _pc(gated_client, seal=RequestSealer("test-sdk"))
    proj = pc.create("Brief A", idempotency_key="mm-create")
    with pytest.raises(SkeletonHTTPError) as ei:
        pc.create("Brief B", idempotency_key="mm-create")
    assert ei.value.status_code == 409
    assert ei.value.code == projects_mod.PROJECT_ERROR_IDEMPOTENCY_MISMATCH
    pc.start_build(proj.project_id, target="a", idempotency_key="mm-build")
    with pytest.raises(SkeletonHTTPError) as ei:
        pc.start_build(proj.project_id, target="b", idempotency_key="mm-build")
    assert ei.value.status_code == 409
    assert ei.value.code == projects_mod.PROJECT_ERROR_IDEMPOTENCY_MISMATCH
