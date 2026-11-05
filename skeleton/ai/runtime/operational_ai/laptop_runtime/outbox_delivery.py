"""Read-only event inventory and caller-acknowledged outbox delivery."""
from __future__ import annotations
from .contracts import identifier,identity_hash,refuse

class DeliveryCursor:
    def __init__(self,worker,*,maximum=32):
        if type(maximum) is not int or not 1<=maximum<=32:
            refuse("invalid outbox ceiling")
        self.worker=worker;self.maximum=maximum

    def pending(self):
        events=self.worker.spine.pending_events(limit=self.maximum)
        if not isinstance(events,(tuple,list)):
            refuse("invalid authoritative outbox snapshot")
        if len(events)>self.maximum:
            refuse("outbox exceeded maximum")
        return list(events)

    def acknowledge(self,event_key,event_sha256):
        result=self.worker.spine.acknowledge_event(identifier(event_key),
                                                   identity_hash(event_sha256))
        if type(result) is not bool:
            refuse("invalid outbox acknowledgment")
        return result
