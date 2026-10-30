import hashlib
import pytest
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_streaming_blob_is_content_addressed_across_reopen(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    spool=ArtifactSpool(root,authorized=True)
    chunks=[b"abcd",b"5678"*1000,b"tail"]
    known=hashlib.sha256(b"".join(chunks)).hexdigest()
    receipt=spool.ingest(iter(chunks),expected_sha256=known,authorized=True)
    assert receipt["sha256"]==known
    assert receipt["bytes"]==len(b"".join(chunks))
    assert spool.verify(known)==receipt["bytes"]
    assert spool.read_window(known,offset=4,length=8,memory_budget_bytes=16,
                             authorized=True)==b"56785678"
    assert ArtifactSpool(root,authorized=True).verify(known)==receipt["bytes"]
    assert not receipt["rights_verified"]

def test_spool_fails_closed_on_tampering_and_budget(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    spool=ArtifactSpool(root,authorized=True)
    with pytest.raises(StudioQuestError):
        spool.ingest([b"wrong"],expected_sha256="a"*64,authorized=True)
    assert not list(spool.path.glob(".staging-*"))
    receipt=spool.ingest([b"hello"],authorized=True)
    target=spool.path/receipt["sha256"]
    target.write_bytes(b"tampered")
    with pytest.raises(StudioQuestError):
        spool.verify(receipt["sha256"])
    with pytest.raises(StudioQuestError):
        spool.read_window(receipt["sha256"],offset=0,length=1,
                          memory_budget_bytes=0,authorized=True)
    with pytest.raises(PermissionError):
        spool.ingest([b"data"],authorized=False)
