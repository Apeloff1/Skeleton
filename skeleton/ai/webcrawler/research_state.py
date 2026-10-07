"""Durable research assurance state backed by crawler SQLite."""
from __future__ import annotations
from dataclasses import asdict
import json
from .temporal_retrieval import TemporalFragment
from .evidence_revision import RevisionReceipt
from .source_quality import SourcePosterior
class ResearchStateStore:
 def __init__(self,db):self.db=db
 def put_temporal(self,row:TemporalFragment):
  raw=json.dumps(asdict(row),sort_keys=True,separators=(",",":"))
  with self.db:self.db.execute("INSERT INTO temporal_fragments VALUES(?,?) ON CONFLICT(fragment_id) DO UPDATE SET payload=excluded.payload",(row.fragment_id,raw))
 def get_temporal(self,fragment_id):
  r=self.db.execute("SELECT payload FROM temporal_fragments WHERE fragment_id=?",(fragment_id,)).fetchone()
  return TemporalFragment(**json.loads(r[0])) if r else None
 def put_revision(self,row:RevisionReceipt):
  raw=json.dumps(asdict(row),sort_keys=True,separators=(",",":"))
  with self.db:self.db.execute("INSERT OR IGNORE INTO evidence_revisions VALUES(?,?)",(row.revision_id,raw))
  prior=self.db.execute("SELECT payload FROM evidence_revisions WHERE revision_id=?",(row.revision_id,)).fetchone()[0]
  if prior!=raw:raise ValueError("revision id collision")
 def put_source_quality(self,row:SourcePosterior):
  with self.db:self.db.execute("INSERT INTO source_quality VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET alpha=excluded.alpha,beta=excluded.beta",(row.source,row.alpha,row.beta))
 def get_source_quality(self,source):
  r=self.db.execute("SELECT alpha,beta FROM source_quality WHERE source=?",(source,)).fetchone()
  return SourcePosterior(source,*r) if r else None
