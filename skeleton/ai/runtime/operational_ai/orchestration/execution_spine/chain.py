"""Transactional hash-chain ledger: verified after each durable state read."""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import canonical,hexdigest,IntegrityFailure,digest,SpineError
ZERO='0'*64

def append(db,stream:str,kind:str,event:dict)->str:
    from .contracts import identifier
    identifier(stream,'stream');identifier(kind,'event kind')
    raw=canonical(event,ceiling=262144)
    head=db.execute('SELECT entry_hash FROM chain ORDER BY sequence DESC LIMIT 1').fetchone()
    previous=head[0] if head else ZERO
    payload_sha=sha256(raw).hexdigest()
    record={'stream':stream,'kind':kind,'payload_sha256':payload_sha,'previous':previous}
    entry_hash=digest(record)
    db.execute('INSERT INTO chain(stream,entry_kind,payload_sha256,previous_hash,entry_hash,entry_json) VALUES(?,?,?,?,?,?)',
        (stream,kind,payload_sha,previous,entry_hash,raw))
    return entry_hash

def verify(db,*,limit:int=100000)->dict:
    if type(limit)is not int or not 1<=limit<=1_000_000:raise SpineError('invalid chain verification bound')
    count=db.execute('SELECT COUNT(*) FROM chain').fetchone()[0]
    if count>limit:raise SpineError('chain exceeds bounded verification window')
    prior=ZERO;last=0
    for seq,stream,kind,payload_sha,prev,entry_hash,raw in db.execute('SELECT sequence,stream,entry_kind,payload_sha256,previous_hash,entry_hash,entry_json FROM chain ORDER BY sequence'):
        if type(seq)is not int or seq<=last:raise IntegrityFailure('non-monotonic audit sequence')
        last=seq
        if prev!=prior:raise IntegrityFailure('audit previous hash mismatch')
        try:decoded=json.loads(raw)
        except (ValueError,TypeError):raise IntegrityFailure('audit event JSON invalid')
        if canonical(decoded,ceiling=262144)!=raw:raise IntegrityFailure('noncanonical audit event')
        if sha256(raw).hexdigest()!=payload_sha:raise IntegrityFailure('audit payload mutation')
        expected=digest({'stream':stream,'kind':kind,'payload_sha256':payload_sha,'previous':prev})
        if expected!=entry_hash:raise IntegrityFailure('audit chain hash mismatch')
        prior=entry_hash
    return {'entries':count,'head':prior,'last_sequence':last}
