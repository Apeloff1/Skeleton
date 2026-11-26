"""Office queue, forge charter fail-closed, and the degraded golden brief."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.agents.studio_office import OfficeQueue, loopback_allowed, reset_office
from skeleton.api.hmac_seal import mint_seal
from skeleton.api.routes import router
from skeleton.api.server import get_state, skeleton_error_handler
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS
from skeleton.kernel.errors import SkeletonError

SECRET = "studio-office"
ACTOR = "office"
TENANT = "default"


def _tools(**overrides):
    base = {
        "doctor": lambda **kwargs: {"ok": True, "green": True, "codes": []},
        "game_build": lambda **kwargs: {
            "ok": True,
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": True,
            "degraded_reason": "missing-godot-binary",
            "playtest_status": "unavailable",
            "code": None,
        },
        "job_status": lambda **kwargs: {"ok": True, "status": "succeeded", "code": None, "execution_id": kwargs.get("execution_id")},
        "list_projects": lambda **kwargs: {"ok": False, "code": "projects_unavailable", "items": []},
        "playtest": lambda **kwargs: {"ok": True, "code": "passed", "agent_taxonomy": "passed", "godot_ran": False, "core_loop_ok": False},
    }
    base.update(overrides)
    return base


def _wait(queue: OfficeQueue, run_id: str) -> dict:
    deadline = time.time() + 2
    last = None
    while time.time() < deadline:
        last = queue.get(run_id, actor_id=ACTOR, tenant_id=TENANT)
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.02)
    raise AssertionError(last)


def test_loopback_default_refuses_remote_hosts(monkeypatch):
    monkeypatch.delenv("SKELETON_OFFICE_ALLOW_REMOTE", raising=False)
    assert loopback_allowed("127.0.0.1") is True
    assert loopback_allowed("::1") is True
    assert loopback_allowed("testclient") is True
    assert loopback_allowed("8.8.8.8") is False
    assert loopback_allowed(None) is False


def test_doctor_red_does_not_build_and_records_codes():
    built: list[object] = []
    queue = OfficeQueue(store=lambda view: None, tools=_tools(
        doctor=lambda **kwargs: {"ok": True, "green": False, "codes": ["configuration_blocked"]},
        game_build=lambda **kwargs: built.append(kwargs) or {"ok": True},
    ))
    run = queue.submit_golden(actor_id=ACTOR, tenant_id=TENANT, inline=True)
    assert run["status"] == "failed"
    assert run["error"]["code"] == "doctor_red"
    assert run["result"]["codes"] == ["configuration_blocked"]
    assert built == []
    assert run["status_history"] == ["queued", "running", "failed"]
    assert any("configuration_blocked" in step["thought"] for step in run["steps"])
    assert "CORE_LOOP_OK" not in " ".join(step["thought"] for step in run["steps"])
    assert run["heartbeat_seq"] >= 1


def test_green_doctor_degraded_godot_does_not_claim_core_loop_ok():
    seen: dict[str, object] = {}

    def game_build(**kwargs):
        seen.update(kwargs)
        return {
            "ok": True,
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": True,
            "degraded_reason": "missing-godot-binary",
            "playtest_status": "unavailable",
            "compiler_marker": "cleared:1:gold:4",
            "code": None,
        }

    queue = OfficeQueue(store=lambda view: None, tools=_tools(game_build=game_build))
    run = queue.submit_golden(actor_id=ACTOR, tenant_id=TENANT, inline=True)
    brief = next(item["brief"] for item in GOLDEN_BRIEFS if item["id"] == "top_down_shooter")
    assert seen["brief"] == brief
    assert seen["playtest"] == "auto"
    assert run["status"] == "succeeded"
    assert run["result"]["core_loop_ok"] is False
    assert run["result"]["degraded"] is True
    assert run["result"]["godot_ran"] is False
    assert run["brief_id"] == "top_down_shooter"
    thoughts = " ".join(step["thought"] for step in run["steps"])
    assert "godot_did_not_prove" in thoughts
    assert "CORE_LOOP_OK" not in thoughts


def test_godot_boot_surfaces_core_loop_ok_from_tool_output():
    queue = OfficeQueue(store=lambda view: None, tools=_tools(game_build=lambda **kwargs: {
        "ok": True,
        "godot_ran": True,
        "core_loop_ok": True,
        "degraded": False,
        "playtest_status": "passed",
        "code": None,
    }))
    run = queue.submit_golden(actor_id=ACTOR, tenant_id=TENANT, inline=True)
    assert run["status"] == "succeeded"
    assert run["result"]["core_loop_ok"] is True
    assert any("CORE_LOOP_OK" in step["thought"] for step in run["steps"])


def test_advise_charter_refuses_a_build_and_missing_projects_fail_closed():
    built: list[object] = []
    queue = OfficeQueue(store=lambda view: None, tools=_tools(game_build=lambda **kwargs: built.append(kwargs)))
    refused = queue.submit(
        "job_watcher",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={"brief": "do not build", "execution_id": "job-1"},
        inline=True,
    )
    assert refused["status"] == "failed"
    assert refused["error"]["code"] == "autonomy_advise"
    assert refused["steps"] == []
    assert built == []

    watched = queue.submit(
        "job_watcher",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={"execution_id": "job-1"},
        inline=True,
    )
    assert watched["status"] == "failed"
    assert watched["error"]["code"] == "projects_unavailable"
    assert any("projects_unavailable" in step["thought"] for step in watched["steps"])


def test_cancel_during_a_tool_and_other_tenant_is_hidden():
    started = []

    def doctor(**kwargs):
        started.append(time.time())
        time.sleep(0.3)
        return {"ok": True, "green": True, "codes": []}

    queue = OfficeQueue(store=lambda view: None, tools=_tools(doctor=doctor))
    queued = queue.submit("doctor", actor_id=ACTOR, tenant_id=TENANT, params={})
    assert queued["status"] in {"queued", "running"}
    deadline = time.time() + 1
    while not started and time.time() < deadline:
        time.sleep(0.01)
    cancelled = queue.cancel(queued["run_id"], actor_id=ACTOR, tenant_id=TENANT)
    finished = _wait(queue, queued["run_id"])
    assert cancelled["status"] == "cancelled" or finished["status"] == "cancelled"
    assert finished["status"] == "cancelled"
    assert finished["heartbeat_seq"] >= 1
    with pytest.raises(KeyError):
        queue.get(queued["run_id"], actor_id="other", tenant_id=TENANT)


def test_list_projects_fails_closed_when_the_store_cannot_open(monkeypatch):
    from skeleton.skills.studio_office_tools import tool_list_projects

    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr("skeleton.app_services.runtime.get_app_services", boom)
    missing = tool_list_projects(actor_id=ACTOR, tenant_id=TENANT)
    assert missing["ok"] is False
    assert missing["code"] == "projects_unavailable"
    assert missing["items"] == []
    assert tool_list_projects()["code"] == "projects_unavailable"


def test_run_is_readable_after_the_process_cache_is_dropped(monkeypatch):
    from skeleton.forge import game_build_queue

    backend = game_build_queue._FallbackQueue()
    monkeypatch.setattr(game_build_queue, "_real_api", lambda: None)
    monkeypatch.setattr(game_build_queue, "_fallback", backend)
    office = OfficeQueue(tools=_tools())
    run = office.submit("doctor", actor_id=ACTOR, tenant_id=TENANT, params={}, inline=True)
    assert run["status"] == "succeeded"
    office._runs.clear()
    loaded = office.get(run["run_id"], actor_id=ACTOR, tenant_id=TENANT)
    assert loaded["schema_version"] == "skeleton.studio_office_run.v1"
    assert loaded["run_id"] == run["run_id"]
    assert loaded["status"] == "succeeded"
    assert loaded["charter_id"] == "doctor"
    with pytest.raises(KeyError):
        office.get(run["run_id"], actor_id="other", tenant_id=TENANT)


def test_queue_store_failure_is_job_unavailable():
    def boom(view):
        del view
        raise RuntimeError("disk")

    office = OfficeQueue(tools=_tools(), store=boom)
    run = office.submit("doctor", actor_id=ACTOR, tenant_id=TENANT, params={}, inline=True)
    assert run["status"] == "failed"
    assert run["error"]["code"] == "job_unavailable"


def test_advise_waits_for_accept_and_reject_does_not_build():
    built: list[object] = []

    def game_build(**kwargs):
        built.append(kwargs["brief"])
        return {
            "ok": True,
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": True,
            "degraded_reason": "missing-godot-binary",
            "code": None,
        }

    office = OfficeQueue(store=lambda view: None, tools=_tools(game_build=game_build))
    proposed = office.submit(
        "game_builder",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={"brief": "ash tunnels", "playtest": "auto", "autonomy": "advise"},
        inline=True,
    )
    assert proposed["status"] == "succeeded"
    assert proposed["result"]["awaiting_accept"] is True
    assert proposed["result"]["proposal"]["tool"] == "game_build"
    assert built == []
    accepted = office.accept(proposed["run_id"], actor_id=ACTOR, tenant_id=TENANT)
    assert built == ["ash tunnels"]
    assert accepted["status"] == "succeeded"
    assert accepted["result"]["applied"] is True
    assert accepted["result"]["core_loop_ok"] is False

    declined = office.submit(
        "game_builder",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={"brief": "do not build", "playtest": "auto", "autonomy": "advise"},
        inline=True,
    )
    rejected = office.reject(declined["run_id"], actor_id=ACTOR, tenant_id=TENANT)
    assert rejected["status"] == "failed"
    assert rejected["error"]["code"] == "proposal_rejected"
    assert built == ["ash tunnels"]
    waiting = office.submit(
        "game_builder",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={"brief": "cancel me", "autonomy": "advise"},
        inline=True,
    )
    cancelled = office.cancel(waiting["run_id"], actor_id=ACTOR, tenant_id=TENANT)
    assert cancelled["status"] == "cancelled"
    assert built == ["ash tunnels"]


def test_doctor_codes_and_asset_stub_use_existing_names():
    import hashlib
    import json

    from skeleton.forge.asset_manifest import STUB, asset_manifest_files
    from skeleton.skills.studio_office_tools import doctor_codes

    codes = doctor_codes({
        "services_ready": False,
        "ai": {
            "configuration_code": "local_model_not_configured",
            "readiness_code": "local_guard_unavailable",
        },
        "checks": {
            "host": [
                {"ok": False, "code": "host:docker"},
                {"ok": True, "code": "host:python"},
            ],
        },
    })
    assert codes == ["local_model_not_configured", "local_guard_unavailable", "host:docker"]
    assert doctor_codes({"ai": {"configuration_code": "not-a-doctor-code"}}) == ["doctor_unavailable"]
    stubbed = json.loads(asset_manifest_files({"project.godot": "config_version=5\n"})["assets/manifest.json"])
    assert stubbed["schema"] == "skeleton.forge.asset_manifest.v1"
    assert stubbed["version"] == 1
    assert stubbed["stubbed"] == STUB
    assert stubbed["assets"] == []
    copied = json.loads(asset_manifest_files({"project.godot": "x", "sprites/hero.png": "png"})["assets/manifest.json"])
    assert copied["stubbed"] is None
    assert copied["assets"][0]["sha256"] == hashlib.sha256(b"png").hexdigest()


def test_loopback_mcp_lists_tools_and_reads_a_fixture(monkeypatch):
    import json
    import socket

    from skeleton.agents.studio_office import OfficeRejected
    from skeleton.api.office_mcp import OfficeMcpServer

    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("SKELETON_OFFICE_ALLOW_REMOTE", raising=False)
    office = OfficeQueue(store=lambda view: None, tools=_tools())
    run = office.submit("doctor", actor_id=ACTOR, tenant_id=TENANT, params={}, inline=True)
    server = OfficeMcpServer(queue=office, tools=office._tools)
    host, port = server.serve()
    seal = mint_seal(ACTOR, secret=SECRET)

    def rpc(method: str, params: dict) -> dict:
        params = {"seal": seal, "tenant": TENANT, **params}
        with socket.create_connection((host, port), timeout=2) as sock:
            sock.sendall(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode() + b"\n")
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(65536)
                assert chunk
                data += chunk
        return json.loads(data.split(b"\n", 1)[0])

    try:
        listed = rpc("tools/list", {})
        names = {item["name"] for item in listed["result"]["tools"]}
        assert {"doctor", "game_build", "job_status", "list_projects", "office_golden", "office_run_status", "office_cancel"} <= names
        doctor = rpc("tools/call", {"name": "doctor", "arguments": {"live": False}})
        assert doctor["result"]["green"] is True
        status = rpc("tools/call", {"name": "office_run_status", "arguments": {"run_id": run["run_id"]}})
        assert status["result"]["run"]["status"] == "succeeded"
        assert status["result"]["run"]["run_id"] == run["run_id"]
    finally:
        server.close()
    refused = OfficeMcpServer(queue=office)
    with pytest.raises(OfficeRejected) as caught:
        refused.serve("8.8.8.8")
    assert caught.value.code == "office_loopback_only"


def test_playtest_charter_uses_the_scripted_agent_not_a_builder():
    from skeleton.skills.studio_office_tools import tool_playtest

    built: list[object] = []
    queue = OfficeQueue(store=lambda view: None, tools=_tools(
        playtest=tool_playtest,
        game_build=lambda **kwargs: built.append(kwargs),
    ))
    missing = queue.submit("playtest", actor_id=ACTOR, tenant_id=TENANT, params={"genre": "top_down_shooter"}, inline=True)
    assert missing["error"]["code"] == "playtest_input_missing"
    run = queue.submit(
        "playtest",
        actor_id=ACTOR,
        tenant_id=TENANT,
        params={
            "genre": "top_down_shooter",
            "frames": 4,
            "content": {
                "player_hp": 100,
                "economy": {"starting_balance": 5, "sink_cost": 1},
                "encounters": [{"hp": 1, "player_damage": 1, "enemy_damage": 0, "loot": 1}],
                "longform": {"completed": True, "ending_id": "return"},
            },
        },
        inline=True,
    )
    assert run["status"] == "succeeded"
    assert run["result"]["agent_taxonomy"] == "passed"
    assert run["result"]["godot_ran"] is False
    assert run["result"]["core_loop_ok"] is False
    assert built == []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    state = get_state()
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    reset_office(OfficeQueue(store=lambda view: None, tools=_tools()))
    with TestClient(app, raise_server_exceptions=False) as api:
        yield api
    reset_office()
    del state


def _headers(**extra):
    headers = {"x-gf-seal": mint_seal(ACTOR, secret=SECRET), "x-skeleton-tenant": TENANT}
    headers.update(extra)
    return headers


def test_office_routes_stay_on_the_forge_charter():
    from skeleton.api.middleware import GatePolicy

    policy = GatePolicy()
    assert policy.required_domain("/api/v1/game/office/golden") == "forge"
    assert policy.required_domain("/api/v1/game/office/runs/run-1/stream") == "forge"
    assert policy.required_domain("/api/v1/game/office-extra") is None


def test_office_api_charter_and_golden_contract(client):
    denied = client.post("/api/v1/game/office/golden", json={})
    assert denied.status_code == 401
    light = client.post("/api/v1/game/office/golden", json={}, headers=_headers(**{"x-gf-actor-weight": "-1"}))
    assert light.status_code == 403
    assert light.json()["detail"]["error"] == "charter_denied"
    swapped = client.post("/api/v1/game/office/golden", json={"brief": "a different game"}, headers=_headers())
    assert swapped.status_code == 422
    planted = client.post("/api/v1/game/office/runs", json={"charter_id": "doctor", "out": "/tmp/plant"}, headers=_headers())
    assert planted.status_code == 422
    foreign = client.post("/api/v1/game/office/runs", json={"charter_id": "doctor", "actor_id": "someone-else"}, headers=_headers())
    assert foreign.status_code == 422
    unknown = client.post("/api/v1/game/office/runs", json={"charter_id": "mercenary"}, headers=_headers())
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["error"] == "unknown_charter"
    accepted = client.post("/api/v1/game/office/golden", json={"frames": 4}, headers=_headers())
    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["status_ref"] == f"/api/v1/game/office/runs/{body['run_id']}"
    assert body["stream_ref"].endswith("/stream")
    deadline = time.time() + 2
    polled = None
    while time.time() < deadline:
        polled = client.get(body["status_ref"], headers=_headers())
        assert polled.status_code == 200, polled.text
        if polled.json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert polled is not None
    payload = polled.json()
    assert payload["status"] == "succeeded"
    assert payload["result"]["degraded"] is True
    assert payload["result"]["core_loop_ok"] is False
    assert payload["schema_version"] == "skeleton.studio_office_run.v1"
    hidden = client.get(body["status_ref"], headers=_headers(**{"x-skeleton-tenant": "other"}))
    assert hidden.status_code == 404
    charters = client.get("/api/v1/game/office/charters", headers=_headers())
    assert charters.status_code == 200
    ids = {row["charter_id"] for row in charters.json()["charters"]}
    assert ids == {"doctor", "game_builder", "playtest", "job_watcher"}


def test_office_stream_replays_terminal_events(client):
    accepted = client.post("/api/v1/game/office/golden", json={}, headers=_headers())
    run_id = accepted.json()["run_id"]
    deadline = time.time() + 2
    while time.time() < deadline:
        if client.get(f"/api/v1/game/office/runs/{run_id}", headers=_headers()).json()["status"] == "succeeded":
            break
        time.sleep(0.02)
    with client.stream("GET", f"/api/v1/game/office/runs/{run_id}/stream", headers=_headers()) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "operation.completed" in text
    assert "CORE_LOOP_OK" not in text


def test_remote_client_is_refused(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("SKELETON_OFFICE_ALLOW_REMOTE", raising=False)
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    reset_office(OfficeQueue(store=lambda view: None, tools=_tools()))
    with TestClient(app, client=("8.8.8.8", 1234), raise_server_exceptions=False) as api:
        response = api.post("/api/v1/game/office/golden", json={}, headers=_headers())
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "office_loopback_only"
    reset_office()
