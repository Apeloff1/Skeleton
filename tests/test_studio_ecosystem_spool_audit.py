from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_spool_audit import audit_artifact_spool

def test_spool_scan_reports_incomplete_without_deletion(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    spool=ArtifactSpool(root,authorized=True)
    good=spool.ingest([b"one"],authorized=True)
    (spool.path/".staging-after-crash").write_bytes(b"staged")
    report=audit_artifact_spool(spool,authorized=True)
    assert report["valid_artifacts"]==1
    assert report["incomplete_staging_files"]==1
    assert report["local_content_consistent"] is False
    assert report["files_deleted"]==0
    assert spool.verify(good["sha256"])==3
