"""Non-destructive recovery from explicitly selected historical Chroma bytes."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from scripts import stage_chroma_recovery as r
from scripts import chroma_backup as b

pytestmark=pytest.mark.skipif(os.name!="posix",reason="POSIX descriptor custody")


def fixture(tmp_path,*,journal=False):
    backup=tmp_path/"backup"
    backup.mkdir(mode=0o700)
    parent=tmp_path/"private-stage"
    parent.mkdir(mode=0o700)
    for i,lane in enumerate(r._LANES):
        store=backup/lane
        store.mkdir()
        conn=sqlite3.connect(store/"chroma.sqlite3")
        for name in sorted(r._REQUIRED_TABLES):
            conn.execute(f"CREATE TABLE {name}(id INTEGER PRIMARY KEY)")
            for n in range(i+1):
                conn.execute(f"INSERT INTO {name} VALUES (?)",(n,))
        conn.commit()
        conn.close()
        (store/"index").mkdir()
        (store/"index"/"segment.bin").write_bytes(bytes([i])*4096)
    if journal:
        (backup/"container-data"/"chroma.sqlite3-wal").write_bytes(b"unresolved WAL")
    manifest={"schema":b.SCHEMA,"source_was_stopped":True,"migration_complete":False,
              "release_accepted":False,"files":b._manifest_files(backup)}
    (backup/"manifest.json").write_bytes(r.canonical(manifest))
    return backup,parent,manifest


def approval(backup,manifest,*,lane="container-data",**updates):
    now=int(time.time())
    fields=dict(authority_id="reviewer",deployment_id="test",source_head="a"*40,
                backup_manifest_sha256=r.sha((backup/"manifest.json").read_bytes()),
                selected_lane=lane,selected_inventory_sha256=r.lane_sha(r.lane_inventory(manifest,lane)),
                selection_review_sha256="b"*64,quiescence_review_sha256="c"*64,
                issued_at=now-1,expires_at=now+120)
    fields.update(updates)
    plan=r.StageApproval(**fields)
    key=Ed25519PrivateKey.generate()
    return r.VerifiedStageApproval(plan,key.sign(plan.canonical_bytes()),"reviewer","test","a"*40,
        key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))


def test_stage_preserves_both_sources_and_never_copies_unselected_store(tmp_path,monkeypatch):
    backup,parent,manifest=fixture(tmp_path)
    monkeypatch.setattr(r,"_assert_head",lambda h:None)
    original=b._manifest_files(backup)
    result=r.stage_recovery(backup,parent/"new",approval(backup,manifest,lane="legacy-volume"))
    assert result["integrity"]["row_counts"]==dict.fromkeys(r._REQUIRED_TABLES,2)
    assert result["integrity"]["vector_graph_integrity_verified"] is False
    assert result["migration_complete"] is False and result["live_store_modified"] is False
    assert b._manifest_files(backup)==original
    assert b._manifest_files(parent/"new"/"data")==r.lane_inventory(manifest,"legacy-volume")
    assert not (parent/"new"/"container-data").exists()
    assert json.loads((parent/"new"/"receipt.json").read_bytes())==result
    with pytest.raises(r.RecoveryDenied):
        r.stage_recovery(backup,parent/"new",approval(backup,manifest))


def test_candidate_inspection_never_infers_authority(tmp_path):
    backup,_,manifest=fixture(tmp_path)
    result=r.inspect_backup_candidates(backup)
    assert result["selection_authorized"] is False and result["database_integrity_verified"] is False
    assert result["lanes"]["legacy-volume"]["inventory_sha256"]==r.lane_sha(r.lane_inventory(manifest,"legacy-volume"))
    assert result["lanes"]["legacy-volume"]["inventory_sha256"]!=result["lanes"]["container-data"]["inventory_sha256"]


def test_unresolved_journal_is_held_without_altering_sources(tmp_path):
    backup,_,manifest=fixture(tmp_path,journal=True)
    before=b._manifest_files(backup)
    result=r.inspect_backup_candidates(backup)
    assert result["lanes"]["container-data"]=={"eligible_for_review":False}
    assert result["lanes"]["legacy-volume"]["eligible_for_review"] is True
    with pytest.raises(r.RecoveryDenied):
        r.lane_inventory(manifest,"container-data")
    assert b._manifest_files(backup)==before


@pytest.mark.parametrize("path",["../escape","container-data/../escape","/absolute",
    "container-data//x","container-data/a\\b","other/surprise","container-data","container-data/\x00bad"])
def test_unsafe_manifest_paths_denied(tmp_path,path):
    _,_,manifest=fixture(tmp_path)
    manifest["files"].append({"path":path,"bytes":1,"sha256":"1"*64})
    with pytest.raises(r.RecoveryDenied):
        r.lane_inventory(manifest,"container-data")


@pytest.mark.parametrize("fault",["wrong_manifest","wrong_lane_pin","invalid_sig","stale_approval","source_changed","private_parent"])
def test_recovery_denial_never_publishes_or_mutates_original(tmp_path,monkeypatch,fault):
    backup,parent,manifest=fixture(tmp_path)
    monkeypatch.setattr(r,"_assert_head",lambda h:None)
    updates={}
    if fault=="wrong_manifest": updates["backup_manifest_sha256"]="8"*64
    elif fault=="wrong_lane_pin": updates["selected_inventory_sha256"]="9"*64
    elif fault=="stale_approval":
        now=int(time.time())
        updates.update(issued_at=now-100,expires_at=now-1)
    if fault=="stale_approval":
        with pytest.raises(r.RecoveryDenied):
            approval(backup,manifest,**updates)
        return
    auth=approval(backup,manifest,**updates)
    if fault=="invalid_sig":
        with pytest.raises(r.RecoveryDenied):
            replace(auth,signature=b"x"*64)
        return
    if fault=="source_changed":
        (backup/"container-data"/"index"/"segment.bin").write_bytes(b"changed")
    if fault=="private_parent":
        parent.chmod(0o755)
    before=b._manifest_files(backup)
    with pytest.raises((r.RecoveryDenied,b.BackupRejected)):
        r.stage_recovery(backup,parent/"new",auth)
    assert not (parent/"new").exists()
    assert b._manifest_files(backup)==before


def test_private_stage_sqlite_invalid_or_wrong_schema_is_held(tmp_path):
    invalid=tmp_path/"invalid.sqlite3"
    invalid.write_bytes(b"not SQLite")
    with pytest.raises(r.RecoveryDenied):
        r.sqlite_integrity(invalid)
    empty=tmp_path/"empty.sqlite3"
    conn=sqlite3.connect(empty)
    conn.execute("CREATE TABLE unrelated(id)")
    conn.commit()
    conn.close()
    with pytest.raises(r.RecoveryDenied):
        r.sqlite_integrity(empty)


def test_same_bytes_replaced_with_symlink_not_accepted(tmp_path,monkeypatch):
    backup,parent,manifest=fixture(tmp_path)
    auth=approval(backup,manifest)
    monkeypatch.setattr(r,"_assert_head",lambda h:None)
    source=backup/"container-data"/"index"/"segment.bin"
    target=tmp_path/"outside.bin"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    with pytest.raises((r.RecoveryDenied,b.BackupRejected,OSError)):
        r.stage_recovery(backup,parent/"new",auth)
    assert not (parent/"new").exists() and target.read_bytes()==bytes(4096)


def test_stage_verifier_rejects_duplicate_signed_plan_keys(tmp_path):
    backup,_,manifest=fixture(tmp_path)
    auth=approval(backup,manifest)
    raw=r.canonical({f.name:getattr(auth.plan,f.name) for f in r.fields(auth.plan)})
    assert r.StageApproval.parse(raw)==auth.plan
    with pytest.raises(r.RecoveryDenied):
        r.StageApproval.parse(raw[:-1]+b',"authority_id":"other"}')


def test_no_replace_publication_preserves_concurrent_destination(tmp_path,monkeypatch):
    backup,parent,manifest=fixture(tmp_path)
    monkeypatch.setattr(r,"_assert_head",lambda h:None)
    actual=r._publish_no_replace
    def competing(source,destination):
        destination.mkdir()
        (destination/"sentinel").write_text("existing")
        actual(source,destination)
    monkeypatch.setattr(r,"_publish_no_replace",competing)
    with pytest.raises(b.BackupRejected):
        r.stage_recovery(backup,parent/"new",approval(backup,manifest))
    assert (parent/"new"/"sentinel").read_text()=="existing"
