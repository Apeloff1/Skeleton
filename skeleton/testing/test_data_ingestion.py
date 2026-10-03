import hashlib,pytest
from skeleton.data.ingestion import *
def _j(p,**kw):
 d=dict(job_id="j",source_id="s",source_digest=hashlib.sha256(p).hexdigest(),acquired_at_ns=1,rights="licensed",classification="internal",parser_version="v1",trusted_source=True); d.update(kw); return IngestionJob(**d)
def test_idempotent_identity_and_quarantine():
 e=IngestionEngine(); p=b"x"; a=e.ingest(_j(p),p,parser=lambda _:{"x":1}); b=e.ingest(_j(p),p,parser=lambda _:{"x":2}); assert a==b and isinstance(a,IngestedRecord)
 assert isinstance(IngestionEngine().ingest(_j(p,trusted_source=False),p,parser=lambda _:{"x":1}),QuarantineRecord)
def test_job_rebind_fails():
 e=IngestionEngine(); e.ingest(_j(b"a"),b"a",parser=lambda _:{"x":1})
 with pytest.raises(IngestionError): e.ingest(_j(b"b"),b"b",parser=lambda _:{"x":2})
