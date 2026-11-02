"""Strict operations across the actual private FlightApplication.

Generated model output is NEVER interpreted as a tool invocation or operator
approval. `work_one` spends model time only after caller bearer verification.
"""
from __future__ import annotations
from ...authority.canonical import ContractViolation
from ...orchestration.execution_spine.contracts import identifier,SpineError
from ...orchestration.flight_control.contracts import FlightSpec,FlightConflict
from .contracts import validate_payload


class FlightDispatcher:
    def __init__(self,application,*,knowledge_plane=None):
        self.app=application
        self.knowledge=knowledge_plane
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
            record=app.ledger.submit(FlightSpec(
                app.spine.identity,
                identifier(payload['job_id'],'job'),
                identifier(payload['session_id'],'session'),
                identifier(payload['request_id'],'request'),
                payload['question'],
                seed=payload.get('seed',0),
                temperature=payload.get('temperature',0.8),
                priority=payload.get('priority',0)))
            return {'job':record,'model_calls':0}
        if operation=='work_one':
            receipt=app.worker.run_one()
            if receipt is None:
                return {'status':'empty','model_calls':0}
            return {'status':receipt.state,'job_id':receipt.job_id,
                    'revision':receipt.revision,'recovered':receipt.recovered}
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
