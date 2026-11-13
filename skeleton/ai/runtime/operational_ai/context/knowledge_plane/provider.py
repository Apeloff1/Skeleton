"""Attested bridge from private FTS search to the existing inference context."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import KnowledgePolicy,KnowledgeError
from .search import search
from ...orchestration.execution_spine.context import Evidence
from ...orchestration.execution_spine.contracts import Identity


@dataclass(slots=True)
class KnowledgeEvidenceProvider:
    db: object
    identity: Identity
    policy: KnowledgePolicy = KnowledgePolicy()

    def __call__(self,identity:Identity,question:str)->tuple[Evidence,...]:
        if identity!=self.identity:
            raise KnowledgeError('evidence provider principal or model mismatch')
        with self.db.snapshot() as conn:
            results=search(conn,identity,question,limit=self.policy.max_hits,policy=self.policy)
        return tuple(Evidence(source_id=hit.source_id,revision=hit.revision,
                 content=hit.passage,sha256=hit.passage_sha256,
                 owner_tenant=identity.tenant,owner_subject=identity.subject,
                 document_sha256=hit.document_sha256,start=hit.char_start,end=hit.char_end,
                 trust='local-document',rights=hit.rights) for hit in results)

    def require_current(self,conn,sources:tuple[dict,...])->None:
        """Called INSIDE the inference commit transaction, after model work."""
        from .freshness import require_current
        require_current(conn,self.identity,sources,policy=self.policy)
