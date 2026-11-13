"""Compare two evidence snapshots with explicit retractions and source drift."""
from __future__ import annotations
from dataclasses import dataclass
from .documents import Document,GroundingError

@dataclass(frozen=True,slots=True)
class SourceRevision:
    doc_id:str
    before_sha:str|None
    after_sha:str|None
    reason:str


def diff_documents(before:tuple[Document,...],after:tuple[Document,...])->tuple[SourceRevision,...]:
    previous={d.doc_id:d for d in before};current={d.doc_id:d for d in after}
    if len(previous)!=len(before) or len(current)!=len(after):
        raise GroundingError('duplicate document identities in revision diff')
    changes=[]
    for key in sorted(set(previous)|set(current)):
        a=previous.get(key);b=current.get(key)
        if a and b and (a.tenant,a.user)!=(b.tenant,b.user):
            raise GroundingError('document identity moved across ownership scopes')
        if a and b and a.sha256==b.sha256 and a.revision==b.revision:continue
        reason='added' if not a else 'removed' if not b else 'revised'
        changes.append(SourceRevision(key,a.sha256 if a else None,b.sha256 if b else None,reason))
    return tuple(changes)
