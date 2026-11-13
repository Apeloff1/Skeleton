"""Read-only, bounded integrity doctor covering foreign keys, chain and receipts."""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import Identity,IntegrityFailure,SpineError,canonical
from .chain import verify

def inspect(db,*,maximum_entries:int=100_000)->dict:
    db.inspect()
    with db.snapshot() as conn:
        proof=verify(conn,limit=maximum_entries)
        principals=conn.execute('SELECT principal,identity_json FROM principals').fetchall()
        for principal,raw in principals:
            try:value=json.loads(raw)
            except(TypeError,ValueError):raise IntegrityFailure('principal JSON corrupted')
            try:bound=Identity(**value)
            except Exception as exc:raise IntegrityFailure('invalid principal record') from exc
            if principal!=bound.key() or raw!=canonical(bound.as_dict()):
                raise IntegrityFailure('stored principal identity altered')
        sessions=conn.execute('SELECT session,revision FROM sessions').fetchall()
        if len(sessions)>maximum_entries:raise SpineError('too many sessions for bounded inspection')
        for session,revision in sessions:
            count=conn.execute('SELECT COUNT(*),MAX(revision) FROM turns WHERE session=?',(session,)).fetchone()
            if count[0]!=revision or (count[1] or 0)!=revision:
                raise IntegrityFailure('session revision or turn inventory mismatch')
        turns=conn.execute('SELECT session,request_id,receipt_json,receipt_sha256,response FROM turns').fetchall()
        if len(turns)>maximum_entries:raise SpineError('too many turns for bounded inspection')
        for session,request,raw,sha,response in turns:
            if not isinstance(raw,bytes) or not isinstance(response,bytes):
                raise IntegrityFailure('turn receipt or output changed SQLite storage type')
            if sha256(raw).hexdigest()!=sha:raise IntegrityFailure('turn receipt corrupted')
            try:rec=json.loads(raw)
            except(TypeError,ValueError):raise IntegrityFailure('turn receipt JSON invalid')
            if sha256(response).hexdigest()!=rec.get('output_sha256'):
                raise IntegrityFailure('turn output corrupted')
            if (not isinstance(rec.get('context_sha256'),str) or len(rec['context_sha256'])!=64):
                raise IntegrityFailure('context custody digest missing')
            if not isinstance(rec.get('context_sha256'),str) or len(rec['context_sha256'])!=64:
                raise IntegrityFailure('context custody digest missing')
            if rec.get('session')!=session or rec.get('request_id')!=request:
                raise IntegrityFailure('turn identity mismatch')
            event=conn.execute('SELECT event_json,event_sha256 FROM outbox WHERE event_key=?',
                (f'turn_{session}_{request}',)).fetchone()
            if not event or sha256(event[0]).hexdigest()!=event[1]:
                raise IntegrityFailure('missing or corrupted transactional audit outbox')
            if event[0]!=raw or event[1]!=sha:
                raise IntegrityFailure('turn receipt and transactional outbox disagree')
            witnessed=conn.execute("SELECT COUNT(*) FROM chain WHERE stream=? AND entry_kind='turn_committed' AND payload_sha256=?", (session,sha)).fetchone()[0]
            if witnessed!=1:raise IntegrityFailure('missing or duplicate witnessed turn commitment')
        pending=conn.execute("SELECT COUNT(*) FROM requests WHERE state='pending'").fetchone()[0]
        unacked=conn.execute('SELECT COUNT(*) FROM outbox WHERE acked=0').fetchone()[0]
        return {'status':'integrity-verified-not-release-certified','chain':proof,
            'principals':len(principals),'sessions':len(sessions),'turns':len(turns),
            'pending':pending,'outbox_pending':unacked}
