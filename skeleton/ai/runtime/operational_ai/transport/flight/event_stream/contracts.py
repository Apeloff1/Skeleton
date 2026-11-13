"""Finite event stream contract: no model output, no forged progress."""
from __future__ import annotations
from dataclasses import dataclass
import re

_HEX=re.compile(r"^[0-9a-f]{64}$")
_JOB=re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_STATES=frozenset({'queued','claimed','running','completed','held','cancelled'})
_TERMINAL=frozenset({'completed','held','cancelled'})

class StreamError(ValueError):
    """A stream request cannot safely be fulfilled."""
class InvalidCursor(StreamError):
    """Invalid or unauthenticated cursor provided by the caller."""
class StreamConflict(StreamError):
    """A previous position disagrees with the authoritative chain."""
class StreamUnavailable(StreamError):
    """No verified snapshot is available; no optimistic status returned."""

def identifier(value:object)->str:
    if type(value) is not str or _JOB.fullmatch(value) is None:
        raise StreamError('invalid bounded stream job identity')
    return value

def hexdigest(value:object)->str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise StreamError('invalid event digest')
    return value

def bounded(value:object, low:int, high:int, name:str)->int:
    if type(value) is not int or not low <= value <= high:
        raise StreamError('invalid bounded '+name)
    return value

@dataclass(frozen=True,slots=True)
class StreamPolicy:
    max_events:int=32
    max_wait_ms:int=2000
    max_snapshot_events:int=4096
    max_payload_bytes:int=65536
    def __post_init__(self):
        bounded(self.max_events,1,64,'event batch')
        bounded(self.max_wait_ms,0,2000,'long poll')
        bounded(self.max_snapshot_events,1,4096,'chain depth')
        bounded(self.max_payload_bytes,8192,262144,'wire bytes')

@dataclass(frozen=True,slots=True)
class FlightEvent:
    job_id:str
    ordinal:int
    kind:str
    digest:str
    cursor:str
    def __post_init__(self):
        identifier(self.job_id)
        bounded(self.ordinal,1,4096,'event ordinal')
        if type(self.kind) is not str or not re.fullmatch('[a-z][a-z0-9-]{0,63}',self.kind):
            raise StreamError('invalid event type')
        hexdigest(self.digest)
        if type(self.cursor) is not str or len(self.cursor)>192:
            raise StreamError('invalid event cursor')
    def public(self)->dict:
        return {'schema':'skeleton.ai.flight-event-observation.v1',
                'job_id':self.job_id,'ordinal':self.ordinal,
                'kind':self.kind,'event_sha256':self.digest}

def terminal(state:str)->bool:
    if state not in _STATES:
        raise StreamUnavailable('unknown authoritative queue state')
    return state in _TERMINAL
