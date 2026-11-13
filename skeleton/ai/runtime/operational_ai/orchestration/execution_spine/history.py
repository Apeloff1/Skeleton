"""Bounded, integrity-checked transcript reconstruction from committed receipts."""
from __future__ import annotations
from hashlib import sha256
import json
from .contracts import Identity,SpineLimits,IntegrityFailure,Conflict
from .principal import require_session

def load(conn,identity:Identity,session:str,limits:SpineLimits)->tuple[dict,...]:
    state=require_session(conn,identity,session)
    if state['revision']>limits.max_history:raise Conflict('session exceeds bounded history policy')
    rows=conn.execute('SELECT revision,prompt,response,receipt_json,receipt_sha256 FROM turns WHERE session=? ORDER BY revision',(session,)).fetchall()
    if len(rows)!=state['revision']:raise IntegrityFailure('transcript missing a committed turn')
    history=[]
    for expected,(rev,prompt,response,receipt,sha) in enumerate(rows,1):
        if rev!=expected:raise IntegrityFailure('session revision gap')
        if sha256(receipt).hexdigest()!=sha:raise IntegrityFailure('receipt digest mismatch')
        try:record=json.loads(receipt);user=prompt.decode('utf8');assistant=response.decode('utf8')
        except (ValueError,TypeError,UnicodeError):raise IntegrityFailure('invalid transcript encoding')
        if (record.get('revision')!=rev or record.get('principal')!=identity.key()
            or sha256(response).hexdigest()!=record.get('output_sha256')
            or len(user.encode())>limits.input_bytes or len(response)>limits.response_bytes):
            raise IntegrityFailure('transcript and receipt disagree')
        history.extend(({'role':'user','content':user},{'role':'assistant','content':assistant}))
    return tuple(history)
