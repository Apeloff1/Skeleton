from datetime import datetime, timezone
import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.persistence.memory_repository import MemoryConflict, SQLiteMemoryRepository
from skeleton.persistence.memory_version_governance import export_history, governed_rollback

NOW=datetime(2026,10,6,tzinfo=timezone.utc)

def proposal(key,content,target=None,version=None):
    return MemoryWriteProposal(tenant_id="t",namespace="n",subject_id="s",kind=MemoryKind.SEMANTIC,idempotency_key=key,content=content,provenance_refs=("source:x",),target_memory_id=target,expected_version=version,data_class="internal")

def seeded():
    r=SQLiteMemoryRepository()
    a=r.write(proposal("a","v1"),now=NOW)
    b=r.write(proposal("b","v2",a.memory_id,1),now=NOW)
    return r,a,b

def test_export_is_contiguous_and_deterministic():
    r,a,_=seeded()
    x=export_history(r,a.memory_id,tenant_id="t",namespace="n")
    y=export_history(r,a.memory_id,tenant_id="t",namespace="n")
    assert x==y and x.head_version==2 and len(x.revision_digests)==2

def test_rollback_appends_revision_and_preserves_evidence():
    r,a,_=seeded()
    rolled=governed_rollback(r,a.memory_id,tenant_id="t",namespace="n",target_version=1,expected_head_version=2,evidence_ref="approval:7",operation_id="op-7",now=NOW)
    assert rolled.version==3 and rolled.content=="v1"
    assert "approval:7" in rolled.provenance_refs
    assert "rollback-from:2" in rolled.provenance_refs
    assert len(r.history(a.memory_id,tenant_id="t",namespace="n"))==3

def test_stale_head_fails_closed():
    r,a,_=seeded()
    with pytest.raises(MemoryConflict,match="head"):
        governed_rollback(r,a.memory_id,tenant_id="t",namespace="n",target_version=1,expected_head_version=1,evidence_ref="approval:7",operation_id="op-7")

def test_tombstone_cannot_be_resurrected():
    r,a,b=seeded(); r.tombstone(a.memory_id,tenant_id="t",namespace="n",expected_version=b.version,now=NOW)
    with pytest.raises(MemoryConflict,match="resurrect"):
        governed_rollback(r,a.memory_id,tenant_id="t",namespace="n",target_version=1,expected_head_version=3,evidence_ref="approval:7",operation_id="op-7")
