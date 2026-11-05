"""Work one ready DAG node and commit its auditable outcome.

A failed or ambiguous call is NEVER retried automatically. Model output cannot
write a new plan, create permissions or execute tools without independent consent.
"""
from __future__ import annotations
import json,threading
from .ports import Ports
from .receipts import receipt
from ..core.errors import Held,Unauthorized,Invalid
from ..core.canonical import canonical,identifier,text
from ..planning.dag import ready
from ..authorization.redemption import redeem
class AgentFabric:
    def __init__(self,store,ports:Ports):
        self.store=store;self.ports=ports
        self._lock=threading.RLock()
    def submit(self,plan):return self.store.create(plan)
    def next(self,plan_id):
        plan,states,status=self.store.load(plan_id)
        if status!='active':return ()
        return ready(plan,{k for k,v in states.items() if v['state']=='complete'},
                     {k for k,v in states.items() if v['state']!='pending'})
    def run_one(self,plan_id,*,worker='local_worker',grant=None,arguments=None):
        identifier(worker,'worker')
        with self._lock:
            candidates=self.next(plan_id)
            if not candidates:return None
            step_id=candidates[0]
            plan,states,_=self.store.load(plan_id)
            step=next(s for s in plan.steps if s.step_id==step_id)
            # Do not claim a tool step until independently signed authority exists.
            if step.kind=='tool' and (grant is None or self.ports.tool is None or self.ports.operator_key is None):
                raise Unauthorized('tool step awaiting separate operator grant')
            fence=self.store.start(plan_id,step_id,worker)
        try:
            if step.kind=='model':
                from hashlib import sha256
                request_id='ag_'+sha256((plan_id+':'+step_id).encode('ascii')).hexdigest()
                result=self.ports.model.complete(session=plan.session_id,
                    request_id=request_id,prompt=step.instruction)
                if (not isinstance(result,dict) or result.get('model_sha256')!=self.store.identity.model_sha256
                    or result.get('tokenizer_sha256')!=self.store.identity.tokenizer_sha256):
                    raise Invalid('model/tokenizer custody proof required')
                output=result.get('output_sha256')
                from ..core.canonical import hex_digest
                hex_digest(output,'model output')
                proof=receipt('model',bytes.fromhex(output),{'request_id':request_id,
                           'native_output_sha256':output})
            elif step.kind=='read':
                # Read-only knowledge requires an independently supplied bounded port.
                if self.ports.reader is None:raise Unauthorized('approved read-only knowledge port required')
                source=self.ports.reader.read(instruction=step.instruction,owner=self.store.identity.key())
                if not isinstance(source,dict) or 'sha256' not in source:raise Invalid('provenance-bound source required')
                from ..core.canonical import hex_digest
                hex_digest(source['sha256'],'source')
                proof=receipt('read',bytes.fromhex(source['sha256']),{'source_sha256':source['sha256']})
            elif step.kind=='review':
                if self.ports.reviewer is None:raise Unauthorized('independent reviewer required')
                review=self.ports.reviewer.request_approval(plan_id,step_id,step.instruction)
                if not isinstance(review,dict) or review.get('approved') is not True:
                    raise Held('operator review pending or rejected')
                proof=receipt('review',canonical({'approved':True}),{'approval':'independent-caller'})
            else:
                assert self.ports.operator_key is not None and self.ports.tool is not None
                params=arguments if arguments is not None else {}
                redeem(self.store.db,self.ports.operator_key,grant,plan=plan_id,step=step_id,
                       resource=step.resource,operation='execute',arguments=params)
                response=self.ports.tool.execute(step.resource,'execute',params)
                if not isinstance(response,dict):raise Invalid('tool receipt required')
                proof=receipt('tool',canonical(response),{'approval':'durably-redeemed'})
            checksum=self.store.finish(plan_id,step_id,worker,fence,proof)
            return {'plan_id':plan_id,'step_id':step_id,'receipt_sha256':checksum,'status':'complete'}
        except BaseException as exc:
            # An uncertain effect cannot be replayed from the workflow's retry queue.
            reason=type(exc).__name__
            try:self.store.hold(plan_id,step_id,worker,fence,reason if reason.isidentifier() else 'Held')
            except Exception:pass
            raise
