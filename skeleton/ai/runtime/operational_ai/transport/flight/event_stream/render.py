"""Encode a finite, authenticated SSE response with no raw model text."""
from __future__ import annotations
import json
from .contracts import StreamError
from .reader import StreamSnapshot

def _event(kind:str,payload:dict,cursor:str|None=None)->bytes:
    body=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    if len(body)>8192:raise StreamError('event JSON exceeds delivery bound')
    frame=(('id: '+cursor+'\n') if cursor else '')+'event: '+kind+'\n'+'data: '+body+'\n\n'
    return frame.encode('ascii')

def encode(snapshot:StreamSnapshot,*,limit_bytes:int=65536)->bytes:
    if not isinstance(snapshot,StreamSnapshot) or type(limit_bytes) is not int or not 8192<=limit_bytes<=262144:
        raise StreamError('invalid finite event response')
    parts=[b': private authenticated flight event projection\n\n']
    for event in snapshot.events:
        parts.append(_event('transition',event.public(),event.cursor))
    # The final checkpoint is not a new transition; it cannot forge progress.
    parts.append(_event('checkpoint',snapshot.record(),snapshot.next_cursor))
    raw=b''.join(parts)
    if len(raw)>limit_bytes:
        raise StreamError('bounded stream response exceeds quota')
    return raw
