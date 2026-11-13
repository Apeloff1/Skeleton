"""Authenticated scoped FTS5 retrieval; exact stored excerpts become evidence."""
from __future__ import annotations
from hashlib import sha256
import math
from .contracts import KnowledgeError,KnowledgePolicy,SearchResult
from .query import fts_expression


def search(conn,identity,question: str,*,limit: int,policy:KnowledgePolicy) -> tuple[SearchResult,...]:
    if type(limit) is not int or not 1<=limit<=policy.max_hits:
        raise KnowledgeError('invalid bounded retrieval limit')
    expr = fts_expression(question,policy)
    if not expr:return ()
    # Top K deterministic by bm25 + doc id + chunk index. Explicit principal
    # and live revision join is applied at query time, not in application code.
    rows = conn.execute('''SELECT c.principal,c.doc_id,c.revision,c.ordinal,c.char_start,c.char_end,
      c.passage,c.passage_sha256,c.document_sha256,d.title,d.rights,d.raw_sha256,
      bm25(ai_kb_fts) AS relevance FROM ai_kb_fts
      JOIN ai_kb_chunks c ON c.row_id=ai_kb_fts.rowid
      JOIN ai_kb_documents d ON d.principal=c.principal AND d.doc_id=c.doc_id
           AND d.revision=c.revision
      WHERE ai_kb_fts MATCH ? AND c.principal=? AND d.active=1 AND d.deleted=0
      ORDER BY relevance ASC,c.doc_id ASC,c.ordinal ASC LIMIT ?''',
      (expr,identity.key(),min(policy.max_scan_rows,max(32,limit*16)))).fetchall()
    selected=[];by_document={}
    for (principal,doc,revision,ordinal,start,end,passage,p_sha,d_sha,title,rights,
         stored_doc_sha,rank) in rows:
        if (principal!=identity.key() or d_sha!=stored_doc_sha
            or type(passage) is not str or end-start!=len(passage)
            or sha256(passage.encode('utf8')).hexdigest()!=p_sha
            or type(rank) not in (float,int) or not math.isfinite(rank)):
            raise KnowledgeError('retrieved passage or document authority corrupted')
        if by_document.get(doc,0)>=2:continue
        id_material = f'{principal}:{doc}:{revision}:{ordinal}:{d_sha}'.encode('ascii')
        source_id='kb_'+sha256(id_material).hexdigest()[:48]
        selected.append(SearchResult(source_id,doc,revision,d_sha,title,start,end,
                                      passage,p_sha,rights,float(-rank)))
        by_document[doc]=by_document.get(doc,0)+1
        if len(selected)>=limit:break
    return tuple(selected)
