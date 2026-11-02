"""Strict operations across the actual private FlightApplication.

Generated model output is NEVER interpreted as a tool invocation or operator
approval. `work_one` spends model time only after caller bearer verification.
"""
from __future__ import annotations
from ...authority.canonical import ContractViolation
import time
from ...orchestration.execution_spine.contracts import identifier,SpineError
from ...orchestration.flight_control.contracts import FlightSpec,FlightConflict
from ...orchestration.flight_control.admission import inspect_before_submit
from .contracts import validate_payload


class FlightDispatcher:
    def __init__(self,application,*,knowledge_plane=None,on_submit=None,allow_manual_work:bool=True,accepting=None):
        self.app=application
        self.knowledge=knowledge_plane
        if on_submit is not None and not callable(on_submit):
            raise ContractViolation('submission wake callback must be callable')
        if type(allow_manual_work) is not bool:
            raise ContractViolation('explicit manual worker mode required')
        if accepting is not None and not callable(accepting):
            raise ContractViolation('submission guard must be callable')
        self.on_submit=on_submit
        self.allow_manual_work=allow_manual_work
        self.accepting=accepting
        if application.spine.identity!=application.ledger.identity:
            raise ContractViolation('flight dispatcher owner/model mismatch')
        if application.worker.ledger is not application.ledger:
            raise ContractViolation('flight dispatcher worker belongs to another queue')

    def dispatch(self,operation:str,payload:dict)->dict:
        validate_payload(operation,payload)
        app=self.app
        if operation=='create':
            session=identifier(payload['session_id'],'session')
            return {'session_id':app.spine.create(session),'created':True}
        if operation=='submit':
            if self.accepting is not None and self.accepting() is not True:
                from ...orchestration.flight_control.contracts import FlightBusy
                raise FlightBusy('automatic native worker is not accepting new work')
            spec=FlightSpec(
                app.spine.identity,
                identifier(payload['job_id'],'job'),
                identifier(payload['session_id'],'session'),
                identifier(payload['request_id'],'request'),
                payload['question'],
                seed=payload.get('seed',0),
                temperature=payload.get('temperature',0.8),
                priority=payload.get('priority',0))
            admission=inspect_before_submit(app.ledger,app.spine,spec)
            record=app.ledger.submit(spec)
            if self.on_submit is not None:
                try:self.on_submit()
                except Exception:
                    # Queue transaction already committed; wakeup is best effort
                    # and periodic polling will pick up the durable task.
                    pass
            return {'job':record,'model_calls':0,'preflight':admission}
        if operation=='work_one':
            if not self.allow_manual_work:
                raise ContractViolation('manual inference unavailable while auto worker owns backend')
            receipt=app.worker.run_one()
            if receipt is None:
                return {'status':'empty','model_calls':0}
            return {'status':receipt.state,'job_id':receipt.job_id,
                    'revision':receipt.revision,'recovered':receipt.recovered}
        if operation=='cancel':
            result=app.ledger.cancel(identifier(payload['job_id'],'job'))
            if self.on_submit is not None:
                try:self.on_submit()
                except Exception:pass
            return {'job':result,'model_calls':0}
        if operation=='wait':
            job=identifier(payload['job_id'],'job')
            max_wait=payload.get('max_wait_ms',0)
            if type(max_wait)is not int or not 0<=max_wait<=2000:
                raise ContractViolation('bounded wait must be 0..2000 ms')
            deadline=time.monotonic_ns()+max_wait*1_000_000
            while True:
                record=app.ledger.inspect(job)
                if record['state'] in ('completed','held','cancelled') or time.monotonic_ns()>=deadline:
                    return {'job':record,'model_calls':0}
                time.sleep(min(.04,max(0,(deadline-time.monotonic_ns())/1e9)))
        if operation=='job':
            return {'job':app.ledger.inspect(identifier(payload['job_id'],'job'))}
        if operation=='queue':
            return {'counts':app.ledger.state_count(),
                    'model_sha256':app.spine.identity.model_sha256}
        if operation=='history':
            session=identifier(payload['session_id'],'session')
            return {'session_id':session,'messages':list(app.spine.history(session))}
        if operation=='replay':
            record=app.spine.replay(identifier(payload['session_id'],'session'),
                  identifier(payload['request_id'],'request'),payload['question'],
                  seed=payload.get('seed',0),temperature=payload.get('temperature',0.8))
            return {'receipt':record,'model_calls':0}
        if operation=='knowledge_search':
            if self.knowledge is None:
                raise ContractViolation('private knowledge capability unavailable')
            limit=payload.get('limit',4)
            if type(limit)is not int or not 1<=limit<=6:
                raise ContractViolation('invalid bounded source limit')
            return {'hits':list(self.knowledge.search(payload['question'],limit=limit))}
        raise ContractViolation('unknown operation')
