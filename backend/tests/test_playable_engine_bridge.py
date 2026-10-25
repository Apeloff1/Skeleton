"""Real route privacy, JWT, EngineChat and EngineText composition regressions."""
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from api_middleware import RoutePrivacyMiddleware
from backend.tests.test_engine_text import _TenantScopedInventoryFixture, _terminal
from backend.tests.test_playable_private_creation import project_boundary
from backend.tests.test_private_memory_boundary import memory_boundary
from core.engine_client import EngineClient, EngineClientConfig, EngineUnavailableError
from core.engine_text import EngineTextError
from core.route_privacy import current_route_privacy
from routes import playable, playable_access

REAL_CODEGEN = playable._codegen_quality_loop
HTML = '''<!DOCTYPE html><html><body style="margin:0;background:#123;color:white">
<canvas id="game"></canvas><script>
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d');
let state='menu',score=0,x=25,y=25,last=performance.now();
const keys={};let best=Number(localStorage.getItem('portal-best')||0);
function resize(){canvas.width=innerWidth;canvas.height=innerHeight}resize();
addEventListener('resize',resize);addEventListener('keydown',e=>keys[e.key]=true);
addEventListener('keyup',e=>keys[e.key]=false);
canvas.addEventListener('pointerdown',()=>{state='playing';x=25;y=25});
function loop(timestamp){const delta=Math.min((timestamp-last)/1000,.05);last=timestamp;
if(state==='playing'){x+=(keys.ArrowRight?1:keys.ArrowLeft?-1:0)*100*delta;
y+=(keys.ArrowDown?1:keys.ArrowUp?-1:0)*100*delta;
if(x>canvas.width-70&&y>canvas.height-70){state='win';score++;best=Math.max(best,score);localStorage.setItem('portal-best',best)}}
ctx.fillStyle='#123';ctx.fillRect(0,0,canvas.width,canvas.height);
ctx.fillStyle='#4e8';ctx.fillRect(canvas.width-60,canvas.height-60,40,40);
ctx.fillStyle='cyan';ctx.fillRect(x,y,20,20);ctx.fillStyle='white';
ctx.fillText('Score '+score+' '+state+' Best '+best,10,18);requestAnimationFrame(loop)}
requestAnimationFrame(loop);</script></body></html>'''


@pytest.fixture
def bridge(project_boundary, monkeypatch):
    _, headers, users, database = project_boundary
    commands, route_contexts = [], []
    class Client(_TenantScopedInventoryFixture):
        config = EngineClientConfig(base_url="http://engine.test", execution_timeout_s=5)
        failure = None
        async def execute(self, command):
            commands.append(command)
            route_contexts.append(current_route_privacy())
            if self.failure:
                raise self.failure
            text = ('{"overall":100,"playability":100,"coherence":100,"fun":100,"polish":100}'
                    if 'Score this game.' in command.compiled_context.prompt else HTML)
            return replace(_terminal(command.execution_request.execution_id),
                           operation_id=command.operation.operation_id, final_output=text)
    engine = Client()
    monkeypatch.setattr(EngineClient, "from_env", classmethod(lambda cls, **kwargs: engine))
    monkeypatch.setattr(playable, "_codegen_quality_loop", REAL_CODEGEN)
    monkeypatch.setenv("AI_ARCHITECTURE_ROOT", str(Path(__file__).resolve().parents[2]))
    app = FastAPI()
    app.add_middleware(RoutePrivacyMiddleware)
    app.include_router(playable.router)
    for prefix in ["/api/unknown-legacy-surface", "/api/health"]:
        router = playable_access.project_router(prefix=prefix)
        @router.post("/model-probe")
        async def probe():
            try:
                return await asyncio.to_thread(playable._llm_in_thread, "private context", playable._GAME_SYS_FAST, ["hint"])
            except playable.PlayableModelFailure as exc:
                raise HTTPException(503, exc.public()) from exc
        app.include_router(router)
    with TestClient(app) as client:
        yield client, headers, database, engine, commands, route_contexts


