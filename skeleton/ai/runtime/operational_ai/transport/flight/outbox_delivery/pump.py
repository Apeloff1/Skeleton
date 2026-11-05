"""Exactly-once local *file identity* across SQLite + filesystem crashes.

This does NOT claim exactly-once external events. Deliveries never execute
model-selected tools, network callbacks or untrusted application code.
"""
from __future__ import annotations
from .contracts import DeliveryHeld,DeliveryPolicy
from .sink import PrivateEventSink
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import outbox

class DeliveryPump:
    def __init__(self,ledger,sink:PrivateEventSink,*,policy:DeliveryPolicy|None=None):
        if not isinstance(sink,PrivateEventSink) or not hasattr(ledger,'identity') or not hasattr(ledger,'db'):
            raise DeliveryHeld('principal-bound SQLite and private spool required')
        self.ledger=ledger
        self.sink=sink
        self.policy=policy or DeliveryPolicy()
        self.sink.bind(ledger.identity)
    def _authorize(self,conn,event):
        if event['kind']=='ai_flight':
            job=self.ledger._get(conn,event['stream'])
            if job['principal']!=self.ledger.identity.key():
                raise DeliveryHeld('flight event outside owned principal')
            from skeleton.ai.runtime.operational_ai.orchestration.flight_control import events
            events.inspect(conn,event['stream'],max_events=4096)
        elif event['kind']=='ai_turn':
            if event['payload'].get('principal')!=self.ledger.identity.key():
                raise DeliveryHeld('native inference receipt outside owned principal')
        else:raise DeliveryHeld('delivery type is not an authorized AI observation')
    def audit(self,*,limit:int=4096)->dict:
        from .audit import verify_custody
        return verify_custody(self.ledger,self.sink,limit=limit)

    def drain(self,*,limit:int=32)->dict:
        from .contracts import count
        count(limit,128)
        if limit>self.policy.max_batch:
            raise DeliveryHeld('operator delivery batch limit exceeded')
        # Every previously acked file must remain verifiable before writing a
        # new receipt. Missing or altered exports hold the delivery boundary.
        self.audit(limit=self.policy.max_inventory)
        with self.ledger.db.snapshot() as conn:
            # Inspect all pending rows before selecting; unknown event kinds are
            # not acknowledged by this observer and must never be rewritten.
            pending=outbox.pending(conn,limit=256)
            records=[]
            for record in pending:
                if record['kind'] not in ('ai_flight','ai_turn'):continue
                self._authorize(conn,record)
                records.append(record)
                if len(records)>=limit:break
        sent=[]
        for event in records:
            proof=self.sink.append(event)
            # SQLite ack is intentionally AFTER fsync. Crash between those
            # steps causes a byte-identical replay, not another new file.
            with self.ledger.db.transaction() as conn:
                outbox.acknowledge(conn,event['event_key'],event['event_sha256'])
            sent.append(proof)
        return {'status':'bounded-private-delivery',
                'count':len(sent),'replayed':sum(x['replayed'] for x in sent),
                'delivery_hashes':tuple(x['delivery_sha256'] for x in sent),
                'model_calls':0}
