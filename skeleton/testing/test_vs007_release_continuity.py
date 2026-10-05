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
