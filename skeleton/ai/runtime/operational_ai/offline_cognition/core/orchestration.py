"""Bounded, source and scope-bound plans. Deliberately no tool or model executor.

Every submitted plan is inert until an independent canonical operator/native
owner admits it. Crash-ambiguous effects are fenced, never automatically retried.
"""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import (
    Scope, CognitionError, identifier, sha, integer, exact, fingerprint,
    hash_bytes, refuse,
)
from .planner import PlanTask, compile_plan, plan_digest
from .tool_intents import ToolIntent, propose, inspect
from .admission import Permit, admit
from .sources import Source

MAX_PLAN_STEPS = 256
MAX_TOOL_BYTES = 131072
OUTCOMES = frozenset((
    "pre-dispatch-refusal", "operator-denial", "capacity-refusal",
    "deadline-expired", "native-effect-unknown", "spine-committed",
    "source-mismatch", "local-transient-error",
))

def guarded_plan(scope, tasks, *, request_id, source_sha256,
                 now_ns, deadline_ns, token_limit, duration_limit_ms):
    """Compile typed DAG with one exact identity and finite token/wall budget."""
    if type(scope) is not Scope:
        refuse("exact scope required")
    identifier(request_id);sha(source_sha256)
    integer(now_ns);integer(deadline_ns,minimum=now_ns+1)
    integer(token_limit,minimum=1,maximum=262144)
    integer(duration_limit_ms,minimum=1,maximum=3600000)
    if type(tasks) not in (tuple,list) or not 1<=len(tasks)<=MAX_PLAN_STEPS:
        refuse("finite task list required")
    checked=compile_plan(tasks,max_tasks=MAX_PLAN_STEPS,max_tokens=token_limit)
    if checked["critical_path_ms"]>duration_limit_ms:
        refuse("critical-path time budget exceeded")
    if (deadline_ns-now_ns)<checked["critical_path_ms"]*1000000:
        refuse("requested deadline cannot contain critical path")
    claim={"schema":"offline-guarded-plan.v1",
           "scope_sha256":scope.digest(),"request_id":request_id,
           "source_sha256":source_sha256,"plan_sha256":checked["sha256"],
           "deadline_ns":deadline_ns,"token_limit":token_limit,
           "duration_limit_ms":duration_limit_ms}
    return {**checked,"plan_claim":claim,"claim_sha256":fingerprint(claim),
            "native_effect_performed":False,"approved_to_execute":False}

def plan_ready(plan, scope, *, request_id, source_sha256, now_ns):
    """Read-only validation never converts a plan into execution permission."""
    if type(plan) is not dict or type(scope) is not Scope:
        refuse("typed plan and scope required")
    expected={"schema","scope_sha256","request_id","source_sha256","plan_sha256",
              "deadline_ns","token_limit","duration_limit_ms"}
    claim=exact(plan.get("plan_claim"),expected)
    if claim["schema"]!="offline-guarded-plan.v1":
        refuse("unknown plan schema")
    if claim["scope_sha256"]!=scope.digest() or claim["request_id"]!=request_id:
        refuse("plan principal/request identity mismatch")
    if claim["source_sha256"]!=sha(source_sha256):
        refuse("plan source revision mismatch")
    if plan.get("claim_sha256")!=fingerprint(claim):
        refuse("plan claim modified")
    if plan.get("sha256")!=claim["plan_sha256"]:
        refuse("compiled task DAG changed")
    record_fields=("order","edges","tokens","critical_path_ms","critical_path",
                   "source_plan_not_authority_to_execute")
    if any(field not in plan for field in record_fields):
        refuse("incomplete canonical plan projection")
    record={field:plan[field] for field in record_fields}
    if record["source_plan_not_authority_to_execute"] is not True:
        refuse("source plan falsely claims execution authority")
    if plan_digest(record)!=plan["sha256"]:
        refuse("task graph projection changed after compile")
    integer(now_ns)
    if now_ns>=claim["deadline_ns"]:
        refuse("expired plan")
    return {"plan_sha256":claim["plan_sha256"],"scope_sha256":scope.digest(),
            "expires_ns":claim["deadline_ns"],"operator_approval_required":True,
            "tool_or_native_execution_authorized":False}

def propose_read(scope, *, request_id, source_id, expires_ns, limit=10,
                 tool="read_source"):
    if type(scope) is not Scope:
        refuse("tool proposal requires exact model scope")
    identifier(source_id)
    integer(limit,minimum=1,maximum=100)
    return propose(scope,request_id=identifier(request_id),tool=tool,
                   arguments={"source_id":source_id,"limit":limit},
                   expires_ns=expires_ns)

