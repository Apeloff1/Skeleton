import os
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool

def test_spool_finalizes_private_single_link_object(tmp_path):
    root=tmp_path/"owner"
    root.mkdir(mode=0o700)
    store=ArtifactSpool(root,authorized=True)
    saved=store.ingest([b"production-source",b"-v2"],authorized=True)
    obj=store.path/saved["sha256"]
    assert obj.stat().st_nlink==1
    assert store.verify(saved["sha256"])==saved["bytes"]
    assert not list(store.path.glob(".staging-*"))
    if os.name=="posix":
        assert obj.stat().st_mode & 0o077==0
