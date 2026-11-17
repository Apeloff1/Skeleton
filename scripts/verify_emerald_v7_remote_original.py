"""Verify and assemble exact published V7 original GLBs from raw remote Git blobs.

The separate stage draft PRs contain four unfiltered Git blobs each ONLY
after publication. This operator validates *the remote objects*, both whole
GLBs, model provenance and immutable branch heads before declaring remote
publication verified. It never merges, activates, releases or installs models.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

import publish_emerald_v7_orbit02 as transport
from emerald_v7_model_pins import DONOR,OUTPUTS,ROOT_JOINT,ANGLE,TARGET_CLIP

RECEIPT_SCHEMA="skeleton.emerald.v7.git-original-remote-reassembly.v1"
MAX_JSON_BYTES=32*1024**2
SCRATCH_RESERVE=transport.PART

def require(condition,message):
    if not condition:raise ValueError(message)

def remote_revision(repo,form,manifest):
    """Fetch exact sibling branch; reject publication races and wrong manifest."""
    ref,commit=transport.head(repo,form,manifest)
    current=transport.git(repo,"ls-remote","--exit-code","origin",ref).decode("ascii").split()
    require(current==[commit,ref],"remote source moved after fetch")
    return ref,commit

def verify_model_shape(file,form):
    """Lightweight independent GLB sanity, after entire model hash is verified."""
    path=Path(file)
    require(path.is_file() and not path.is_symlink()
            and (path.stat().st_size,transport.sha(path))==
                (form["bytes"],form["sha256"]),
            "fully assembled original model SHA-256 differs")
    with path.open("rb") as source:
        header=source.read(20)
        require(len(header)==20,"original GLB too short")
        magic,version,total,json_size,json_tag=struct.unpack("<4sIIII",header)
        require((magic,version,total,json_tag)==
                (b"glTF",2,form["bytes"],0x4e4f534a)
                and 0<json_size<=MAX_JSON_BYTES and json_size%4==0,
                "original GLB or JSON header differs")
        doc=json.loads(source.read(json_size))
        require(source.tell()==20+json_size,
                "original GLB JSON truncated")
        bin_head=source.read(8)
        require(len(bin_head)==8,"missing original BIN header")
        length,tag=struct.unpack("<II",bin_head)
        require(tag==0x004e4942 and 28+json_size+length==total,
                "original full GLB binary extent differs")
    identity=doc.get("extras",{})
    correction=identity.get("orbit02ClearanceCorrection",{})
    require(doc.get("asset",{}).get("version")=="2.0"
            and identity.get("stage")==form["stage"]
            and identity.get("donorSha256")==DONOR
            and len(doc.get("skins",[]))==1
            and len(doc["skins"][0]["joints"])==108
            and len(doc.get("animations",[]))==381
            and correction.get("schema")=="skeleton.emerald.orbit02-tail-clearance.v1"
            and correction.get("source_v6_sha256")==form["source_v6_sha256"]
            and correction.get("donor_sha256")==DONOR
            and correction.get("joint_index")==ROOT_JOINT
            and correction.get("clip")==TARGET_CLIP
            and correction.get("local_y_radians")==ANGLE
            and correction.get("modified_sampler_streams")==1
            and correction.get("modified_keyframes")==160,
            "remote original does not match source-bound V7 donor/animation")
    require(all(correction.get(flag) is False for flag in (
        "automatic_adoption","equipment_enabled",
        "continuous_collision_qualified",
        "real_mixer_qualified","crossfade_transition_qualified",
        "artist_approved","unreal_compiled","physical_rtx_verified",
        "release_qualified") if flag in correction),
        "original remote GLB metadata falsely claims acceptance")
    require(all(form.get(flag) is False for flag in (
        "automatic_adoption","continuous_collision_qualified",
        "real_three_mixer_qualified","artistic_approved",
        "physical_rtx_verified","release_qualified")),
        "review-only original form manifest was elevated")
    return {"stage":form["stage"],"model_bytes":form["bytes"],
            "model_sha256":form["sha256"],
            "original_donor_sha256":DONOR,
            "rig_joints":108,"animation_clips":381,
            "tail_root_joint":ROOT_JOINT,
            "corrected_clip":TARGET_CLIP,
            "corrected_quaternion_keys":160,
            "release_qualified":False}

def remote_part(repo,head,entry):
    """Retrieve exact remote tree entry, reject LFS pointers and unsafe modes."""
    path=entry["path"]
    listing=transport.git(repo,"ls-tree",head,"--",path).decode("ascii")
    require(listing.count("\n")==1 and "\t" in listing,
            "remote original raw binary part is missing: "+path)
    metadata,name=listing.strip().split("\t",1)
    parts=metadata.split()
    require(name==path and len(parts)==3 and
            parts[0]=="100644" and parts[1]=="blob" and
            transport.OID.fullmatch(parts[2]),
            "remote original model tree entry is not an ordinary raw blob")
    identifier=parts[2]
    require(transport.git(repo,"cat-file","-t",identifier)==b"blob\n",
            "remote original object is not a Git blob")
    length=int(transport.git(repo,"cat-file","-s",identifier))
    require(length==entry["bytes"] and 0<length<=transport.PART,
            "remote raw blob byte count differs from source manifest")
    raw=transport.git(repo,"cat-file","blob",identifier)
    require(len(raw)==length and transport.digest(raw)==entry["sha256"],
            "remote raw Git object has wrong SHA-256")
    # Whole model reconstruction reads only actual Git object content.
    return raw,identifier

def stream_form(repo,head,form,destination):
    """Do not create a completed model until every actual raw Git part matches."""
    output=Path(destination)
    require(output.parent.is_dir() and not output.parent.is_symlink()
            and not os.path.lexists(output) and
            output.name==form["asset"],
            "new original model output path required")
    total=0
    whole=hashlib.sha256()
    parts=[]
    try:
        with output.open("xb") as out:
            for entry in form["parts"]:
                require(entry["offset"]==total,
                        "original model offsets do not form a contiguous byte stream")
                raw,blob=remote_part(repo,head,entry)
                total+=len(raw)
                require(total<=form["bytes"],
                        "unapproved extra original model bytes")
                out.write(raw);whole.update(raw)
                parts.append({"path":entry["path"],
                              "git_blob_oid":blob,"bytes":len(raw),
                              "sha256":entry["sha256"]})
            out.flush()
            os.fsync(out.fileno())
        require(total==form["bytes"] and
                whole.hexdigest()==form["sha256"],
                "remote original complete GLB digest mismatch")
        original=verify_model_shape(output,form)
        return {**original,"verified_raw_git_parts":parts}
    except BaseException:
        if output.exists():output.unlink()
        raise

def verify_remote(repo,destination):
    """Transactional two-model delivery; release flags remain false."""
    repo=Path(repo)
    destination=Path(destination).absolute()
    require(destination.parent.is_dir()
            and not destination.parent.is_symlink()
            and not os.path.lexists(destination),
            "trusted unused complete original-model output directory required")
    forms,manifest=transport.load()
    require(tuple(x["stage"] for x in forms)==("pathfinder","archivist"),
            "incomplete original V7 two-form publication")
    require(shutil.disk_usage(destination.parent).free >=
            sum(x["bytes"] for x in forms)+SCRATCH_RESERVE,
            "insufficient capacity for two exact original GLBs")
    transport.authorized(repo)
    heads={}
    for form in forms:
        ref,sha=remote_revision(repo,form,manifest)
        heads[form["stage"]]={"branch":ref,"head":sha}
    output={"schema":RECEIPT_SCHEMA,
            "original_donor_sha256":DONOR,
            "remote_repository":"Apeloff1/Skeleton",
            "original_model_count":2,
            "verified_original_git_raw_bytes":0,
            "original_model_heads":heads,
            "models":[],
            "remote_binary_publication_verified":False,
            "full_continuous_collision_qualified":False,
            "real_three_mixer_qualified":False,
            "artist_approved":False,
            "unreal_compiled":False,
            "physical_rtx_verified":False,
            "release_qualified":False}
    lock=destination.parent/("."+destination.name+".custody.lock")
    require(not os.path.lexists(lock),
            "another original Git publication qualifier is running")
    lock.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(dir=destination.parent,
                                         prefix=".emerald-v7-remote-") as scratch:
            scratch=Path(scratch)
            for form in forms:
                stage=form["stage"]
                item=stream_form(repo,heads[stage]["head"],form,scratch/form["asset"])
                output["models"].append(item)
                output["verified_original_git_raw_bytes"]+=item["model_bytes"]
            # Repeat read-only remote source check after fetching all 8 objects.
            for form in forms:
                stage=form["stage"]
                ref=heads[stage]["branch"]
                latest=transport.git(repo,"ls-remote","--exit-code",
                                     "origin",ref).decode("ascii").split()
                require(latest==[heads[stage]["head"],ref],
                        "remote source head changed during full model verification")
            require(output["verified_original_git_raw_bytes"]==
                    sum(x["bytes"] for x in forms)==229515688,
                    "remote two-form GLB source inventory incomplete")
            output["remote_binary_publication_verified"]=True
            with (scratch/"remote-git-original-custody.json").open("x",encoding="utf-8") as out:
                json.dump(output,out,indent=2,allow_nan=False)
                out.write("\n");out.flush();os.fsync(out.fileno())
            require(not os.path.lexists(destination),
                    "destination appeared during original source qualification")
            os.rename(scratch,destination)
        return output
    finally:
        lock.rmdir()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    result=verify_remote(a.repo,a.output)
    print(json.dumps({key:value for key,value in result.items()
                      if key!="models"},indent=2))

if __name__=="__main__":
    main()
