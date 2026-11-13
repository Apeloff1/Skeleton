"""task_decompose: evidence-bound, non-executing workflow facade."""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
from skeleton.ai.runtime.operational_ai.offline_cognition.core.orchestration import (
    guarded_plan,plan_ready,propose_read,ReadResult,classify_outcome,
    escalation,CircuitSnapshot,observe_circuit,request_circuit_recovery,
)

def compile(scope,tasks,*,request_id,source_sha256,now_ns,deadline_ns,
            token_limit=8192,duration_limit_ms=30000):
    if token_limit>PROFILE.context_limit:refuse("plan exceeds family token budget")
    if duration_limit_ms>PROFILE.latency_ms:refuse("plan exceeds family duration budget")
    return guarded_plan(scope,tasks,request_id=request_id,
            source_sha256=source_sha256,now_ns=now_ns,deadline_ns=deadline_ns,
            token_limit=token_limit,duration_limit_ms=duration_limit_ms)

def inspect(plan,scope,*,request_id,source_sha256,now_ns):
    return plan_ready(plan,scope,request_id=request_id,
                      source_sha256=source_sha256,now_ns=now_ns)

def read_only_proposal(scope,*,request_id,source_id,expires_ns,limit=10):
    return propose_read(scope,request_id=request_id,source_id=source_id,
                        expires_ns=expires_ns,limit=limit)

def original_read_receipt(intent,source,scope,*,request_id,payload,retrieved_ns):
    return ReadResult(intent,source,scope,request_id,payload,retrieved_ns).receipt()

def outcome(status,*,dispatch_marker,authoritative_commit):
    return classify_outcome(status,dispatch_marker=dispatch_marker,
                            authoritative_commit=authoritative_commit)

def ask_operator(scope,*,request_id,source_sha256,cause,created_ns):
    return escalation(scope,request_id=request_id,source_sha256=source_sha256,
                      cause=cause,created_ns=created_ns)

def observe(old,scope,*,failure,now_ns):
    return observe_circuit(old,scope,failure=failure,now_ns=now_ns)

def recovery_request(old,scope,*,expected_revision,operator_approved):
    return request_circuit_recovery(old,scope,
            expected_revision=expected_revision,operator_approved=operator_approved)

def contract():
    return {"family":PROFILE.name,"task_admission_ceiling":256,
            "token_limit":PROFILE.context_limit,"duration_limit_ms":PROFILE.latency_ms,
            "external_operator_grant_verified":False,"native_execution_performed":False}
