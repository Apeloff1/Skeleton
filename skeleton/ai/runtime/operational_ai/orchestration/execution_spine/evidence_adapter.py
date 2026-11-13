"""Scoped encrypted-memory bridge: only independently admitted source excerpts.

Verifies each returned local passage against its full SHA-pinned Source before
admitting it into the lower-trust context lane. Never upgrades tool or model
text to higher authority and never searches across tenants or identities.
"""
from __future__ import annotations
from hashlib import sha256
from .context import Evidence
from .contracts import Identity,Conflict,SpineLimits

class SealedEvidenceProvider:
    def __init__(self,memory,*,max_candidates:int=2048,max_passage:int=4096):
        if type(max_candidates)is not int or not 1<=max_candidates<=2048:
            raise Conflict('unbounded memory source search')
        if type(max_passage)is not int or not 128<=max_passage<=8192:
            raise Conflict('unbounded evidence passage')
        self.memory=memory;self.maximum=max_candidates;self.passage=max_passage

    def __call__(self,identity:Identity,question:str):
        from skeleton.ai.runtime.operational_ai.authority.identity import Actor
        if not isinstance(identity,Identity):raise Conflict('explicit memory identity required')
        actor=Actor(identity.tenant,identity.subject,identity.model_sha256,identity.tokenizer_sha256)
        # The encrypted store validates the per-source AEAD and revision itself.
        source_by_id={source.source_id:source for source in self.memory.sources(actor,maximum=self.maximum)}
        hits=self.memory.search(actor,question,limit=8)
        result=[]
        for hit in hits:
            source=source_by_id.get(hit.source_id)
            if source is None:raise Conflict('search hit absent from authenticated source inventory')
            if source.trust=='model-generated':continue
            if (source.digest!=hit.sha256 or source.body[hit.start:hit.end]!=hit.body or
                hit.end-hit.start>self.passage or source.owner_tenant!=identity.tenant or
                source.owner_user!=identity.subject):
                raise Conflict('retrieved source excerpt failed provenance binding')
            result.append(Evidence(source.source_id,source.revision,hit.body,
                sha256(hit.body.encode('utf8')).hexdigest(),identity.tenant,identity.subject,
                document_sha256=source.digest,start=hit.start,end=hit.end,
                trust=source.trust,rights=source.rights))
        return tuple(result)