def test_real_middleware_and_engine_text_bridge_generates_with_confidential_scope(bridge):
    client, headers, db, _, commands, contexts = bridge
    # Repeat in the same serving process: each generation crosses its worker
    # loop and the real immutable EngineText request/compiled-command boundary.
    for _ in range(2):
        result = client.post("/api/playable/generate", headers=headers["alice"],
                             json={"brief": "Original tiny square reaches green portal", "depth": "fast"})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "ready"
        assert result.json()["provider"] == "skeleton-engine"
        assert result.json()["model"] == "engine-routed"
        assert result.json()["engine_execution_id"]
        assert result.json()["engine_provider_receipts"] == ["provider:one"]
    assert len(commands) == 4
    assert [command.execution_request.resource_budget["max_output_tokens"] for command in commands] == [1024, 256, 1024, 256]
    assert all(context.domain == "studio" and context.max_data_class.label == "confidential" for context in contexts)
    for command in commands:
        assert command.operation.actor_id == "alice@example.test"
        assert command.operation.tenant_id == "tenant-a"
        assert command.compiled_context.data_class == "confidential"
    pid = db.playables.rows[0]["playable_id"]
    assert client.get(f"/api/playable/{pid}/raw", headers=headers["bob"]).status_code == 404
    assert client.get(f"/api/playable/{pid}/raw").status_code == 401
    assert len(commands) == 4


@pytest.mark.parametrize("path", ["/api/unknown-legacy-surface/model-probe", "/api/health/model-probe"])
def test_real_engine_bridge_keeps_public_and_legacy_privacy_denials(bridge, path):
    client, headers, db, _, commands, _ = bridge
    result = client.post(path, headers=headers["alice"])
    assert result.status_code == 503 and result.json()["detail"]["error_code"] == "project_model_transfer_denied"
    assert commands == [] and db.playables.rows == []


def test_uncertain_engine_dispatch_is_not_retried_repaired_or_persisted(bridge):
    client, headers, db, engine, commands, _ = bridge
    engine.failure = EngineUnavailableError("private transport detail")
    response = client.post("/api/playable/generate", headers=headers["alice"],
                           json={"brief": "Original tiny square reaches green portal", "depth": "fast"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error_code"] == "project_model_execution_unconfirmed" and detail["retry_same_request"] is True
    assert detail["engine_request_key"].startswith("engine-chat:")
    assert "private transport detail" not in response.text
    assert len(commands) == 1 and db.playables.rows == []


def test_old_unconfirmed_job_is_observed_without_time_based_failure_or_replacement(bridge):
    client, headers, db, _, commands, _ = bridge
    db.playable_jobs.rows.append({"job_id": "retained-job", "job_status": "unconfirmed",
        "owner_id": "alice@example.test", "tenant_id": "tenant-a",
        "engine_request_key": "engine-chat:retained",
        "created_at": (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()})
    response = client.get("/api/playable/job/retained-job", headers=headers["alice"])
    assert response.status_code == 200 and response.json()["job_status"] == "unconfirmed"
    assert response.json()["engine_request_key"] == "engine-chat:retained"
    assert commands == [] and not any(call[0] == "update" for call in db.playable_jobs.calls)


@pytest.mark.asyncio
async def test_uncertain_job_retains_nonterminal_custody_and_safe_request_key(monkeypatch):
    updates = []
    async def authorize(**kwargs):
        return {"tenant_id": "tenant-a", "owner_id": "alice"}
    class Jobs:
        async def update_one(self, query, update):
            updates.append((query, update))
    from types import SimpleNamespace
    monkeypatch.setattr(playable, "reauthorize_project_context", authorize)
    monkeypatch.setattr(playable, "_db", SimpleNamespace(playable_jobs=Jobs()))
    async def uncertain():
        raise playable.PlayableModelFailure("project_model_execution_unconfirmed", unconfirmed=True,
                                           request_key="engine-chat:retained")
    await playable._run_job("job", uncertain())
    value = updates[0][1]["$set"]
    assert value["job_status"] == "unconfirmed" and value["engine_request_key"] == "engine-chat:retained"
    assert value["retry_same_request"] is True and "playable_id" not in value
