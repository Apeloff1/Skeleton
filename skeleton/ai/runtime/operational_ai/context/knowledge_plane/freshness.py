"""Exact source revision/CAS validation within the final inference commit.

A document can be revoked while the model spends CPU. The final authoritative
inference transaction must not commit the generated answer as grounded in a
source that no longer exists or is no longer independently approved.
"""
from __future__ import annotations
from hashlib import sha256
from .contracts import KnowledgeError,KnowledgePolicy
from ...orchestration.execution_spine.contracts import hexdigest


def require_current(conn, identity, sources: tuple[dict,...],
                    *, policy: KnowledgePolicy) -> None:
    if not isinstance(sources,tuple) or len(sources)>policy.max_hits:
        raise KnowledgeError('source-commit provenance span is unbounded')
    principal=identity.key()
    seen=set()
    for source in sources:
        if not isinstance(source,dict) or not {
            'source_id','revision','sha256','document_sha256','char_start','char_end',
        }.issubset(source):
            raise KnowledgeError('inference source receipt has missing custody fields')
        sid=source['source_id'];revision=source['revision']
        if (type(sid)is not str or len(sid)>128 or not sid.startswith('kb_')
            or sid in seen or type(revision)is not int or revision<1):
            raise KnowledgeError('source identity malformed or repeated')
        seen.add(sid)
        hexdigest(source['sha256'],'source digest')
        hexdigest(source['document_sha256'],'document digest')
        rows=conn.execute('''SELECT c.doc_id,c.ordinal,c.char_start,c.char_end,c.passage,
                c.passage_sha256,c.document_sha256,d.raw_sha256
                FROM ai_kb_chunks c JOIN ai_kb_documents d
                  ON d.principal=c.principal AND d.doc_id=c.doc_id AND d.revision=c.revision
                WHERE c.principal=? AND c.revision=? AND c.passage_sha256=?
                  AND c.document_sha256=? AND d.active=1 AND d.deleted=0
                  LIMIT 64''',
                  (principal,revision,source['sha256'],source['document_sha256'])).fetchall()
        if len(rows)>=64:raise KnowledgeError('ambiguous source proof exceeds bounded lookup')
        valid=0
        for doc,ordinal,start,end,passage,p_sha,d_sha,raw_sha in rows:
            expected='kb_'+sha256(f'{principal}:{doc}:{revision}:{ordinal}:{d_sha}'.encode('ascii')).hexdigest()[:48]
            if expected != sid:continue
            if (start!=source['char_start'] or end!=source['char_end']
                or raw_sha!=source['document_sha256'] or
                sha256(passage.encode('utf8')).hexdigest()!=p_sha):
                raise KnowledgeError('inference source mutated since context compilation')
            valid+=1
        if valid!=1:
            raise KnowledgeError('approved source revision expired before inference commit')