@dataclass(frozen=True, slots=True)
class ReadResult:
    """Original operator-approved bytes bind one inert read-only tool proposal."""
    intent: ToolIntent
    source: Source
    scope: Scope
    request_id: str
    payload: bytes
    retrieved_ns: int
    limit: int = 10

    def __post_init__(self):
        if type(self.intent) is not ToolIntent or type(self.source) is not Source:
            refuse("typed read intent/source required")
        if type(self.scope) is not Scope or not self.source.approved:
            refuse("operator-approved source and scope required")
        if type(self.payload) is not bytes or not 1<=len(self.payload)<=MAX_TOOL_BYTES:
            refuse("finite source payload required")
        identifier(self.request_id);integer(self.retrieved_ns)
        integer(self.limit,minimum=1,maximum=100)
        if self.intent.args_sha256!=fingerprint({"source_id":self.source.source_id,
                                                  "limit":self.limit}):
            refuse("tool reply has a different original proposal argument digest")
        if self.intent.request_id!=self.request_id or (
            self.intent.scope_sha256!=self.scope.digest()
        ):
            refuse("tool reply not bound to source request and principal")
        if (self.source.tenant,self.source.subject)!=(self.scope.tenant,self.scope.subject):
            refuse("foreign scope tool output")
        if self.intent.tool not in ("read_source","inspect_receipt"):
            refuse("tool output is not an authorized read response")
        if self.retrieved_ns>=self.intent.expires_ns:
            refuse("tool output arrived after expiry")
        if self.source.bytes_length!=len(self.payload) or (
            self.source.sha256!=hash_bytes(self.payload)
        ):
            refuse("tool result does not match independent original receipt")

    def receipt(self):
        body={"schema":"offline-read-evidence.v1",
              "intent_id":self.intent.intent_id,
              "scope_sha256":self.scope.digest(),
              "request_id":self.request_id,
              "source_id":self.source.source_id,
              "source_sha256":self.source.sha256,
              "byte_count":len(self.payload),
              "result_limit":self.limit,
              "retrieved_ns":self.retrieved_ns}
        return {**body,"receipt_sha256":fingerprint(body),
                "original_bytes_verified":True,
                "semantic_entailment_proved":False,
                "tool_grant_issued_by_this_module":False}

def verify_operator_input(permit, scope, operation, *,
                          source_sha256, now_ns):
    """Delegates exact grant to existing permit owner; grants no new privilege."""
    receipt=admit(permit,scope,operation,now_ns=now_ns,
                  required_source_sha256=source_sha256)
    return {"permit_receipt":receipt,"scope_sha256":scope.digest(),
            "additional_execution_authority":False}

def classify_outcome(outcome, *, dispatch_marker, authoritative_commit):
    """Never conflate a crash or transport error with a safe native retry."""
    if type(outcome) is not str or outcome not in OUTCOMES:
        refuse("unknown native transition outcome")
    if type(dispatch_marker) is not bool or type(authoritative_commit) is not bool:
        refuse("explicit actual dispatch and durable commit bits required")
    if authoritative_commit and outcome!="spine-committed":
        refuse("durable commit conflicts with reported outcome")
    if outcome=="spine-committed" and not authoritative_commit:
        refuse("reported commit has no canonical source proof")
    if outcome=="native-effect-unknown" and not dispatch_marker:
        refuse("unproven native dispatch marker")
    if authoritative_commit:
        state="committed-read-only-replay"
    elif dispatch_marker:
        state="native-effect-unknown-held"
    elif outcome in ("operator-denial","source-mismatch","deadline-expired"):
        state="terminal-policy-hold"
    else:
        state="pre-dispatch-held"
    return {"outcome":outcome,"state":state,
            "automatic_retry_allowed":False,
            "reconciliation_requires_canonical_spine":dispatch_marker and not authoritative_commit,
            "operator_reapproval_required":state=="pre-dispatch-held",
            "committed_replay_only":authoritative_commit}

def escalation(scope, *, request_id, source_sha256, cause, created_ns):
    """Create digest-only operator review intent; never dispatch or elevate."""
    if type(scope) is not Scope:refuse("scoped escalation required")
    identifier(request_id);sha(source_sha256);integer(created_ns)
    if cause not in OUTCOMES:
        refuse("noncanonical escalation reason")
    claim={"schema":"offline-escalation-intent.v1",
           "scope_sha256":scope.digest(),"request_id":request_id,
           "source_sha256":source_sha256,"reason":cause,"created_ns":created_ns}
    return {**claim,"intent_sha256":fingerprint(claim),
            "operator_notified":False,"privilege_granted":False,
            "native_retrial_triggered":False}

@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    scope_sha256: str
    revision: int
    failures: int
    last_seen_ns: int
    held: bool
    def __post_init__(self):
        sha(self.scope_sha256)
        integer(self.revision,minimum=1)
        integer(self.failures,maximum=1000000)
        integer(self.last_seen_ns)
        if type(self.held) is not bool:
            refuse("explicit circuit hold required")

def observe_circuit(old, scope, *, failure, now_ns, threshold=3):
    """Pure CAS candidate; external canonical state owner must publish it."""
    if type(old) is not CircuitSnapshot or type(scope) is not Scope:
        refuse("revision-bound circuit input required")
    if old.scope_sha256!=scope.digest():
        refuse("cross-model or cross-principal circuit")
    if type(failure) is not bool:
        refuse("explicit failure observation required")
    integer(now_ns,minimum=old.last_seen_ns+1)
    integer(threshold,minimum=1,maximum=100)
    count=min(1000000,old.failures+1) if failure else 0
    held=old.held or count>=threshold
    return CircuitSnapshot(scope.digest(),old.revision+1,count,now_ns,held)

def request_circuit_recovery(old,scope,*,expected_revision,operator_approved):
    """An approval declaration is never interpreted as a verified signed grant."""
    if type(old) is not CircuitSnapshot or type(scope) is not Scope:
        refuse("typed scoped circuit required")
    integer(expected_revision,minimum=1)
    if old.revision!=expected_revision or old.scope_sha256!=scope.digest():
        refuse("stale or foreign circuit revision")
    if type(operator_approved) is not bool or not operator_approved:
        refuse("explicit operator recovery request required")
    return {"scope_sha256":old.scope_sha256,"revision":old.revision,
            "state":"recovery-requested-held",
            "operator_signature_verified":False,
            "execution_enabled":False,"automatic_reopen":False}
