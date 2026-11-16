"""Explicit co-hosted protected application composition.

Uses the real backend global canonical writers and the existing engine factory
on one event loop, not two independent Mongo owners or a synthetic provider.
The external reviewer and real model assets remain operator-owned. Deployment
authorization is an independently signed plan bound to the signed writer
cutover. There are no HTTP/env switches creating trust.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import time
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.runtime.inference.native_guard_binding import NativeGuardPins
from skeleton.ai.runtime.inference.reviewer_custody import ReviewerTrustAnchor, ReviewerCustodyVerifier
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient
from skeleton.app.canonical_writer_cutover import VerifiedWriterCutover
from skeleton.app.reviewer_client_configuration import PinnedReviewerTLS, create_pinned_reviewer_client
from skeleton.app.trusted_native_startup import TrustedNativeStartup

_DOMAIN=b"skeleton.protected-cohost-launch.v1\0"
_SHA=re.compile(r"[0-9a-f]{40}\Z",re.ASCII)
_HEX=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)
_ID=re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z",re.ASCII)
_SCOPE_LIMIT=512
_MAX_PLAN=64*1024
_MAX_PINS=16


class ProtectedStackDenied(RuntimeError):
    pass


def require(condition,code="protected stack admission denied"):
    if condition is not True:
        raise ProtectedStackDenied(code)


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _pin(value):
    return type(value) is str and _HEX.fullmatch(value) is not None and value!="0"*64


def _id(value):
    return type(value) is str and _ID.fullmatch(value) is not None


def _scope(value):
    try:
        return (type(value) is str and bool(value) and value==value.strip()
                and len(value.encode("utf-8","strict"))<=_SCOPE_LIMIT
                and all(ord(c)>=32 and ord(c)!=127 for c in value))
    except UnicodeError:
        return False


def _unique(pairs):
    row={}
    for k,v in pairs:
        require(k not in row,"duplicate launch plan field")
        row[k]=v
    return row


def _constant(_):
    raise ProtectedStackDenied("nonfinite launch plan")


@dataclass(frozen=True,slots=True)
class ProtectedStackLaunchPlan:
    authority_id: str
    deployment_id: str
    source_head: str
    writer_plan_sha256: str
    issued_at: int
    expires_at: int
    backend_port: int
    engine_port: int
    reviewer_endpoint: str
    reviewer_authority: str
    reviewer_domain: str
    reviewer_public_key_hex: str
    reviewer_ca_sha256: str
    reviewer_client_cert_sha256: str
    policy_sha256: str
    memory_namespace: str
    probe_tenant_id: str
    probe_actor_id: str
    probe_context_id: str
    active_model_id: str
    models: tuple[NativeGuardPins,...]

    def __post_init__(self):
        require(_id(self.authority_id) and _id(self.deployment_id)
                and type(self.source_head) is str and _SHA.fullmatch(self.source_head) is not None)
        require(all(_pin(v) for v in (self.writer_plan_sha256,self.reviewer_public_key_hex,
                    self.reviewer_ca_sha256,self.reviewer_client_cert_sha256,self.policy_sha256)))
        require(type(self.issued_at) is int and type(self.expires_at) is int
                and 0<self.issued_at<self.expires_at<(1<<63) and self.expires_at-self.issued_at<=600)
        require(type(self.backend_port) is int and type(self.engine_port) is int
                and 1024<=self.backend_port<=65535 and 1024<=self.engine_port<=65535
                and self.backend_port!=self.engine_port)
        require(_id(self.reviewer_authority) and _id(self.reviewer_domain)
                and len({self.reviewer_authority,self.reviewer_domain,self.authority_id,self.deployment_id})==4)
        require(type(self.reviewer_endpoint) is str and 1<=len(self.reviewer_endpoint)<=2048
                and all(33<=ord(c)<=126 for c in self.reviewer_endpoint))
        try:
            endpoint=urlsplit(self.reviewer_endpoint)
            require(endpoint.scheme=="https" and bool(endpoint.hostname)
                    and endpoint.username is None and endpoint.password is None
                    and endpoint.path in ("","/") and not endpoint.query and not endpoint.fragment
                    and "\\" not in endpoint.netloc and "%" not in endpoint.netloc
                    and (endpoint.port is None or 1<=endpoint.port<=65535),
                    "independent HTTPS reviewer endpoint required")
        except ValueError:
            raise ProtectedStackDenied("invalid reviewer endpoint") from None
        require(type(self.memory_namespace) is str and 1<=len(self.memory_namespace)<=128
                and all(c.isascii() and (c.isalnum() or c in "_.-") for c in self.memory_namespace))
        require(all(_scope(v) for v in (self.probe_tenant_id,self.probe_actor_id,self.probe_context_id)))
        require(type(self.models) is tuple and 1<=len(self.models)<=_MAX_PINS
                and all(type(model) is NativeGuardPins and all(_pin(d) for d in
                     (model.model_digest,model.runtime_digest,model.tokenizer_digest)) for model in self.models))
        identities=tuple(model.model_id for model in self.models)
        require(tuple(sorted(set(identities)))==identities
                and type(self.active_model_id) is str and self.active_model_id in identities)

    def document(self):
        result={f.name:getattr(self,f.name) for f in fields(self)}
        result["models"]=[{f.name:getattr(model,f.name) for f in fields(model)} for model in self.models]
        return result

    def canonical_bytes(self):
        raw=_DOMAIN+_canonical(self.document())
        require(len(raw)<=_MAX_PLAN)
        return raw

    @classmethod
    def parse(cls,raw):
        require(type(raw) is bytes and 0<len(raw)<=_MAX_PLAN)
        try:
            doc=json.loads(raw.decode("utf-8","strict"),object_pairs_hook=_unique,parse_constant=_constant)
            require(type(doc) is dict and set(doc)=={f.name for f in fields(cls)}
                    and type(doc["models"]) is list and 1<=len(doc["models"])<=_MAX_PINS)
            require(all(type(item) is dict and set(item)=={f.name for f in fields(NativeGuardPins)}
                        for item in doc["models"]))
            doc["models"]=tuple(NativeGuardPins(**item) for item in doc["models"])
            return cls(**doc)
        except ProtectedStackDenied:
            raise
        except Exception:
            raise ProtectedStackDenied("invalid protected launch document") from None


@dataclass(frozen=True,slots=True)
class VerifiedProtectedStackLaunch:
    plan: ProtectedStackLaunchPlan
    writer_approval: VerifiedWriterCutover
    signature: bytes
    public_key: bytes

    def __post_init__(self):
        self.verify()

    def verify(self):
        p,w=self.plan,self.writer_approval
        require(type(p) is ProtectedStackLaunchPlan and type(w) is VerifiedWriterCutover
                and p.authority_id==w.authority_id and p.deployment_id==w.deployment_id
                and p.source_head==w.source_head
                and p.writer_plan_sha256==hashlib.sha256(w.plan.canonical_bytes()).hexdigest()
                and type(self.public_key) is bytes and len(self.public_key)==32
                and self.public_key==w.public_key
                and bytes.fromhex(p.reviewer_public_key_hex)!=self.public_key
                and p.issued_at<=int(time.time())<p.expires_at
                and type(self.signature) is bytes and len(self.signature)==64)
        w.verify()
        try:
            Ed25519PublicKey.from_public_bytes(self.public_key).verify(self.signature,p.canonical_bytes())
        except (InvalidSignature,TypeError,ValueError):
            raise ProtectedStackDenied("protected launch signature rejected") from None


def assert_local_configuration(launch,environ):
    """Observe explicit local-only config before imports or writer reservation.

    Do not rewrite .env, choose model assets or synthesize credentials. The
    actual engine registry will independently bind the loaded model pins.
    """
    require(type(launch) is VerifiedProtectedStackLaunch)
    launch.verify()
    plan=launch.plan
    require(environ.get("AI_PROVIDER")=="local" and
            environ.get("SKELETON_INTERNAL_URL")==f"http://127.0.0.1:{plan.engine_port}",
            "explicit same-process loopback engine and local provider required")
    token=environ.get("SKL_ENGINE_SERVICE_TOKEN")
    require(type(token) is str and 32<=len(token)<=4096 and
            token.isascii() and all(33<=ord(c)<=126 for c in token),
            "existing authenticated engine service channel required")
    model_paths=("AI_LOCAL_MODEL_PATH","AI_LOCAL_DEPLOYMENT_PATH","AI_LOCAL_MODEL_CATALOG_PATH")
    require(sum(bool(environ.get(name,"").strip()) for name in model_paths)==1,
            "exactly one operator-selected local model source required")
    require(not any(environ.get(name,"").strip() for name in
                    ("AI_SECONDARY_API_KEY","AI_SECONDARY_BASE_URL","AI_SECONDARY_MODEL","AI_VERIFICATION_MODEL")),
            "external provider fallback or verifier not admitted")


def create_launch_reviewer(launch,*,ca_path,client_cert_path,client_key_path):
    launch.verify()
    p=launch.plan
    anchor=ReviewerTrustAnchor(p.reviewer_authority,p.reviewer_domain,bytes.fromhex(p.reviewer_public_key_hex))
    tls=PinnedReviewerTLS(ca_path,p.reviewer_ca_sha256,client_cert_path,
                         p.reviewer_client_cert_sha256,client_key_path)
    return create_pinned_reviewer_client(endpoint=p.reviewer_endpoint,anchor=anchor,tls=tls)


def _reviewer_matches(launch,reviewer):
    p=launch.plan
    anchor=ReviewerTrustAnchor(p.reviewer_authority,p.reviewer_domain,bytes.fromhex(p.reviewer_public_key_hex))
    require(type(reviewer) is SignedReviewerClient and getattr(reviewer,"_closed",True) is False
            and getattr(reviewer,"_anchor",None)==anchor
            and getattr(reviewer,"_base_url",None)==p.reviewer_endpoint.rstrip("/"),
            "exact independent reviewer client not installed")
    return anchor


async def _attest_startup(launch,reviewer,epoch):
    """Actual scoped independent signer challenge, never semantic inference."""
    launch.verify()
    anchor=_reviewer_matches(launch,reviewer)
    p=launch.plan
    scope={"tenant_id":p.probe_tenant_id,"actor_id":p.probe_actor_id,"context_id":p.probe_context_id}
    before=await epoch.read_epoch(**scope)
    verifier=ReviewerCustodyVerifier(reviewer=reviewer,authority_id=anchor.authority_id,
                                   trust_anchor=anchor)
    for pin in p.models:
        launch.verify()
        await verifier.verify(**scope,epoch=before,model_digest=pin.model_digest,
                              runtime_digest=pin.runtime_digest,tokenizer_digest=pin.tokenizer_digest)
    require(await epoch.read_epoch(**scope)==before,"canonical source changed during reviewer challenge")
    launch.verify()


def verify_loaded_registry(launch,state):
    """Require all and only the independently pinned local model routes."""
    launch.verify()
    coordinator=getattr(state,"engine_execution_coordinator",None)
    registry=getattr(coordinator,"provider_registry",None)
    require(registry is not None and registry.active_id=="local" and registry.available is True
            and getattr(registry,"_fallback_ids",None)==(),
            "guarded native registry unavailable")
    statuses=registry.statuses()
    p=launch.plan
    require(type(statuses) is list and len(statuses)==len(p.models)
            and all(type(row) is dict and row.get("id")=="local" and type(row.get("model")) is str
                    and row.get("available") is True for row in statuses),
            "exact local model inventory unavailable")
    require({row["model"] for row in statuses}=={pin.model_id for pin in p.models}
            and getattr(registry.active,"model",None)==p.active_model_id,
            "configured model inventory differs from approved plan")
    for pin in p.models:
        adapter=registry.require_selected("local",pin.model_id)
        require(getattr(adapter,"require_guarded_inference",None) is True
                and getattr(adapter,"guarded_service",None) is not None
                and adapter.available is True,
                "loaded model lacks actual guarded adapter")
    return registry


@contextmanager
def _listener(port):
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        # Do not use SO_REUSEPORT, wildcard hosts or accidental extra listeners.
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind(("127.0.0.1",port))
        sock.listen(128)
        sock.setblocking(False)
        require(sock.getsockname()==("127.0.0.1",port),"protected listener identity mismatch")
        yield sock
    finally:
        sock.close()


def _new_server(app,port):
    import uvicorn
    class OwnedServer(uvicorn.Server):
        # Exactly one owner installs process signal handling; ASGI servers
        # cannot overwrite each other's handlers.
        @contextmanager
        def capture_signals(self):
            yield

        def install_signal_handlers(self):
            return None
    return OwnedServer(uvicorn.Config(app,host="127.0.0.1",port=port,workers=1,
                         reload=False,lifespan="on",access_log=False,
                         log_level="warning",timeout_graceful_shutdown=30))


async def _serve(server,sock):
    try:
        await server.serve(sockets=[sock])
    except SystemExit:
        raise ProtectedStackDenied("protected service failed to start") from None


async def _wait_started(server,task,*,timeout,stop):
    deadline=time.monotonic()+timeout
    while True:
        require(not stop.is_set(),"protected stack startup interrupted")
        if task.done():
            try:
                task.result()
            except Exception:
                raise ProtectedStackDenied("protected service startup failed") from None
            raise ProtectedStackDenied("protected service exited before startup")
        if server.started is True:
            require(not server.should_exit,"protected service startup exited")
            return
        require(time.monotonic()<deadline,"protected service startup deadline exceeded")
        await asyncio.sleep(.05)


@dataclass(slots=True)
class _ServerLane:
    server: object
    sock: object
    task: asyncio.Task | None=None

    def begin(self):
        require(self.task is None,"protected service cannot restart in same process")
        self.task=asyncio.create_task(_serve(self.server,self.sock))

    async def wait(self,*,timeout,stop):
        require(self.task is not None)
        await _wait_started(self.server,self.task,timeout=timeout,stop=stop)

    async def drain(self,timeout):
        if self.task is None:
            return
        self.server.should_exit=True
        try:
            await asyncio.wait_for(asyncio.shield(self.task),timeout=timeout)
            self.task.result()
        except TimeoutError:
            # Never report clean shutdown or release reservation on timeout.
            self.server.force_exit=True
            self.task.cancel()
            raise ProtectedStackDenied("protected service drain uncertain") from None
        except Exception:
            raise ProtectedStackDenied("protected service drain failed") from None


class CohostedStackSupervisor:
    """Backend binding starts the real guarded engine; backend drains first.

    The callback is installed directly in the existing backend startup path.
    It cannot be created by a public request. The engine must bind the same
    exact owners and demonstrate loaded guarded registry availability before
    the backend proceeds through its ordinary lifespan.
    """
    def __init__(self,launch,reviewer,backend_app,engine_factory,engine_state,
                 backend_lane,engine_socket,stop,*,engine_server_factory=_new_server):
        require(type(launch) is VerifiedProtectedStackLaunch)
        self.launch=launch
        self.reviewer=reviewer
        self.backend_app=backend_app
        self.engine_factory=engine_factory
        self.engine_state=engine_state
        self.backend_lane=backend_lane
        self.engine_socket=engine_socket
        self.stop=stop
        self.engine_server_factory=engine_server_factory
        self.engine_lane=None
        self.runtime=None
        self.engine_drained=False
        self.composed=False

    async def _bootstrap(self,state):
        require(self.runtime is not None and self.composed is False)
        conversation,memory,writer,epoch=self.runtime
        require(writer.repository is memory)
        await _attest_startup(self.launch,self.reviewer,epoch)
        p=self.launch.plan
        startup=TrustedNativeStartup(conversation,memory,epoch,self.reviewer,p.models,
                                     p.policy_sha256,p.memory_namespace)
        await startup(state)

    async def after_binding(self,runtime):
        self.launch.verify()
        require(self.runtime is None and self.engine_lane is None and type(runtime) is tuple
                and len(runtime)==4 and not self.stop.is_set(),
                "protected engine composition already started or interrupted")
        self.runtime=runtime
        app=self.engine_factory(trusted_protected_bootstrap=self._bootstrap)
        self.engine_lane=_ServerLane(self.engine_server_factory(app,self.launch.plan.engine_port),
                                     self.engine_socket)
        self.engine_lane.begin()
        await self.engine_lane.wait(timeout=180,stop=self.stop)
        state=self.engine_state()
        registry=verify_loaded_registry(self.launch,state)
        conversation,memory,_,epoch=runtime
        owners=getattr(state,"_engine_canonical_mongo_owners",None)
        require(type(owners) is tuple and len(owners)==5
                and owners[0] is conversation and owners[1] is memory and owners[3] is epoch
                and owners[2]==self.launch.plan.memory_namespace
                and owners[4]==self.launch.plan.policy_sha256)
        require(getattr(state,"_engine_local_guard_components",None) is not None
                and getattr(state.engine_execution_coordinator,"provider_registry",None) is registry)
        await epoch._assert_deployment_latch()
        self.launch.verify()
        self.composed=True
        # This is an observation receipt, not generation, device or release proof.
        return {"shared_canonical_owners_observed":True,"scoped_reviewer_challenge_observed":True,
                "guarded_registry_available_observed":True,"inference_qualified":False,
                "external_writer_coverage_verified":False,"device_qualified":False,
                "release_qualified":False}

    async def before_database_close(self):
        # Called only after backend stops admitting traffic and drains its own
        # background work. The real engine may still need the shared backend
        # Mongo transport to finalize durable execution.
        require(self.engine_lane is not None and self.composed)
        await self.engine_lane.drain(60)
        state=self.engine_state()
        require(getattr(state,"engine_execution_coordinator",None) is None
                and not getattr(state,"_engine_shutdown_pending",True),
                "engine custody not drained")
        self.engine_drained=True

    async def supervise(self):
        self.backend_lane.begin()
        normal=False
        try:
            await self.backend_lane.wait(timeout=300,stop=self.stop)
            require(self.composed and self.engine_lane is not None,
                    "backend started without guarded composition")
            stop_task=asyncio.create_task(self.stop.wait())
            try:
                done,_=await asyncio.wait((stop_task,self.backend_lane.task,self.engine_lane.task),
                                          return_when=asyncio.FIRST_COMPLETED)
                normal=stop_task in done and self.stop.is_set() and self.backend_lane.task not in done \
                       and self.engine_lane.task not in done
            finally:
                stop_task.cancel()
                await asyncio.gather(stop_task,return_exceptions=True)
            require(normal,"protected stack member exited unexpectedly")
        finally:
            # Backend shutdown hook drains engine before closing shared DB.
            # If that hook never ran, attempt engine drain, but still fail.
            try:
                await self.backend_lane.drain(90)
            finally:
                if self.engine_lane is not None and not self.engine_drained:
                    await self.engine_lane.drain(60)
        require(normal and self.engine_drained,"protected stack shutdown not qualified")


async def run_cohosted_stack(launch,reviewer,*,backend_app,engine_factory,engine_state,checkpoint):
    """Single event-loop, two loopback origins, same actual canonical owners."""
    require(os.name=="posix","co-hosted protected stack requires POSIX signal supervision")
    launch.verify()
    _reviewer_matches(launch,reviewer)
    from core.canonical_writer_startup import configure_cutover
    p=launch.plan
    loop=asyncio.get_running_loop()
    stop=asyncio.Event()
    installed=[]
    try:
        with _listener(p.backend_port) as backend_sock,_listener(p.engine_port) as engine_sock:
            backend_lane=_ServerLane(_new_server(backend_app,p.backend_port),backend_sock)
            supervisor=CohostedStackSupervisor(launch,reviewer,backend_app,engine_factory,
                        engine_state,backend_lane,engine_sock,stop)
            for sig in (signal.SIGINT,signal.SIGTERM):
                loop.add_signal_handler(sig,stop.set)
                installed.append(sig)
            configure_cutover(backend_app,launch.writer_approval,local_checkpoint=checkpoint,
                             after_binding=supervisor.after_binding,
                             before_database_close=supervisor.before_database_close)
            await supervisor.supervise()
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)
