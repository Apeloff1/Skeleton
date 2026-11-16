"""Signed co-hosted composition and server lifecycle regressions."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from skeleton.app import protected_stack as s
from skeleton.app.canonical_writer_cutover import CanonicalWriterCutover, VerifiedWriterCutover
from skeleton.ai.runtime.inference.native_guard_binding import NativeGuardPins


def launch_fixture(**updates):
    signer=Ed25519PrivateKey.generate()
    key=signer.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    reviewer=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    now=int(time.time())
    writer=CanonicalWriterCutover(authority_id="operator",deployment_id="live-stack",source_head="a"*40,
        database_name="canonical",replica_set="rs",voting_hosts=("db:27017",),
        principal_inventory=(("admin","writer"),("ROLE_BOUNDARY",""),("canonical","readWrite")),
        issued_at=now-10,expires_at=now+300,epoch_count=1,source_scope_count=1,
        inventory_sha256="1"*64,backup_sha256="2"*64,quiescence_sha256="3"*64,
        external_writer_retirement_sha256="4"*64,storage_provenance_sha256="5"*64,
        predecessor_generation=0,predecessor_latch_sha256=None)
    verified=VerifiedWriterCutover(writer,signer.sign(writer.canonical_bytes()),
        writer.authority_id,writer.deployment_id,writer.source_head,key)
    values=dict(authority_id=writer.authority_id,deployment_id=writer.deployment_id,
        source_head=writer.source_head,writer_plan_sha256=hashlib.sha256(writer.canonical_bytes()).hexdigest(),
        issued_at=now-5,expires_at=now+300,backend_port=8001,engine_port=8010,
        reviewer_endpoint="https://independent.example:8443",
        reviewer_authority="reviewer",reviewer_domain="isolated",reviewer_public_key_hex=reviewer.hex(),
        reviewer_ca_sha256="6"*64,reviewer_client_cert_sha256="7"*64,policy_sha256="8"*64,
        memory_namespace="assistant",probe_tenant_id="tenant",probe_actor_id="actor",
        probe_context_id="context",active_model_id="native",
        models=(NativeGuardPins("native","9"*64,"a"*64,"b"*64),))
    values.update(updates)
    p=s.ProtectedStackLaunchPlan(**values)
    return s.VerifiedProtectedStackLaunch(p,verified,signer.sign(p.canonical_bytes()),key)


def test_signed_plan_parse_and_exact_writer_binding():
    launch=launch_fixture()
    plan=s.ProtectedStackLaunchPlan.parse(json.dumps(launch.plan.document()).encode())
    assert plan==launch.plan
    with pytest.raises(s.ProtectedStackDenied):
        replace(launch,plan=replace(plan,policy_sha256="c"*64))
    with pytest.raises(s.ProtectedStackDenied):
        replace(launch,writer_approval=launch_fixture().writer_approval)
    with pytest.raises(s.ProtectedStackDenied):
        s.ProtectedStackLaunchPlan.parse(json.dumps(plan.document()).encode()[:-1]+b',"source_head":"other"}')


@pytest.mark.parametrize("updates",[
    {"writer_plan_sha256":"f"*64},{"backend_port":8010},{"backend_port":True},
    {"reviewer_endpoint":"http://reviewer.example"},{"reviewer_endpoint":"https://user:pass@reviewer.example"},
    {"reviewer_endpoint":"https://reviewer.example/path"},{"reviewer_domain":"operator"},
    {"policy_sha256":"0"*64},{"active_model_id":"wrong"},{"probe_actor_id":"bad\nactor"},
    {"models":(NativeGuardPins("native","0"*64,"a"*64,"b"*64),)},
])
def test_launch_denies_wrong_identity_or_unsafe_configuration(updates):
    with pytest.raises(s.ProtectedStackDenied):
        launch_fixture(**updates)


def env():
    return {"AI_PROVIDER":"local","SKELETON_INTERNAL_URL":"http://127.0.0.1:8010",
            "SKL_ENGINE_SERVICE_TOKEN":"x"*64,"AI_LOCAL_MODEL_PATH":"/models/native"}


@pytest.mark.parametrize("change",[
    {"AI_PROVIDER":"openai"},{"SKELETON_INTERNAL_URL":"http://localhost:8010"},
    {"SKL_ENGINE_SERVICE_TOKEN":"short"},{"AI_LOCAL_DEPLOYMENT_PATH":"/other"},
    {"AI_LOCAL_MODEL_PATH":""},{"AI_SECONDARY_MODEL":"external"},{"AI_VERIFICATION_MODEL":"external"},
])
def test_local_config_is_observation_not_rewrite(change):
    values=env()
    values.update(change)
    before=dict(values)
    with pytest.raises(s.ProtectedStackDenied):
        s.assert_local_configuration(launch_fixture(),values)
    assert values==before


def registry_fixture():
    local=SimpleNamespace(model="native",available=True,require_guarded_inference=True,guarded_service=object())
    registry=SimpleNamespace(active_id="local",available=True,active=local,_fallback_ids=(),
                statuses=lambda:[{"id":"local","model":"native","available":True}],
                require_selected=lambda provider,model:local)
    return SimpleNamespace(engine_execution_coordinator=SimpleNamespace(provider_registry=registry)),registry,local


def test_loaded_actual_registry_required():
    state,registry,local=registry_fixture()
    launch=launch_fixture()
    assert s.verify_loaded_registry(launch,state) is registry
    local.guarded_service=None
    with pytest.raises(s.ProtectedStackDenied):
        s.verify_loaded_registry(launch,state)


@pytest.mark.parametrize("change",[
    lambda r,a:setattr(r,"active_id","openai"),
    lambda r,a:setattr(r,"_fallback_ids",("openai",)),
    lambda r,a:setattr(a,"model","other"),
    lambda r,a:setattr(a,"require_guarded_inference",False),
    lambda r,a:setattr(r,"statuses",lambda:[{"id":"local","model":"native","available":False}]),
])
def test_unavailable_extra_or_unguarded_route_cannot_start_backend(change):
    state,registry,local=registry_fixture()
    change(registry,local)
    with pytest.raises(s.ProtectedStackDenied):
        s.verify_loaded_registry(launch_fixture(),state)


class FakeServer:
    def __init__(self,events,name,*,after=None,before=None,fail=False):
        self.events,self.name=events,name
        self.after,self.before,self.fail=after,before,fail
        self.started=False
        self.should_exit=False
        self.force_exit=False

    async def serve(self,*,sockets):
        self.events.append(self.name+"-enter")
        if self.fail:
            return
        if self.after:
            await self.after()
        self.started=True
        self.events.append(self.name+"-started")
        while not self.should_exit:
            await asyncio.sleep(.005)
        if self.before:
            await self.before()
        self.events.append(self.name+"-drained")


def test_two_server_order_and_shared_owner_identity(monkeypatch):
    launch=launch_fixture()
    events=[]
    owner,mem=object(),object()
    epoch=SimpleNamespace(_assert_deployment_latch=AsyncMock())
    writer=SimpleNamespace(repository=mem)
    state,registry,_=registry_fixture()
    state._engine_canonical_mongo_owners=(owner,mem,launch.plan.memory_namespace,epoch,launch.plan.policy_sha256)
    state._engine_local_guard_components=object()
    state._engine_shutdown_pending=False

    async def run():
        stop=asyncio.Event()
        supervisor=None
        def new_engine(app,port):
            assert port==launch.plan.engine_port
            async def close():
                state.engine_execution_coordinator=None
            return FakeServer(events,"engine",before=close)
        async def after_binding():
            evidence=await supervisor.after_binding((owner,mem,writer,epoch))
            assert evidence["inference_qualified"] is False
        async def before_close():
            events.append("backend-work-drained")
            await supervisor.before_database_close()
            events.append("shared-mongo-close")
        backend=s._ServerLane(FakeServer(events,"backend",after=after_binding,before=before_close),object())
        supervisor=s.CohostedStackSupervisor(launch,object(),object(),lambda **kwargs:object(),
            lambda:state,backend,object(),stop,engine_server_factory=new_engine)
        task=asyncio.create_task(supervisor.supervise())
        for i in range(200):
            if backend.server.started:
                break
            await asyncio.sleep(.01)
        assert backend.server.started
        stop.set()
        await asyncio.wait_for(task,3)
        assert supervisor.engine_drained
    asyncio.run(run())
    assert events.index("engine-started")<events.index("backend-started")
    assert events.index("backend-work-drained")<events.index("engine-drained")<events.index("shared-mongo-close")


def test_engine_exit_during_startup_prevents_backend_ready():
    launch=launch_fixture()
    events=[]
    async def run():
        stop=asyncio.Event()
        backend=s._ServerLane(FakeServer(events,"backend"),object())
        supervisor=s.CohostedStackSupervisor(launch,object(),object(),lambda **kw:object(),lambda:None,
            backend,object(),stop,engine_server_factory=lambda app,port:FakeServer(events,"engine",fail=True))
        with pytest.raises(s.ProtectedStackDenied):
            await supervisor.after_binding((object(),object(),object(),object()))
        assert not supervisor.composed
        assert not backend.server.started
        await supervisor.engine_lane.drain(1)
    asyncio.run(run())


def test_wait_started_denies_interrupted_or_failed_server():
    async def run():
        stop=asyncio.Event()
        lane=s._ServerLane(FakeServer([],"engine",fail=True),object())
        lane.begin()
        with pytest.raises(s.ProtectedStackDenied):
            await lane.wait(timeout=1,stop=stop)
        await lane.drain(1)
        stop.set()
        lane2=s._ServerLane(FakeServer([],"backend"),object())
        lane2.begin()
        with pytest.raises(s.ProtectedStackDenied):
            await lane2.wait(timeout=1,stop=stop)
        await lane2.drain(1)
    asyncio.run(run())
