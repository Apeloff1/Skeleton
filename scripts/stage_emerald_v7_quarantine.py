"""Stage exact remotely reassembled Emerald V7 models for review, never runtime.

The active Emerald public/native v1 pin and original Hoarder remain untouched.
A source receipt is checked for consistency but this command is NOT a fresh
remote Git check. Even successfully staged originals are quarantined.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

import publish_emerald_v7_orbit02 as publication
import verify_emerald_v7_remote_original as remote
from emerald_v7_model_pins import DONOR, require

ROOT=Path(__file__).resolve().parents[1]
SOURCE_RECEIPT="remote-git-original-custody.json"
STAGING_RECEIPT="v7-quarantine-receipt.json"
SCHEMA="skeleton.emerald.v7.quarantined-two-model-inspection.v1"
MAX_RECEIPT=256*1024
CHUNK=4*1024**2

def trusted_dir(path):
    path=Path(path)
    return path.is_dir() and not path.is_symlink()

def outside_worktree(path):
    # Resolve every ancestor so ../ and linked parent directories cannot
    # redirect an otherwise external-looking destination into the app.
    path=Path(path).resolve(strict=False)
    require(not path.is_relative_to(ROOT.resolve()),
            "refuse to write V7 review originals into application source, active assets, or native install")
    return path

def source_receipt(root,forms):
    root=Path(root)
    require(trusted_dir(root),
            "original source delivery must be an ordinary directory")
    manifest=root/SOURCE_RECEIPT
    require(manifest.is_file() and not manifest.is_symlink()
            and 0<manifest.stat().st_size<=MAX_RECEIPT,
            "missing bounded independent original remote Git receipt")
    actual={x.name for x in root.iterdir()}
    require(actual=={SOURCE_RECEIPT,"pathfinder.glb","archivist.glb"}
            and all(not x.is_symlink() for x in root.iterdir()),
            "unknown, linked or missing original delivered model")
    evidence=json.loads(manifest.read_bytes())
    require(evidence.get("schema")==remote.RECEIPT_SCHEMA
            and evidence.get("original_donor_sha256")==DONOR
            and evidence.get("remote_repository")=="Apeloff1/Skeleton"
            and evidence.get("original_model_count")==2
            and evidence.get("verified_original_git_raw_bytes")==229515688
            and evidence.get("remote_binary_publication_verified") is True,
            "incomplete or self-contradictory prior remote original publication")
    require(all(evidence.get(flag) is False for flag in (
            "full_continuous_collision_qualified","real_three_mixer_qualified",
            "artist_approved","unreal_compiled","physical_rtx_verified",
            "release_qualified")),
            "remote source receipt claims unverified product acceptance")
    heads=evidence.get("original_model_heads")
    models=evidence.get("models")
    require(isinstance(heads,dict) and set(heads)=={"pathfinder","archivist"}
            and isinstance(models,list)
            and len(models)==2 and
            [x.get("stage") for x in models]==["pathfinder","archivist"],
            "missing original remote revisions or one evolution model")
    for form,model in zip(forms,models):
        stage=form["stage"]
        branch=heads[stage]
        require(branch.get("branch")==publication.target_ref(stage)
                and publication.OID.fullmatch(branch.get("head","")),
                "incorrect original Git branch identity or commit")
        require((model.get("model_bytes"),model.get("model_sha256"))==
                (form["bytes"],form["sha256"])
                and model.get("original_donor_sha256")==DONOR
                and model.get("rig_joints")==108
                and model.get("animation_clips")==381
                and model.get("tail_root_joint")==34
                and model.get("corrected_clip")=="orbit-02"
                and model.get("corrected_quaternion_keys")==160
                and model.get("release_qualified") is False,
                "source reported model differs from immutable original V7 manifest")
        entries=model.get("verified_raw_git_parts")
        require(isinstance(entries,list) and len(entries)==4,
                "missing original published Git blob entries")
        for entry,expected in zip(entries,form["parts"]):
            require(entry.get("path")==expected["path"]
                    and entry.get("bytes")==expected["bytes"]
                    and entry.get("sha256")==expected["sha256"]
                    and publication.OID.fullmatch(entry.get("git_blob_oid","")),
                    "remote source part receipt differs from original SHA pin")
    return evidence

def exact_copy(src,destination,expected_bytes,expected_sha):
    """Snapshot file through nofollow descriptor and verify no mutation."""
    src=Path(src);destination=Path(destination)
    require(src.is_file() and not src.is_symlink()
            and destination.parent.is_dir() and
            not os.path.lexists(destination),
            "unsafe source or destination for original binary copy")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)
    source_stat=src.stat()
    identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    written=0
    checksum=hashlib.sha256()
    try:
        with os.fdopen(os.open(src,flags),"rb") as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode)
                    and identity(source_stat)==identity(before)
                    and before.st_size==expected_bytes,
                    "original V7 source identity or length changed")
            with destination.open("xb") as out:
                while written<expected_bytes:
                    chunk=stream.read(min(CHUNK,expected_bytes-written))
                    require(chunk,"truncated model while staging original")
                    out.write(chunk)
                    checksum.update(chunk)
                    written+=len(chunk)
                require(not stream.read(1),"appended source model bytes")
                out.flush();os.fsync(out.fileno())
            require(identity(before)==identity(os.fstat(stream.fileno()))
                    and checksum.hexdigest()==expected_sha,
                    "original source mutated or SHA-256 differs during staging")
    except BaseException:
        if destination.exists():destination.unlink()
        raise
    return {"bytes":written,"sha256":checksum.hexdigest()}

def install_quarantine(source,destination):
    source=outside_worktree(source)
    destination=outside_worktree(destination)
    require(trusted_dir(source) and trusted_dir(destination.parent)
            and not os.path.lexists(destination)
            and not destination.is_relative_to(source),
            "fresh separate non-runtime quarantine destination required")
    forms,_original_manifest=publication.load()
    require(len(forms)==2,"incomplete pinned V7 source stage inventory")
    preceding=source_receipt(source,forms)
    require(shutil.disk_usage(destination.parent).free >=
            sum(x["bytes"] for x in forms)+publication.PART,
            "insufficient trusted quarantine scratch capacity")
    lock=destination.parent/("."+destination.name+".quarantine.lock")
    require(not os.path.lexists(lock),
            "concurrent V7 quarantine mutation is not allowed")
    lock.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(dir=destination.parent,
                                         prefix=".emerald-v7-quarantine-") as scratch:
            scratch=Path(scratch)
            records=[]
            for form in forms:
                path=scratch/form["asset"]
                copied=exact_copy(source/form["asset"],path,
                                  form["bytes"],form["sha256"])
                independent=remote.verify_model_shape(path,form)
                require(independent["model_sha256"]==copied["sha256"]
                        and independent["release_qualified"] is False,
                        "quarantined original model structure differs")
                path.chmod(0o444)
                records.append({"stage":form["stage"],**copied,
                                "donor_sha256":DONOR,
                                "source_model_byte_verified":True,
                                "source_current_remote_head_rechecked":False,
                                "approved_for_runtime":False})
            output={
              "schema":SCHEMA,
              "original_model_count":2,"original_total_bytes":sum(x["bytes"] for x in forms),
              "original_donor_sha256":DONOR,
              "source_remote_heads":preceding["original_model_heads"],
              "previous_source_receipt_present":True,
              "source_current_remote_head_rechecked":False,
              "source_files_sha_verified":True,
              "models":records,
              "quarantine_only":True,
              "approved_for_runtime":False,
              "frontend_public_asset_installed":False,
              "native_original_model_replaced":False,
              "equipment_enabled":False,
              "full_continuous_collision_qualified":False,
              "real_three_mixer_qualified":False,
              "artist_approved":False,
              "unreal_compiled":False,
              "physical_rtx_verified":False,
              "remote_publication_revalidated_by_this_step":False,
              "release_qualified":False,
            }
            with (scratch/STAGING_RECEIPT).open("x",encoding="utf-8") as stream:
                json.dump(output,stream,indent=2,allow_nan=False)
                stream.write("\n");stream.flush();os.fsync(stream.fileno())
            require(not os.path.lexists(destination),
                    "quarantine path appeared during original review staging")
            os.rename(scratch,destination)
        return output
    finally:
        lock.rmdir()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    record=install_quarantine(a.source,a.output)
    print(json.dumps({k:v for k,v in record.items()
                      if k!="models"},indent=2))

if __name__=="__main__":
    main()
