"""All-or-nothing source admission with explicit revision CAS and event custody."""
from __future__ import annotations
from hashlib import sha256
from time import time_ns
from .contracts import (KnowledgeError, KnowledgePolicy, document_id, rights_tag,
                        content_type, title_text, DocumentRecord)
from .decode import decode_source
from .chunks import split
from . import catalog, events
from .doctor import _reconstruct
from ...orchestration.execution_spine.principal import admit


def ingest(conn, identity, raw: bytes, *, doc_id: str, title: str,
           rights: str, kind: str, approved: bool, expected_revision: int,
           policy: KnowledgePolicy) -> tuple[DocumentRecord, bool]:
    """Return (record,replayed); caller owns SpineDatabase BEGIN IMMEDIATE."""
    if approved is not True: raise KnowledgeError('document ingestion requires independent explicit approval')
    document_id(doc_id);title_text(title,policy=policy);rights_tag(rights);content_type(kind)
    if type(expected_revision) is not int or expected_revision < 0:
        raise KnowledgeError('expected document revision CAS required')
    if type(raw) is not bytes or not 0 < len(raw) <= policy.max_document_bytes:
        raise KnowledgeError('unbounded or empty source')
    text = decode_source(raw,kind)
    parts = split(text,policy)
    raw_sha = sha256(raw).hexdigest()
    normalized_sha = sha256(text.encode('utf8')).hexdigest()
    principal = admit(conn,identity)
    old = catalog.latest(conn,principal,doc_id)
    current = old.revision if old else 0
    if old and old.active and old.document_sha256 == raw_sha and old.title == title and old.rights == rights and old.content_type == kind:
        if expected_revision not in (old.revision-1,old.revision):
            raise KnowledgeError('idempotent document retry has wrong expected revision')
        # Same revision only if the normalized chunks are demonstrably unchanged.
        stored=conn.execute('SELECT COUNT(*) FROM ai_kb_chunks WHERE principal=? AND doc_id=? AND revision=?',
                            (principal,doc_id,old.revision)).fetchone()[0]
        if stored != len(parts): raise KnowledgeError('idempotent document has missing chunks')
        normalized_expected=conn.execute('SELECT normalized_sha256 FROM ai_kb_documents '
            'WHERE principal=? AND doc_id=? AND revision=?',
            (principal,doc_id,old.revision)).fetchone()[0]
        if normalized_expected!=normalized_sha:
            raise KnowledgeError('idempotent document normalized source digest diverges')
        _reconstruct(conn,principal,doc_id,old.revision,normalized_expected,stored,policy.max_scan_rows)
        events.inspect(conn,principal)
        return old, True
    if expected_revision != current:
        raise KnowledgeError('document revision CAS conflict')
    if current >= policy.max_revisions:
        raise KnowledgeError('revision retention ceiling reached; explicit archival required')
    q=catalog.totals(conn,principal)
    if q['active_documents'] + (0 if old and old.active else 1)>policy.max_documents:
        raise KnowledgeError('active document count exhausted')
    if q['lifetime_bytes'] + len(raw)>policy.max_total_bytes:
        raise KnowledgeError('corpus lifetime byte budget exceeded')
    if q['declared_chunks'] + len(parts)>policy.max_scan_rows:
        raise KnowledgeError('corpus chunk budget exceeded')
    events.inspect(conn,principal)
    if old and old.active:
        old_normalized=conn.execute('SELECT normalized_sha256 FROM ai_kb_documents '
             'WHERE principal=? AND doc_id=? AND revision=?',
             (principal,doc_id,current)).fetchone()[0]
        _reconstruct(conn,principal,doc_id,current,old_normalized,old.chunks,policy.max_scan_rows)
        conn.execute('UPDATE ai_kb_documents SET active=0 WHERE principal=? AND doc_id=? AND revision=? AND active=1',
                     (principal,doc_id,current))
    revision = current + 1
    conn.execute('INSERT INTO ai_kb_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (principal,doc_id,revision,title,rights,kind,raw_sha,normalized_sha,len(raw),
         len(text.encode('utf8')),len(parts),1,0,time_ns()))
    for part in parts:
        conn.execute('''INSERT INTO ai_kb_chunks
           (principal,doc_id,revision,ordinal,char_start,char_end,passage,passage_sha256,document_sha256)
           VALUES(?,?,?,?,?,?,?,?,?)''',
           (principal,doc_id,revision,part.index,part.start,part.end,part.passage,part.digest,raw_sha))
    events.append(conn,principal,action='ingested',doc_id=doc_id,revision=revision,
                  raw_sha256=raw_sha,normalized_sha256=normalized_sha,chunks=len(parts))
    return catalog.latest(conn,principal,doc_id),False


def forget(conn, identity, *, doc_id: str, expected_revision: int,
           approved: bool) -> bool:
    if approved is not True:raise KnowledgeError('deletion requires independent operator approval')
    document_id(doc_id)
    if type(expected_revision) is not int or expected_revision < 1:
        raise KnowledgeError('deletion requires expected revision')
    principal = identity.key()
    row = catalog.latest(conn,principal,doc_id)
    if row is None:raise KnowledgeError('unknown source cannot be deleted')
    if row.revision != expected_revision:
        raise KnowledgeError('document deletion revision CAS mismatch')
    if not row.active:return False
    events.inspect(conn,principal)
    normalized=conn.execute('SELECT normalized_sha256 FROM ai_kb_documents '
                            'WHERE principal=? AND doc_id=? AND revision=?',
                            (principal,doc_id,row.revision)).fetchone()[0]
    _reconstruct(conn,principal,doc_id,row.revision,normalized,row.chunks,65536)
    changed = conn.execute('UPDATE ai_kb_documents SET active=0,deleted=1 '
                           'WHERE principal=? AND doc_id=? AND revision=? AND active=1',
                           (principal,doc_id,row.revision))
    if changed.rowcount != 1:raise KnowledgeError('document deletion lost CAS')
    # No implicit physical erasure: receipts and archived chunks are retained
    # for chain review. Retrieval excludes all inactive versions by design.
    events.append(conn,principal,action='forgotten',doc_id=doc_id,revision=row.revision,
                  raw_sha256=row.document_sha256,normalized_sha256='0'*64,chunks=row.chunks)
    return True
