"""Prove both sides of the SQLite -> immutable-file delivery boundary.

An outbox `acked` bit alone does not prove a consumer can recover its receipt.
This auditor reviews *all* bounded owned deliveries, including already acked
rows, and refuses a missing file, conflicting local copy or an untracked spool
file. A pending row with an already published file is valid after a crash.
"""
from __future__ import annotations
from hashlib import sha256
import json,os
from .contracts import DeliveryHeld,count
from .projection import encode
from .verify import verify_saved_receipt
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import canonical


def _decode(row):
    sequence,key,stream,kind,raw,upstream,acked=row
    try:payload=json.loads(raw)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise DeliveryHeld('corrupt persisted AI observation') from exc
    if sha256(raw).hexdigest()!=upstream or canonical(payload,ceiling=262144)!=raw:
        raise DeliveryHeld('authoritative AI observation mutated')
    return {'sequence':sequence,'event_key':key,'stream':stream,'kind':kind,
            'payload':payload,'event_sha256':upstream},acked


def verify_custody(ledger,sink,*,limit:int=4096)->dict:
    count(limit,16384)
    sink._require_bound()
    # Compare a single immutable snapshot against disk. Updates while reading
    # are either rejected or rechecked on the next invocation; no DB rewrite.
    with ledger.db.snapshot() as conn:
        rows=conn.execute("""SELECT sequence,event_key,stream,kind,event_json,event_sha256,acked
          FROM outbox WHERE kind IN ('ai_flight','ai_turn') ORDER BY sequence LIMIT ?""",(limit+1,)).fetchall()
        if len(rows)>limit:
            raise DeliveryHeld('owned delivery audit exceeds bounded inventory')
        events=[]
        for row in rows:
            event,acked=_decode(row)
            # Verify principal and canonical flight event continuity under same
            # transaction before trusting an exported observation.
            if event['kind']=='ai_flight':
                job=ledger._get(conn,event['stream'])
                if job['principal']!=ledger.identity.key():
                    raise DeliveryHeld('flight observation has wrong owner')
                from skeleton.ai.runtime.operational_ai.orchestration.flight_control import events as flight_events
                flight_events.inspect(conn,event['stream'],max_events=4096)
            else:
                if event['payload'].get('principal')!=ledger.identity.key():
                    raise DeliveryHeld('turn observation has wrong owner')
                identity=(event['stream'],event['payload'].get('request_id'))
                entry=conn.execute('SELECT receipt_json,receipt_sha256 FROM turns WHERE session=? AND request_id=?',identity).fetchone()
                if entry is None or sha256(entry[0]).hexdigest()!=entry[1] or entry[0]!=row[4]:
                    raise DeliveryHeld('turn observation differs from committed inference')
            filename,expected,digest=encode(event)
            events.append((filename,expected,digest,bool(acked)))
        with sink._lock_guard():
            sink._require_bound()
            names=os.listdir(sink._fd)
            known={name for name,raw,digest,acked in events}
            actual={name for name in names if name.endswith('.event')}
            if actual-known:
                raise DeliveryHeld('spool contains an event absent from authoritative database')
            if len(actual)>sink.policy.max_inventory:
                raise DeliveryHeld('private spool exceeds bounded audit inventory')
            verified=0;unacked_published=0
            for name,raw,digest,acked in events:
                if name not in actual:
                    if acked:
                        raise DeliveryHeld('acknowledged AI event has no durable receipt')
                    continue
                saved=sink._read(name)
                if saved!=raw:
                    raise DeliveryHeld('published AI event is incomplete or altered')
                verify_saved_receipt(saved,name)
                verified+=1
                if not acked:unacked_published+=1
            if len(names)>len(actual)+2:
                raise DeliveryHeld('private spool contains unexpected metadata')
        return {'status':'verified-owned-delivery-custody',
                'database_events':len(events),'published_receipts':verified,
                'unacknowledged_published':unacked_published,
                'acknowledged':sum(acked for _,_,_,acked in events),
                'model_calls':0,'release_certified':False}
