"""Bounded, read-only verification of source reconstruction and event custody."""
from __future__ import annotations
from hashlib import sha256
from .contracts import KnowledgeError, KnowledgePolicy
from . import events, catalog
from ...orchestration.execution_spine.contracts import canonical


def _reconstruct(conn, principal: str, doc_id: str, revision: int,
                 normalized_sha: str, expected_chunks: int, maximum: int) -> int:
    rows=conn.execute('''SELECT ordinal,char_start,char_end,passage,passage_sha256,document_sha256
        FROM ai_kb_chunks WHERE principal=? AND doc_id=? AND revision=?
        ORDER BY ordinal LIMIT ?''',(principal,doc_id,revision,maximum+1)).fetchall()
    if len(rows)>maximum or len(rows)!=expected_chunks:
        raise KnowledgeError('missing or unbounded document chunk inventory')
    original=conn.execute('SELECT raw_sha256,normalized_bytes FROM ai_kb_documents '
                          'WHERE principal=? AND doc_id=? AND revision=?',
                          (principal,doc_id,revision)).fetchone()
    if original is None:raise KnowledgeError('orphan document reconstruction')
    # Streaming SHA verification avoids O(document_size^2) reconstruction and
    # prevents a forged overlapping chunk from injecting different text.
    h=sha256();offset=0;byte_count=0;recent=''
    for position,(ordinal,start,end,passage,p_sha,d_sha) in enumerate(rows):
        if (ordinal!=position or type(start)is not int or type(end)is not int or
            not isinstance(passage,str) or end-start!=len(passage) or
            sha256(passage.encode('utf8')).hexdigest()!=p_sha or
            d_sha!=original[0] or start>offset or end<=offset):
            raise KnowledgeError('document chunk content or coverage corrupted')
        overlap=offset-start
        if overlap>len(recent) or (overlap and recent[-overlap:]!=passage[:overlap]):
            raise KnowledgeError('overlapping chunks disagree about original bytes')
        suffix=passage[overlap:]
        encoded=suffix.encode('utf8');h.update(encoded);byte_count+=len(encoded)
        recent=(recent+suffix)[-8192:]
        offset=end
    if h.hexdigest()!=normalized_sha or byte_count!=original[1]:
        raise KnowledgeError('normalized document digest or length mismatch')
    return len(rows)


def inspect(db, identity, *, maximum: int = 65536)->dict:
    if type(maximum)is not int or not 1<=maximum<=65536:
        raise KnowledgeError('invalid bounded corpus doctor scan')
    db.inspect()
    principal=identity.key()
    with db.snapshot() as conn:
        records=conn.execute('''SELECT doc_id,revision,normalized_sha256,chunks,active,deleted
             FROM ai_kb_documents WHERE principal=? ORDER BY doc_id,revision LIMIT ?''',
             (principal,maximum+1)).fetchall()
        if len(records)>maximum:raise KnowledgeError('corpus document revision budget exhausted')
        active={};chunks=0
        for doc,rev,normalized,expected,enabled,deleted in records:
            if enabled:
                if doc in active or deleted:
                    raise KnowledgeError('multiple active or deleted corpus revisions')
                active[doc]=rev
            chunks+=_reconstruct(conn,principal,doc,rev,normalized,expected,maximum)
            if chunks>maximum:raise KnowledgeError('corpus chunk doctor budget exceeded')
        evts=events.inspect(conn,principal,limit=maximum)
        total=catalog.totals(conn,principal)
        if total['revisions']!=len(records) or total['declared_chunks']!=chunks:
            raise KnowledgeError('corpus materialized inventory diverges')
        # An empty corpus may never have been mutated. Otherwise every
        # revision admission and every live deletion has a witnessed event.
        admissions={(e['doc_id'],e['revision']) for e in evts if e['action']=='ingested'}
        if admissions!={(d,r) for d,r,_,_,_,_ in records}:
            raise KnowledgeError('knowledge revisions do not match admissible event chain')
        forgotten={(e['doc_id'],e['revision']) for e in evts if e['action']=='forgotten'}
        if forgotten!={(d,r) for d,r,_,_,_,deleted in records if deleted}:
            raise KnowledgeError('deleted records lack verified deletion events')
        head=evts[-1]['event_sha256'] if evts else '0'*64
        snapshot={'schema':'skeleton.ai.knowledge-proof.v1','principal':principal,
                  'active_documents':len(active),'revisions':len(records),'chunks':chunks,
                  'mutation_events':len(evts),'event_head_sha256':head}
        return {'status':'source-custody-verified-not-answer-truth','proof':snapshot,
                'proof_sha256':sha256(canonical(snapshot)).hexdigest(),
                'index_status':'FTS5 is query index, not the source-of-truth digest'}
