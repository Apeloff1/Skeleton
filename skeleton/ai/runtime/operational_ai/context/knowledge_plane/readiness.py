"""Explicit retrieval readiness rather than treating table presence as proof."""
from __future__ import annotations
from .contracts import KnowledgeError
from . import schema


def inspect_readiness(plane, *, minimum_documents: int = 0, maximum: int = 65536) -> dict:
    if type(minimum_documents)is not int or not 0<=minimum_documents<=100000:
        raise KnowledgeError('invalid required minimum source inventory')
    schema.verify(plane.db)
    evidence=plane.doctor(maximum=maximum)
    active=evidence['proof']['active_documents']
    return {'schema':'skeleton.ai.knowledge-readiness.v1',
            'principal':plane.identity.key(), 'documents':active,
            'status':'ready' if active>=minimum_documents else 'insufficient-approved-sources',
            'source_custody_sha256':evidence['proof_sha256'],
            'minimum_documents':minimum_documents,'model_calls':0}
