"""Durable content-addressed crawler storage using only the Python standard library."""
from __future__ import annotations
import json, os, sqlite3, tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Mapping
from .core import CrawlDocument\nfrom .migrations import migrate

class SqliteCrawlStore:
    def __init__(self,path:str|Path):
        self.path=str(path)
        self.db=sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS documents(
          content_hash TEXT PRIMARY KEY, canonical_url TEXT NOT NULL, fetched_url TEXT NOT NULL,
          title TEXT NOT NULL, text TEXT NOT NULL, content_type TEXT NOT NULL,
          fetched_at REAL NOT NULL, source_score REAL NOT NULL, provenance TEXT NOT NULL, links TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS urls(
          canonical_url TEXT PRIMARY KEY, content_hash TEXT NOT NULL REFERENCES documents(content_hash));
        CREATE TABLE IF NOT EXISTS checkpoints(
          key TEXT PRIMARY KEY, state TEXT NOT NULL);
        """)
        self.db.commit()\n        migrate(self.db)
    def close(self): self.db.close()
    def has_url(self,url:str)->bool:
        return self.db.execute("SELECT 1 FROM urls WHERE canonical_url=?",(url,)).fetchone() is not None
    def has_content(self,digest:str)->bool:
        return self.db.execute("SELECT 1 FROM documents WHERE content_hash=?",(digest,)).fetchone() is not None
    def put(self,doc:CrawlDocument)->bool:
        novel=not self.has_content(doc.content_hash)
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)""",(
                doc.content_hash,doc.canonical_url,doc.fetched_url,doc.title,doc.text,doc.content_type,
                doc.fetched_at,doc.source_score,json.dumps(dict(doc.provenance),sort_keys=True),
                json.dumps(list(doc.links))))
            self.db.execute("""INSERT INTO urls VALUES(?,?) ON CONFLICT(canonical_url)
              DO UPDATE SET content_hash=excluded.content_hash""",(doc.canonical_url,doc.content_hash))
        return novel
    def get(self,digest:str)->CrawlDocument|None:
        r=self.db.execute("SELECT canonical_url,fetched_url,title,text,content_type,content_hash,fetched_at,source_score,provenance,links FROM documents WHERE content_hash=?",(digest,)).fetchone()
        if not r:return None
        return CrawlDocument(*r[:8],json.loads(r[8]),tuple(json.loads(r[9])))
    def iter_documents(self):
        for (digest,) in self.db.execute("SELECT content_hash FROM documents ORDER BY canonical_url"):
            yield self.get(digest)
    def save_checkpoint(self,key:str,state:Mapping[str,object])->None:
        raw=json.dumps(state,sort_keys=True,separators=(",",":"))
        with self.db:self.db.execute("""INSERT INTO checkpoints VALUES(?,?) ON CONFLICT(key)
          DO UPDATE SET state=excluded.state""",(key,raw))
    def load_checkpoint(self,key:str):
        r=self.db.execute("SELECT state FROM checkpoints WHERE key=?",(key,)).fetchone()
        return json.loads(r[0]) if r else None
