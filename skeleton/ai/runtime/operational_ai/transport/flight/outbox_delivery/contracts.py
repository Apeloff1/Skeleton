"""Finite spool authority: verified AI observations only, no model text."""
from __future__ import annotations
from dataclasses import dataclass
import re

_ID=re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_SHA=re.compile(r'^[0-9a-f]{64}$')
_ALLOWED=frozenset(('ai_flight','ai_turn'))
_DENIED=frozenset(('text','prompt','question','content','messages','passage','source_text',
                  'api_key','authorization','bearer','secret','private_key'))

class DeliveryHeld(RuntimeError):
    """Unsafe event or filesystem state requires independent operator review."""

def event_id(value:object)->str:
    if type(value)is not str or _ID.fullmatch(value) is None:
        raise DeliveryHeld('noncanonical event identifier')
    return value

def digest(value:object)->str:
    if type(value)is not str or _SHA.fullmatch(value) is None:
        raise DeliveryHeld('malformed event digest')
    return value

def count(value:object,maximum:int=256)->int:
    if type(value)is not int or not 1<=value<=maximum:
        raise DeliveryHeld('delivery limit exceeds bound')
    return value

def verify_public(event:dict)->None:
    if type(event)is not dict or event.get('kind') not in _ALLOWED:
        raise DeliveryHeld('unsupported private delivery kind')
    def check(value,depth=0):
        if depth>12:raise DeliveryHeld('excessive event object nesting')
        if isinstance(value,dict):
            for k,v in value.items():
                if type(k)is not str or k.lower() in _DENIED:
                    raise DeliveryHeld('event contains potentially private prompt or model text')
                check(v,depth+1)
        elif isinstance(value,(list,tuple)):
            for v in value:check(v,depth+1)
        elif type(value) not in (str,int,float,bool,type(None)):
            raise DeliveryHeld('unsupported outbox payload type')
    check(event.get('payload'))

@dataclass(frozen=True,slots=True)
class DeliveryPolicy:
    max_batch:int=32
    max_receipt_bytes:int=262144
    max_inventory:int=4096
    def __post_init__(self):
        count(self.max_batch,128)
        if type(self.max_receipt_bytes)is not int or not 4096<=self.max_receipt_bytes<=524288:
            raise DeliveryHeld('invalid receipt ceiling')
        count(self.max_inventory,16384)
