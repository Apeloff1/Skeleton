"""One content-addressed, redacted, canonical on-disk delivery receipt."""
from __future__ import annotations
from hashlib import sha256
from ..outbox_delivery.contracts import DeliveryHeld,event_id,digest,verify_public
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import canonical


def encode(event:dict)->tuple[str,bytes,str]:
    from .schema import validate_external
    validate_external(event)
    if set(event)!={'sequence','event_key','stream','kind','payload','event_sha256'}:
        raise DeliveryHeld('outbox event omitted required custody fields')
    key=event_id(event['event_key']);stream=event_id(event['stream']);upstream=digest(event['event_sha256'])
    raw=canonical(event['payload'],ceiling=262144)
    if sha256(raw).hexdigest()!=upstream:
        raise DeliveryHeld('outbox payload digest mismatch')
    ordinal=event['sequence']
    if type(ordinal)is not int or not 1<=ordinal<=2**63-1:
        raise DeliveryHeld('invalid delivery source sequence')
    record={'schema':'skeleton.ai.local-delivery.v1','event_key':key,
            'stream':stream,'kind':event['kind'],'source_sequence':ordinal,
            'source_sha256':upstream,'payload':event['payload']}
    encoded=canonical(record,ceiling=524288)
    return sha256(key.encode('ascii')).hexdigest()+'.event',encoded,sha256(encoded).hexdigest()
