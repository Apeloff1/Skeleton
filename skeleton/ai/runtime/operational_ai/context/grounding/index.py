"""Independent, scoped local FTS5 index; indexed passages are derived from authoritative source bytes."""
from __future__ import annotations
import sqlite3,threading
from .documents import Document,Passage,GroundingError,check_id
from .chunking import segment
from .query import escaped_fts_query

class GroundingIndex:
    def __init__(self,path:str=':memory:'):
        self._lock=threading.RLock()
        self._db=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.execute('''CREATE TABLE IF NOT EXISTS docs (
            tenant TEXT NOT NULL,user TEXT NOT NULL,doc_id TEXT NOT NULL,
            revision INTEGER NOT NULL, origin TEXT NOT NULL,rights TEXT NOT NULL,trust TEXT NOT NULL,
            sha256 TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(tenant,user,doc_id))''')
        self._db.execute('''CREATE TABLE IF NOT EXISTS passages (
            tenant TEXT NOT NULL,user TEXT NOT NULL,doc_id TEXT NOT NULL,chunk_id TEXT NOT NULL,
            revision INTEGER NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,
            sha256 TEXT NOT NULL,trust TEXT NOT NULL,body TEXT NOT NULL,
            PRIMARY KEY(tenant,user,chunk_id),
            FOREIGN KEY (tenant,user,doc_id) REFERENCES docs ON DELETE CASCADE)''')
        self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(body, content='passages', content_rowid='rowid')")
        for key,kind in (('ai_fts_ai','ai'),):pass
        # Contentless triggers update on the same transaction boundary as source custody.
        self._db.executescript('''
            CREATE TRIGGER IF NOT EXISTS pf_insert AFTER INSERT ON passages BEGIN
              INSERT INTO passages_fts(rowid,body) VALUES(new.rowid,new.body); END;
            CREATE TRIGGER IF NOT EXISTS pf_delete AFTER DELETE ON passages BEGIN
              INSERT INTO passages_fts(passages_fts,rowid,body) VALUES('delete',old.rowid,old.body); END;
            CREATE TRIGGER IF NOT EXISTS pf_update AFTER UPDATE ON passages BEGIN
              INSERT INTO passages_fts(passages_fts,rowid,body) VALUES('delete',old.rowid,old.body);
              INSERT INTO passages_fts(rowid,body) VALUES(new.rowid,new.body); END;
        ''')

    def admit(self,doc:Document)->int:
        chunks=segment(doc)
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                old=self._db.execute('SELECT revision FROM docs WHERE tenant=? AND user=? AND doc_id=?',
                    (doc.tenant,doc.user,doc.doc_id)).fetchone()
                if old and old[0]>=doc.revision:raise GroundingError('stale document revision')
                self._db.execute('DELETE FROM docs WHERE tenant=? AND user=? AND doc_id=?',
                    (doc.tenant,doc.user,doc.doc_id))
                self._db.execute('INSERT INTO docs VALUES (?,?,?,?,?,?,?,?,?)',
                    (doc.tenant,doc.user,doc.doc_id,doc.revision,doc.origin,doc.rights,doc.trust,doc.sha256,doc.text))
                for passage in chunks:
                    self._db.execute('INSERT INTO passages VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (doc.tenant,doc.user,passage.doc_id,passage.chunk_id,passage.revision,
                         passage.start,passage.end,passage.sha256,passage.trust,passage.body))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK');raise
        return len(chunks)

    def retrieve(self,tenant:str,user:str,query:str,*,limit:int=8)->tuple[tuple[Passage,float],...]:
        check_id(tenant,'tenant');check_id(user,'user')
        if type(limit) is not int or not 1<=limit<=64:raise GroundingError('query limit out of range')
        q=escaped_fts_query(query)
        if not q:return ()
        with self._lock:
            rows=self._db.execute('''SELECT p.doc_id,p.chunk_id,p.start,p.end,p.body,p.sha256,p.revision,p.trust,
                   bm25(passages_fts) FROM passages_fts JOIN passages p ON p.rowid=passages_fts.rowid
                   WHERE passages_fts MATCH ? AND p.tenant=? AND p.user=?
                   ORDER BY bm25(passages_fts),p.chunk_id LIMIT ?''',(q,tenant,user,limit)).fetchall()
        return tuple((Passage(*row[:8]),float(row[8])) for row in rows)

    def verify(self,tenant:str,user:str,passage:Passage)->bool:
        check_id(tenant,'tenant');check_id(user,'user')
        with self._lock:
            doc=self._db.execute('SELECT body,sha256,revision FROM docs WHERE tenant=? AND user=? AND doc_id=?',
                (tenant,user,passage.doc_id)).fetchone()
            row=self._db.execute('SELECT start,end,body FROM passages WHERE tenant=? AND user=? AND chunk_id=?',
                (tenant,user,passage.chunk_id)).fetchone()
        return bool(doc and row and doc[1]==passage.sha256 and doc[2]==passage.revision
                    and row==(passage.start,passage.end,passage.body)
                    and doc[0][passage.start:passage.end]==passage.body)

    def forget(self,tenant:str,user:str,doc_id:str)->bool:
        check_id(tenant,'tenant');check_id(user,'user');check_id(doc_id,'document')
        with self._lock:
            return self._db.execute('DELETE FROM docs WHERE tenant=? AND user=? AND doc_id=?',(tenant,user,doc_id)).rowcount==1

    def close(self):
        with self._lock:self._db.close()
