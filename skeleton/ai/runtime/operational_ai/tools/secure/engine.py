"""Transaction coordinator: schema then risk policy then durable dedupe then execution.

No model-generated grant can authorize a tool. Non-idempotent writes need an
external transaction adapter and are refused by this safe in-process executor.
"""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
import json,time
from .spec import ToolInvocation,ToolError
from .registry import SecureRegistry
from .policy import ToolPolicy,ToolGrant
from .receipts import ToolExecutionReceipt,output_digest

class SecureToolEngine:
    def __init__(self,registry:SecureRegistry,policy:ToolPolicy,*,max_executions:int=128):
        if type(max_executions) is not int or not 1<=max_executions<=10000:
            raise ToolError('invalid bounded tool limit')
        self.registry=registry;self.policy=policy
        self.max=max_executions;self._count=0;self._receipts={}

    def execute(self,inv:ToolInvocation,grant:ToolGrant)->ToolExecutionReceipt:
        started=time.monotonic_ns()
        spec,handler,args=self.registry.resolve(inv)
        decision=self.policy.check(spec,inv,grant)
        if not decision.admitted:raise ToolError('tool grant refused: '+decision.reason)
        if spec.risk!='read' and not spec.idempotent:
            raise ToolError('non-idempotent effects require durable external effect custody')
        raw=json.dumps({'scope':[inv.tenant,inv.user,inv.session],
                        'name':inv.tool_name,'args':args,'spec':inv.expected_spec_sha},
                       sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        digest=sha256(raw).hexdigest()
        identity=(inv.tenant,inv.user,inv.session,inv.invocation_id)
        if identity in self._receipts:
            old=self._receipts[identity]
            if old.request_sha!=digest:raise ToolError('invocation ID request conflict')
            return old
        if self._count>=self.max:raise ToolError('tool execution budget exhausted')
        self._count+=1
        try:
            result=handler(args)
            if not isinstance(result,dict):raise ToolError('tool handler returned non-object')
            encoded=json.dumps(result,allow_nan=False).encode()
            if len(encoded)>spec.max_output_bytes:raise ToolError('tool output exceeds boundary')
            elapsed=time.monotonic_ns()-started
            if elapsed>spec.timeout_ms*1_000_000:
                raise ToolError('tool exceeded postcondition deadline')
            receipt=ToolExecutionReceipt(inv.invocation_id,spec.digest,digest,output_digest(result),
                                        'succeeded',result,elapsed)
            self._receipts[identity]=receipt
            return receipt
        except Exception as exc:
            # An effectful operation may have happened before a timeout/exception;
            # therefore never fabricate a failed-safe retry receipt for it.
            if spec.risk!='read':
                self._receipts[identity]=ToolExecutionReceipt(inv.invocation_id,spec.digest,digest,
                    output_digest({}),'uncertain',{},time.monotonic_ns()-started,'effect-outcome-unknown')
            raise ToolError('tool operation failed or is uncertain') from exc
