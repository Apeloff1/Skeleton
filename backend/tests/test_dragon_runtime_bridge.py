import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from core.dragon_runtime_bridge import install_dragon_runtime, dragon_foreground
from routes.gameforge_auth import require_role
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy


def configured_app():
    app=FastAPI()
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256),
        (PlanePolicy('interactive',2,ResourceVector(),1.),PlanePolicy('background',1,ResourceVector(),1.))))
    envelope=ResourceEnvelope(100,10,10000,3,1,1,10)
    pool=install_dragon_runtime(app,scheduler,envelope,hardware=lambda:HardwareSample(256*1024**2,4,.1,.9,True,False,10),clock=lambda:10)
    # Override the exact authentication dependency attached to the foreground adapter.
    auth_dependency=dragon_foreground.__defaults__[0].dependency
    app.dependency_overrides[auth_dependency]=lambda:{'email':'alice@example.test','tenant_id':'tenant','role':'viewer'}
    return app,pool,scheduler,envelope


def test_installer_preserves_shared_ledger_and_rejects_budget_reset():
    app,pool,scheduler,envelope=configured_app()
    assert app.state.dragon_practice_executor_factory.__self__ is pool
    assert pool.shared_resources is scheduler
    with pytest.raises(ValueError): install_dragon_runtime(app,scheduler,envelope)


def test_real_http_dependency_holds_foreground_until_response():
    app,pool,_,_=configured_app()
    background=pool.executor('other-owner')
    @app.post('/chat',dependencies=[Depends(dragon_foreground)])
    async def chat():
        assert background.foreground_waiting.is_set()
        return {'foreground':pool.status()['foreground_requests']}
    with TestClient(app) as client:
        assert client.post('/chat').json()=={'foreground':1}
    assert not background.foreground_waiting.is_set()


def test_http_exception_cleans_foreground_count():
    from fastapi import HTTPException
    app,pool,_,_=configured_app()
    @app.post('/chat',dependencies=[Depends(dragon_foreground)])
    async def chat(): raise HTTPException(status_code=409,detail='failed turn')
    with TestClient(app) as client: assert client.post('/chat').status_code==409
    assert pool.status()['foreground_requests']==0


def test_lifespan_mount_reuses_accounting_and_keeps_unconfigured_app_closed():
    from types import SimpleNamespace
    from core.dragon_runtime_bridge import mount_configured_dragon_runtime
    app=FastAPI();authority=SimpleNamespace(dragon_projection=None)
    assert mount_configured_dragon_runtime(app,authority)=={'resource_runtime_mounted':False,'conversation_binding_mounted':False}
    assert not hasattr(app.state,'dragon_practice_executor_factory')
    _,_,scheduler,envelope=configured_app()
    app.state.global_resource_scheduler=scheduler
    app.state.dragon_resource_envelope=envelope
    assert mount_configured_dragon_runtime(app,authority)['resource_runtime_mounted']
    original=app.state.dragon_execution_pool
    original.executor('alice').governor.tokens=10
    mount_configured_dragon_runtime(app,authority)
    assert app.state.dragon_execution_pool is original
    assert original.executor('alice').governor.tokens==10


def test_real_http_foreground_applies_and_restores_hardware_context_budget():
    from skeleton.contracts.context import ContextBudget
    from core.dragon_runtime_bridge import dragon_context_budget
    app,pool,_,_=configured_app()
    base=ContextBudget(128000,4096,0,2048,1024,40000,16000,16000)
    @app.post('/chat',dependencies=[Depends(dragon_foreground)])
    async def chat():
        bounded=dragon_context_budget(base)
        assert bounded.max_context_tokens==16384
        assert bounded.max_segment_tokens < base.max_segment_tokens
        return {'limit':bounded.max_context_tokens}
    with TestClient(app) as client: assert client.post('/chat').json()=={'limit':16384}
    assert dragon_context_budget(base) is base


def test_heavy_hardware_denies_provider_initialization_and_releases_foreground():
    from dataclasses import replace
    app,pool,_,_=configured_app()
    healthy=pool.hardware()
    pool.hardware=lambda:replace(healthy,thermal_limited=True)
    @app.post('/chat',dependencies=[Depends(dragon_foreground)])
    async def chat(): pytest.fail('provider must not initialize')
    with TestClient(app) as client: assert client.post('/chat').status_code==503
    assert pool.status()['foreground_requests']==0
