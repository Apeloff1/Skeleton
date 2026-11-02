"""Read-only local AI observation consumer with bounded restart cursors.

No inference, tool execution or external network transport is performed here.
A caller can resume from an exact monotonic SQLite event sequence and receive
only already published, verified metadata. Raw chat/model text is not present.
"""
from __future__ import annotations
import os
from .contracts import DeliveryHeld,count
from .projection import encode
from .verify import verify_saved_receipt
from .audit import _decode


def read_since(ledger,sink,*,sequence:int=0,limit:int=32)->dict:
    if type(sequence) is not int or not 0<=sequence<2**63:
        raise DeliveryHeld('noncanonical local delivery resume sequence')
    count(limit,256)
    sink._require_bound()
    records=[]
    with ledger.db.snapshot() as conn:
        # A stable source sequence is preferred over filename order; this
        # preserves cross-process event ordering and reveals genuine gaps.
        rows=conn.execute("""SELECT sequence,event_key,stream,kind,event_json,event_sha256,acked
          FROM outbox WHERE sequence>? AND kind IN ('ai_turn','ai_flight')
          ORDER BY sequence LIMIT ?""",(sequence,limit+1)).fetchall()
        more=len(rows)>limit
        for row in rows[:limit]:
            event,acked=_decode(row)
            if event['kind']=='ai_flight':
                job=ledger._get(conn,event['stream'])
                if job['principal']!=ledger.identity.key():
                    raise DeliveryHeld('delivery cursor crossed principal boundary')
                from skeleton.ai.runtime.operational_ai.orchestration.flight_control import events as flight_events
                flight_events.inspect(conn,event['stream'])
            elif event['payload'].get('principal')!=ledger.identity.key():
                raise DeliveryHeld('delivery cursor crossed principal boundary')
            name,raw,sha=encode(event)
            # A pending SQLite row is not yet a committed delivery, even if a
            # file was published before a crash. Reconciliation must run first.
            if not acked:
                more=True
                break
            with sink._lock_guard():
                saved=sink._read(name)
                if saved!=raw:
                    raise DeliveryHeld('published delivery no longer matches source')
                verify_saved_receipt(saved,name)
            records.append({'sequence':event['sequence'],
                 'event_key':event['event_key'],'kind':event['kind'],
                 'stream':event['stream'],'source_sha256':event['event_sha256'],
                 'delivery_sha256':sha})
    return {'schema':'skeleton.ai.private-delivery-cursor.v1',
            'events':tuple(records),'next_sequence':records[-1]['sequence'] if records else sequence,
            'backlog':more,'model_calls':0,'contains_model_text':False}
