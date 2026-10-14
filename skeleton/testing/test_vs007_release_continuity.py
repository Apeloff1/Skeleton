from __future__ import annotations
import hashlib,pytest
from skeleton.app.desktop_release import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def rel(i="RELEASE.V1",schema=1):return SignedDesktopRelease(i,S(i),S("sig:"+i),"SIGNER.RELEASE",schema)
def receipt():return DesktopArtifactReceipt("RELEASE.V1",S("state-v1"),S("artifact"),1)
def acceptance(i="RELEASE.V2"):return DesktopAcceptanceRun("RUN.1",i,S("env"),S("vs001"),S("artifact"))
def test_update_requires_migration_before_commit():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2))
 with pytest.raises(DesktopReleaseError,match="migration not complete"):t.commit(acceptance())
def test_acceptance_must_target_exact_release():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2));t.migrate(S("state-v2"))
 with pytest.raises(DesktopReleaseError,match="wrong release"):t.commit(acceptance("RELEASE.V3"))
def test_clean_update_preserves_governed_receipt_identity():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2));t.migrate(S("state-v2"));r=t.commit(acceptance());assert r.release_id=="RELEASE.V2" and r.schema_version==2
def test_interrupted_migration_requires_rollback():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2));t.migrate(S("partial"));assert t.interrupt()=="rollback_required"
def test_rollback_restores_exact_preupdate_authoritative_state():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2));t.migrate(S("partial"));e=t.rollback(S("rollback-artifact"));assert e.preupdate_state_digest==e.restored_state_digest==S("state-v1");assert t.receipt.release_id=="RELEASE.V1"
def test_release_and_receipt_schema_must_match():
 with pytest.raises(DesktopReleaseError,match="mismatch"):DesktopUpdateTransaction(rel(schema=2),receipt())
def test_same_release_cannot_be_update_target():
 t=DesktopUpdateTransaction(rel(),receipt())
 with pytest.raises(DesktopReleaseError,match="differ"):t.stage(rel())

def test_schema_versions_reject_boolean_aliases():
 with pytest.raises(DesktopReleaseError,match="schema_version"):rel(schema=True)
 with pytest.raises(DesktopReleaseError,match="schema_version"):DesktopArtifactReceipt("RELEASE.V1",S("state"),S("artifact"),True)
def test_acceptance_artifact_must_match_signed_target():
 t=DesktopUpdateTransaction(rel(),receipt());target=rel("RELEASE.V2",2);t.stage(target);t.migrate(S("state-v2"))
 bad=DesktopAcceptanceRun("RUN.1",target.release_id,S("env"),S("vs001"),S("wrong"))
 with pytest.raises(DesktopReleaseError,match="signed target"):t.commit(bad)
def test_parallel_update_cannot_replace_staged_target():
 t=DesktopUpdateTransaction(rel(),receipt());t.stage(rel("RELEASE.V2",2))
 with pytest.raises(DesktopReleaseError,match="already in progress"):t.stage(rel("RELEASE.V3",3))

def test_migration_receipt_moves_to_signed_target_artifact():
 t=DesktopUpdateTransaction(rel(),receipt());target=rel("RELEASE.V2",2);t.stage(target);t.migrate(S("state-v2"))
 assert t.receipt.artifact_digest==target.artifact_digest
def test_rollback_restores_entire_preupdate_receipt():
 original=receipt();t=DesktopUpdateTransaction(rel(),original);t.stage(rel("RELEASE.V2",2));t.migrate(S("partial"))
 t.rollback(S("rollback-artifact"));assert t.receipt==original
def test_rollback_after_commit_is_forbidden():
 t=DesktopUpdateTransaction(rel(),receipt());target=rel("RELEASE.V2",2);t.stage(target);t.migrate(S("state-v2"))
 good=DesktopAcceptanceRun("RUN.1",target.release_id,S("env"),S("vs001"),target.artifact_digest);t.commit(good)
 with pytest.raises(DesktopReleaseError,match="rollback-eligible"):t.rollback(S("rollback"))
def test_second_update_starts_from_committed_release():
 t=DesktopUpdateTransaction(rel(),receipt());v2=rel("RELEASE.V2",2);t.stage(v2);t.migrate(S("state-v2"))
 t.commit(DesktopAcceptanceRun("RUN.1",v2.release_id,S("env"),S("vs001"),v2.artifact_digest))
 t.stage(rel("RELEASE.V3",3));assert t.preupdate_receipt.release_id=="RELEASE.V2"
