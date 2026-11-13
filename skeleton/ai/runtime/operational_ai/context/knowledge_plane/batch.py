"""Bounded all-or-none corpus ingestion, no partial indexed release."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .contracts import (KnowledgeError,KnowledgePolicy,document_id,source_path,rights_tag,
                        content_type,title_text)
from .path_guard import read_source
from . import ingest


@dataclass(frozen=True,slots=True)
class BatchItem:
    source: str
    document_id: str
    title: str
    rights: str
    content_type: str
    expected_revision: int

    def validate(self,policy:KnowledgePolicy)->None:
        source_path(self.source);document_id(self.document_id)
        title_text(self.title,policy=policy);rights_tag(self.rights)
        content_type(self.content_type)
        if type(self.expected_revision)is not int or self.expected_revision<0:
            raise KnowledgeError('invalid batch compare-and-swap revision')


def ingest_batch(plane, *, source_root, items: Iterable[BatchItem],
                 approved: bool=False, maximum: int=16)->tuple[dict,...]:
    if approved is not True:raise KnowledgeError('independent bulk import approval required')
    if type(maximum)is not int or not 1<=maximum<=64:
        raise KnowledgeError('invalid finite batch limit')
    from itertools import islice
    entries=tuple(islice(iter(items),maximum+1))
    if not entries or len(entries)>maximum:
        raise KnowledgeError('empty or unbounded knowledge import batch')
    if any(not isinstance(item,BatchItem) for item in entries):
        raise KnowledgeError('untrusted bulk document descriptor')
    ids=set();paths=set();prepared=[];total=0
    for item in entries:
        item.validate(plane.policy)
        if item.document_id in ids or item.source in paths:
            raise KnowledgeError('duplicate batch source or document identity')
        ids.add(item.document_id);paths.add(item.source)
        raw=read_source(source_root,item.source,policy=plane.policy)
        total+=len(raw)
        if total>min(plane.policy.max_total_bytes,64*1024*1024):
            raise KnowledgeError('operator import batch byte budget exceeded')
        prepared.append((item,raw))
    # Separate path inspection from the short authoritative SQLite transaction.
    with plane.db.transaction() as conn:
        written=[]
        for item,raw in prepared:
            record,replayed=ingest.ingest(conn,plane.identity,raw,
                doc_id=item.document_id,title=item.title,rights=item.rights,
                kind=item.content_type,approved=True,
                expected_revision=item.expected_revision,policy=plane.policy)
            written.append(record.to_dict()|{'replayed':replayed})
        return tuple(written)
