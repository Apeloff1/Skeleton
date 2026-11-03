"""Live durable-job acceptance oracle, exercising SQLite transactions.

All cases execute real store methods. Native-model execution is deliberately
excluded: physical checkpoint/tokenizer and model quality require independent
device qualification; no fake generation is substituted in production.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import sqlite3
from typing import Any

from .admission import AdmissionPolicy, Telemetry
from .audit import verify_audit
from .bridge import NativeJobBridge
from .canonical import sha256
from .errors import JobDenied
from .observer import metrics
from .pagination import CursorCodec
from .recovery import inspect_hold
from .result import JobResult
from .result_caps import assess
from .spec import JobIdentity,JobSpec,WorkLimits,require_id
from .store import JobStore
from .dependency import status as dependency_status

SHA_A="a"*64
SHA_B="b"*64
SHA_C="c"*64
OWNER=JobIdentity("tenant","user","session",SHA_A,SHA_B)


def make_store(limits:WorkLimits|None=None)->JobStore:
    db=sqlite3.connect(":memory:", isolation_level=None)
    return JobStore(db,limits=limits)


def make_spec(name:str="job_1",*,owner:JobIdentity=OWNER,
              request_id:str|None=None,question:str="Explain this text.",
              created_ms:int=1000,expires_ms:int=10000,
              priority:int=0,dependencies:tuple=())->JobSpec:
    return JobSpec(name,request_id or name,owner,question,
                   created_ms,expires_ms,priority,dependencies)


def make_result(spec:JobSpec,*,text:str="Real service fixture receipt.",
                output_sha:str|None=None,model_sha:str|None=None,
                tokenizer_sha:str|None=None,request_id:str|None=None,
                output_tokens:int=8)->JobResult:
    return JobResult(text,output_sha or sha256(text.encode("utf-8")),
                     model_sha or spec.owner.model_sha256,
                     tokenizer_sha or spec.owner.tokenizer_sha256,
                     11,output_tokens,request_id or spec.request_id)


def _do(domain:str,p:dict[str,Any])->dict:
    variant=p["variant"]
    if domain=="identity":
        require_id(variant)
        return {"state":"valid"}

    if domain=="work_limits":
        WorkLimits(**p["limits"])
        return {"state":"valid"}

    if domain=="job_contract":
        JobSpec(
            p["job_id"],p["request_id"],OWNER,p["question"],
            p["created_ms"],p["expires_ms"],p["priority"],
            tuple(p["dependencies"]),
        )
        return {"state":"valid"}

    if domain=="model_binding":
        owner=JobIdentity(p["tenant"],p["user"],p["session"],p["model_sha"],p["tokenizer_sha"])
        spec=make_spec(owner=owner)
        db=make_store()
        db.submit(spec,now_ms=1000)
        view=db.inspect(spec.job_id,OWNER)
        return {"state":view["state"]}

    if domain=="submission":
        store=make_store()
        spec=make_spec(
            name=p["job_id"],request_id=p["request_id"],
            question=p["question"],created_ms=p["created_ms"],expires_ms=p["expires_ms"],
        )
        return {"state":store.submit(spec,now_ms=p["now_ms"])}

    if domain=="dedup":
        store=make_store()
        first=make_spec(name="job_1")
        store.submit(first,now_ms=1000)
        next_spec=make_spec(
            name=p["job_id"],request_id=p["request_id"],
            question=p["question"],priority=p["priority"],
        )
        return {"state":store.submit(next_spec,now_ms=1000)}

    if domain=="capacity":
        limits=WorkLimits(queue_depth=p["global"],tenant_depth=p["per_tenant"],
                          active_per_tenant=1)
        store=make_store(limits)
        tenants=p["tenants"]
        for i,tenant in enumerate(tenants):
            owner=JobIdentity(tenant,"user","session",SHA_A,SHA_B)
            store.submit(make_spec(name="job_"+str(i),owner=owner),now_ms=1000)
        return {"state":"admitted"}

    if domain=="claim":
        store=make_store()
        store.submit(make_spec(),now_ms=1000)
        claim=store.claim(p["worker"],now_ms=p["now_ms"],lease_ms=p["lease_ms"])
        if claim is None:
            return {"state":"none"}
        return {"state":"claimed"}

    if domain=="heartbeat":
        store=make_store()
        store.submit(make_spec(),now_ms=1000)
        claim=store.claim("worker",now_ms=1000,lease_ms=500)
        until=store.heartbeat(claim,now_ms=p["now_ms"],extend_ms=p["extend_ms"])
        return {"state":"extended" if until>claim.lease_expires_ms else "unchanged"}

    if domain=="completion":
        store=make_store()
        spec=make_spec()
        store.submit(spec,now_ms=1000)
        claim=store.claim("worker",now_ms=1000,lease_ms=5000)
        result=make_result(
            spec, text=p["text"],model_sha=p["model_sha"],
            tokenizer_sha=p["tokenizer_sha"],request_id=p["request_id"],
            output_tokens=p["generated_tokens"],
        )
        result=replace(result,output_sha256=p["output_sha"]) if p["output_sha"] else result
        committed=store.finish(claim,result,now_ms=p["now_ms"])
        if p["repeat"]:
            committed=store.finish(claim,result,now_ms=p["now_ms"])
        return {"state":committed}

    if domain=="result_limits":
        spec=make_spec()
        result=make_result(
            spec, text=p["text"],output_tokens=p["generated_tokens"],
            model_sha=p["model_sha"],tokenizer_sha=p["tokenizer_sha"],
            request_id=p["request_id"],
        )
        limits=WorkLimits(output_tokens=p["token_limit"])
        assess(result,spec,limits)
        return {"state":"valid"}

    if domain=="cancellation":
        store=make_store()
        store.submit(make_spec(),now_ms=1000)
        if p["claimed"]:
            claim=store.claim("worker",now_ms=1000,lease_ms=5000)
        owner=OWNER if p["owner"]=="tenant" else JobIdentity("other","user","session",SHA_A,SHA_B)
        first=store.cancel("job_1",owner,now_ms=p["now_ms"])
        if p["repeat"]:
            first=store.cancel("job_1",owner,now_ms=p["now_ms"])
        return {"state":first}

    if domain=="failure":
        store=make_store()
        store.submit(make_spec(),now_ms=1000)
        claim=store.claim("worker",now_ms=1000,lease_ms=5000)
        state=store.fail(claim,now_ms=p["now_ms"],code=p["code"],ambiguous=p["ambiguous"])
        return {"state":state}

    if domain=="sweep":
        store=make_store()
        spec=make_spec(expires_ms=p["expires_ms"])
        store.submit(spec,now_ms=1000)
        if p["claimed"]:
            store.claim("worker",now_ms=1000,lease_ms=500)
        result=store.sweep(now_ms=p["now_ms"],limit=p["sweep_limit"])
        view=store.inspect("job_1",OWNER)
        return {"state":view["state"],"changed":sum(result.values())}

    if domain=="dependencies":
        if p["parent_state"] not in ("pending","completed","cancelled","failed","held"):
            from .errors import deny
            deny("dependency-unknown-state")
        store=make_store()
        parent=make_spec(name="parent")
        store.submit(parent,now_ms=1000)
        if p["parent_state"]=="completed":
            claim=store.claim("worker",now_ms=1000)
            store.finish(claim,make_result(parent),now_ms=1001)
        elif p["parent_state"]=="cancelled":
            store.cancel("parent",OWNER,now_ms=1001)
        elif p["parent_state"]=="failed":
            claim=store.claim("worker",now_ms=1000)
            store.fail(claim,now_ms=1001,code="fatal",ambiguous=False)
        elif p["parent_state"]=="held":
            claim=store.claim("worker",now_ms=1000)
            store.fail(claim,now_ms=1001,code="uncertain",ambiguous=True)
        child=make_spec(name="child",dependencies=("parent",))
        store.submit(child,now_ms=1001)
        if p["sweep"]:
            store.sweep(now_ms=1002)
        view=dependency_status(store,"child",OWNER)
        return {"state":"ready" if view["ready"] else
                ("blocked" if view["blocked"] else "waiting")}

    if domain=="fairness":
        from .canonical import require_int
        require_int(p["take"],0,1024,"fairness-count")
        if type(p["tenants"]) is not list or type(p["priorities"]) is not list or len(p["tenants"])!=len(p["priorities"]):
            from .errors import deny
            deny("fairness-inventory")
        store=make_store(WorkLimits(active_per_tenant=1))
        names=p["tenants"]
        for i,name in enumerate(names):
            owner=JobIdentity(name,"user","session",SHA_A,SHA_B)
            store.submit(make_spec(name="job_"+str(i),owner=owner,
                       priority=p["priorities"][i]),now_ms=1000)
        got=[]
        for i in range(p["take"]):
            claim=store.claim("worker",now_ms=1000,lease_ms=1000)
            if claim is None:
                break
            got.append(claim.owner.tenant)
        return {"state":",".join(got)}

    if domain=="audit":
        store=make_store()
        from .canonical import require_int
        count=require_int(p["events"],1,32,"audit-events")
        target=require_int(p["target"],1,count,"audit-target")
        for i in range(count):
            store.submit(make_spec(name="job_"+str(i)),now_ms=1000)
        if p["tamper"]=="payload":
            store.db.execute("UPDATE ai_job_audit SET event_json=? WHERE seq=?",(b'{}',target))
        elif p["tamper"]=="head":
            store.db.execute("UPDATE ai_job_state SET audit_sha=?",("f"*64,))
        elif p["tamper"]=="chain":
            store.db.execute("UPDATE ai_job_audit SET previous_sha=? WHERE seq=?",("f"*64,target))
        verified=verify_audit(store.db)
        return {"state":"verified" if verified["verified"] else "failed"}

    if domain=="recovery":
        store=make_store()
        store.submit(make_spec(),now_ms=1000)
        claim=store.claim("worker",now_ms=1000,lease_ms=500)
        store.fail(claim,now_ms=1100,code="ambiguous",ambiguous=True)
        if p["inspect"]:
            inspect_hold(store,"job_1",OWNER,now_ms=p["now_ms"])
        if p["resume"]:
            store.manual_resume(
              "job_1",OWNER,now_ms=p["now_ms"],no_effect_proof_sha256=p["proof_sha"],
              operator_approved=p["operator_approved"],
              proof_verifier=lambda spec,proof: proof==SHA_A and spec.request_id=="job_1",
            )
        return {"state":store.inspect("job_1",OWNER)["state"]}

    if domain=="admission":
        policy=AdmissionPolicy(maximum_pressure=p["threshold"])
        sample=Telemetry(p["memory"],p["cpu"],p["queue"],p["observed_ms"])
        policy.check(make_spec(),WorkLimits(),sample,now_ms=p["now_ms"])
        return {"state":"admitted"}

    if domain=="cursor":
        codec=CursorCodec(b"secret"*8)
        ticket=codec.seal(
          tenant="tenant",last_job_id="job_1",
          issued_ms=p["issued_ms"],expires_ms=p["expires_ms"],
        )
        if p["tamper"]:
            ticket=ticket[:-2]+"xx"
        codec.open(ticket,tenant=p["tenant"],now_ms=p["now_ms"])
        return {"state":"verified"}

    if domain=="observer":
        store=make_store()
        for i in range(p["jobs"]):
            store.submit(make_spec(name="job_"+str(i)),now_ms=1000)
        if p["tamper"]:
            store.db.execute("UPDATE ai_job_state SET audit_sha=?",("f"*64,))
        summary=metrics(store,p["tenant"],top=p["top"])
        return {"state":"verified" if summary["verified"] else "failed"}

    raise AssertionError("unknown live durable-job acceptance domain: "+str(domain))


def evaluate(domain:str,payload:dict)->dict:
    try:
        result=_do(domain,payload)
        return {"allowed":True,**result}
    except JobDenied as exc:
        return {"allowed":False,"code":exc.code}
