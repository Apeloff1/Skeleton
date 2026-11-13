"""Bounded inventory and revision introspection without private passage text."""
from __future__ import annotations
from .contracts import DocumentRecord, KnowledgeError, document_id

FIELDS = ('doc_id','revision','raw_sha256','raw_bytes','chunks','title','rights','active','content_type')


def record(row) -> DocumentRecord:
    return DocumentRecord(row[0],row[1],row[2],row[3],row[4],row[5],row[6],bool(row[7]),row[8])


def latest(conn, principal: str, doc_id: str) -> DocumentRecord | None:
    document_id(doc_id)
    row = conn.execute('SELECT ' + ','.join(FIELDS) + ' FROM ai_kb_documents '
                       'WHERE principal=? AND doc_id=? ORDER BY revision DESC LIMIT 1',
                       (principal,doc_id)).fetchone()
    return record(row) if row else None


def list_documents(conn, principal: str, *, limit: int = 128,
                   include_inactive: bool = False) -> tuple[DocumentRecord, ...]:
    if type(limit) is not int or not 1 <= limit <= 4096:
        raise KnowledgeError('invalid finite document listing ceiling')
    where = '' if include_inactive else ' AND active=1'
    rows = conn.execute('SELECT ' + ','.join('d.'+name for name in FIELDS)
                       + ' FROM ai_kb_documents d WHERE principal=?' + where
                       + ' AND d.revision=(SELECT MAX(revision) FROM ai_kb_documents x '
                         'WHERE x.principal=d.principal AND x.doc_id=d.doc_id) '
                         'ORDER BY d.doc_id LIMIT ?', (principal,limit+1)).fetchall()
    if len(rows)>limit:
        raise KnowledgeError('document listing exceeds operator bound')
    return tuple(map(record,rows))


def totals(conn, principal: str) -> dict:
    docs = conn.execute('SELECT COUNT(*),COALESCE(SUM(raw_bytes),0),'
                        'COALESCE(SUM(chunks),0) FROM ai_kb_documents WHERE principal=?',
                        (principal,)).fetchone()
    active = conn.execute('SELECT COUNT(*) FROM ai_kb_documents WHERE principal=? AND active=1',
                          (principal,)).fetchone()[0]
    return {'revisions':docs[0], 'lifetime_bytes':docs[1],
            'declared_chunks':docs[2], 'active_documents':active}
