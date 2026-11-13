"""Validate observed state against last durable transition, not only hashes."""
from __future__ import annotations
from .contracts import FlightConflict

END_STATE={
 'submitted':'queued', 'claimed':'claimed', 'model-started':'running',
 'heartbeat':None, 'completed':'completed', 'receipt-recovered':'completed',
 'held':'held','uncertain-held':'held', 'cancel-requested':'running',
 'cancelled':'cancelled','unstarted-requeued':'queued',
}

ALLOWED={
 'submitted':(None,),
 'claimed':('queued',),
 'model-started':('claimed',),
 'heartbeat':('claimed','running'),
 'completed':('running',),
 'receipt-recovered':('running',),
 'held':('claimed','running'),
 'uncertain-held':('running',),
 'cancel-requested':('running',),
 'cancelled':('queued','claimed'),
 'unstarted-requeued':('claimed',),
}


def verify(events:list[dict]|tuple[dict,...],current_state:str)->str:
    state=None
    for event in events:
        kind=event['kind']
        if kind not in END_STATE or state not in ALLOWED[kind]:
            raise FlightConflict('invalid durable flight transition sequence')
        state=END_STATE[kind] or state
    if state!=current_state:
        raise FlightConflict('job status differs from durable event transition')
    return state
