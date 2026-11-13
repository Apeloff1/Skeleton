"""Strict independent read of private immutable delivery artifacts."""
from __future__ import annotations
from hashlib import sha256
from .contracts import DeliveryHeld,event_id,digest
from skeleton.ai.runtime.operational_ai.authority.canonical import load_json
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import canonical

def verify_saved_receipt(raw:bytes,filename:str)->dict:
    if type(raw)is not bytes or not 1<=len(raw)<=524288:
        raise DeliveryHeld('invalid saved receipt length')
    try:value=load_json(raw,ceiling=524288)
    except Exception as exc:raise DeliveryHeld('invalid saved receipt JSON') from exc
    if type(value)is not dict or set(value)!={'schema','event_key','stream','kind',
                         'source_sequence','source_sha256','payload'} or value['schema']!='skeleton.ai.local-delivery.v1':
        raise DeliveryHeld('saved receipt schema mismatch')
    if canonical(value,ceiling=524288)!=raw:
        raise DeliveryHeld('noncanonical delivery receipt')
    key=event_id(value['event_key']);event_id(value['stream'])
    if filename!=sha256(key.encode('ascii')).hexdigest()+'.event':
        raise DeliveryHeld('delivery filename does not match event identity')
    digest(value['source_sha256'])
    from .schema import validate_external
    validate_external({'sequence':value['source_sequence'], 'event_key':value['event_key'],
       'stream':value['stream'], 'kind':value['kind'],
       'payload':value['payload'], 'event_sha256':value['source_sha256']})
    if sha256(canonical(value['payload'],ceiling=262144)).hexdigest()!=value['source_sha256']:
        raise DeliveryHeld('saved receipt upstream payload digest mismatch')
    if type(value['source_sequence'])is not int or value['source_sequence']<1:
        raise DeliveryHeld('saved receipt source ordinal invalid')
    return {'event_key':key,'delivery_sha256':sha256(raw).hexdigest(),
            'kind':value['kind'],'verified':True}
