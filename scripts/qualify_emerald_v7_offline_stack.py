"""Resume-safe original-byte Emerald V7 full offline qualification conveyor.

Three immutable inputs: prior V6 exact original GLBs, two exact V7 ZIP
packages, and two original source-tool archives. Rebuild original V7 GLBs
with exact sha256; revalidate one-track mutation; run 108 source-bound
sampled-pose checks with checkpoints and independent witness ledger checks.
No native, browser, artist, hardware, continuous CCD, merge or release claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

import check_emerald_v7_nine_phase as nine
import emerald_v7_crossfade_screen as screen
import prepare_emerald_v7_reviewed_tools as tools
import publish_emerald_v7_orbit02 as transport
import verify_emerald_v7_orbit02 as independent

STAGES=("pathfinder","archivist")
MODEL_BYTES=sum(x[0] for x in screen.OUTPUTS.values())
SAMPLES_PER_STAGE=54
REQUIRED_FREE=MODEL_BYTES+128*1024**2
SCHEMA="skeleton.emerald.v7.offline-full-chain.v1"

def require(condition,message):
    if not condition:
        raise ValueError(message)

def digest(path):
    with Path(path).open("rb") as data:
        return hashlib.file_digest(data,"sha256").hexdigest()

def verified_original_v6(root,stage):
    path=Path(root)/(stage+".glb")
    size,sha=independent.SOURCES[stage]
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size==size and digest(path)==sha,
            "missing exact original V6 source GLB: "+stage)
    return path

def verify_staged_tools(path):
    path=Path(path)
    receipt=path/"source-custody.json"
    require(path.is_dir() and not path.is_symlink() and
            receipt.is_file() and not receipt.is_symlink(),
            "missing staged original contact source receipt")
    data=json.loads(receipt.read_bytes())
    require(data.get("schema")=="skeleton.emerald.reviewed-tools-custody.v1"
            and data.get("donor_sha256")==tools.MODEL_SHA
            and data.get("staged_file_count")==5
            and all(data.get(flag) is False for flag in (
                "source_executed_by_this_command",
                "original_model_bytes_copied","measured_contact_clearance",
                "continuous_collision_qualified",
                "real_three_mixer_qualified","artist_approved",
                "physical_rtx_verified","release_qualified")),
            "original source-tool staging receipt differs")
    require(data.get("archives")=={
        kind:{"sha256":meta["sha256"],"bytes":meta["bytes"]}
        for kind,meta in tools.ARCHIVES.items()},
        "reviewed original archive provenance mismatch")
    for filename,(_kind,length,sha) in tools.FILES.items():
        target=path/filename
        require(target.is_file() and not target.is_symlink()
                and target.stat().st_size==length and digest(target)==sha
                and data["staged_files"].get(filename,{}).get("sha256")==sha,
                "modified source-tool import: "+filename)
    require({i.name for i in path.iterdir()}==
            set(tools.FILES)|{"source-custody.json"},
            "extra unreviewed code in the original contact tool directory")
    return True

def stage_v7_original(zip_path,form,output):
    """Stream exactly pinned original chunk bytes to a new GLB, no ZIP extraction."""
    output=Path(output)
    require(output.parent.is_dir() and not output.parent.is_symlink()
            and not os.path.lexists(output) and output.name==form["asset"],
            "trusted unused destination for original model required")
    written=0
    whole=hashlib.sha256()
    try:
        with output.open("xb") as destination:
            for part,raw in transport.verified_zip(zip_path,form):
                require(part["offset"]==written and len(raw)==part["bytes"],
                        "original binary part order differs")
                destination.write(raw)
                whole.update(raw)
                written+=len(raw)
            destination.flush()
            os.fsync(destination.fileno())
        require(written==form["bytes"] and
                whole.hexdigest()==form["sha256"],
                "model reconstruction differs from exact V7 source")
    except BaseException:
        if output.exists():
            output.unlink()
        raise
    return {"original_glb":str(output),"sha256":whole.hexdigest(),
            "model_bytes":written,"v7_original_bytes_verified":True}

def validate_operator_report(report,stage,form):
    require(report.get("schema")=="skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1"
            and report.get("stage")==stage
            and report.get("sampled_screen_complete") is True
            and report.get("generation")=="v7",
            "wrong or incomplete real original V7 exported pose report")
    ledger_form=next(x for x in load_ledger()["forms"] if x["stage"]==stage)
    nine.verify_full_report(report,ledger_form,ledger_form["near_margin_counts_by_route"])
    return {
      "stage":stage,
      "exact_glb_sha256":form["sha256"],
      "sampled_poses":report["total_sampled_blends"],
      "new_contacts":report["observed_new_contact_instances"],
      "near_margin_pairs":sum(r["within_8mm_not_contact"] for r in report["samples"]),
      "origin_report_matches_recorded_pose_matrix":True,
      "real_three_mixer_qualified":False,
      "continuous_collision_qualified":False,
      "release_qualified":False,
    }

def load_ledger():
    ledger=json.loads(nine.DEFAULT.read_bytes())
    nine.verify(ledger)
    return ledger

def require_inputs(bundle_dir,source_v6,contact_zip,seams_zip):
    forms,_raw=transport.load()
    require(tuple(f["stage"] for f in forms)==STAGES,
            "source publication manifest mismatch")
    v6={stage:verified_original_v6(source_v6,stage) for stage in STAGES}
    # Recheck both zip containers before any state mutation or model staging.
    for form in forms:
        source=Path(bundle_dir)/form["zip_filename"]
        require(source.is_file() and not source.is_symlink() and
                source.stat().st_size>=form["bytes"] and
                transport.sha(source)==form["zip_sha256"],
                "original V7 ZIP missing or source pin mismatch: "+form["stage"])
    archive_paths={
      "contact":tools.authorize_archive(contact_zip,"contact"),
      "seams":tools.authorize_archive(seams_zip,"seams"),
    }
    return forms,v6,archive_paths

def workspace_admission(workdir,resume):
    workdir=Path(workdir).absolute()
    require(workdir.parent.is_dir() and not workdir.parent.is_symlink(),
            "trusted workspace parent required")
    if resume:
        require(workdir.is_dir() and not workdir.is_symlink()
                and (workdir/"source-tools").is_dir()
                and (workdir/"models").is_dir()
                and (workdir/"reports").is_dir(),
                "cannot resume incomplete or untrusted qualification workspace")
    else:
        require(not os.path.lexists(workdir),"fresh unique workspace required")
        require(shutil.disk_usage(workdir.parent).free>=REQUIRED_FREE,
                "insufficient original model plus scratch storage")
        workdir.mkdir(mode=0o700)
        (workdir/"models").mkdir(mode=0o700)
        (workdir/"reports").mkdir(mode=0o700)
    return workdir

def execute(workdir,bundles,source_v6,contact_zip,seams_zip,resume=False,budget=1200):
    require(type(resume) is bool and 60<=budget<=7200,
            "invalid execution mode or resource budget")
    forms,v6,archives=require_inputs(
        bundles,source_v6,contact_zip,seams_zip)
    ledger=load_ledger()
    work=workspace_admission(workdir,resume)
    require(not (work/"qualification-complete.json").exists(),
            "workspace already finalized; refusing repeated qualification")
    source_tools=work/"source-tools"
    if resume:
        verify_staged_tools(source_tools)
    else:
        tools.stage(archives["contact"],archives["seams"],source_tools)
        verify_staged_tools(source_tools)
    evidence=[]
    for form in forms:
        stage=form["stage"]
        model=work/"models"/form["asset"]
        if not resume:
            stage_v7_original(Path(bundles)/form["zip_filename"],form,model)
        else:
            require(model.is_file() and not model.is_symlink()
                    and (model.stat().st_size,digest(model))==
                     (form["bytes"],form["sha256"]),
                    "staged original V7 model changed since checkpoint")
        structural=independent.verify(stage,v6[stage],model)
        require(structural["original_embedded_binary_prefix_exact"] is True
                and structural["original_mesh_skin_materials_exact"] is True
                and structural["growth_clip_exact"] is True
                and structural["modified_sampler_streams"]==1
                and structural["modified_keyframes"]==160,
                "unqualified source V6 → V7 mutation")
        final=work/"reports"/(stage+"-nine-phase-contact-report.json")
        progress=work/"reports"/(stage+"-checkpoint.json")
        if final.exists():
            require(resume and final.is_file() and not final.is_symlink(),
                    "pre-existing final report not authorized")
            report=json.loads(final.read_bytes())
        else:
            report=screen.run(
                stage,model,source_tools,steps=9,time_budget=budget,
                checkpoint=progress,resume=resume and progress.exists())
            # Preserve measured results even when they disagree with the
            # original recorded near-margin counts, for independent triage.
            with final.open("x",encoding="utf-8") as stream:
                json.dump(report,stream,indent=2,allow_nan=False)
                stream.write("\n")
                stream.flush();os.fsync(stream.fileno())
        admission=validate_operator_report(report,stage,form)
        admission["independent_original_byte_verifier"]=structural["schema"]
        admission["sampled_report_sha256"]=digest(final)
        admission["recorded_full_report_digest_equal"]=(digest(final)==next(
            x["full_report_sha256"] for x in ledger["forms"]
            if x["stage"]==stage))
        evidence.append(admission)
    require(len(evidence)==2 and
            sum(e["sampled_poses"] for e in evidence)==108 and
            sum(e["new_contacts"] for e in evidence)==0 and
            sum(e["near_margin_pairs"] for e in evidence)==415154,
            "original source-bound 108-pose evidence differs")
    result={
      "schema":SCHEMA,"original_donor_sha256":tools.MODEL_SHA,
      "original_contact_source_verified":True,
      "original_v6_to_v7_binary_prefix_verified":True,
      "original_v7_glbs_verified":2,
      "actual_sampled_poses_replayed":108,
      "source_stage_results":evidence,
      "recorded_ledger_sha256":digest(nine.DEFAULT),
      "approximate_crossfade_only":True,
      "all_anatomical_pairs_qualified":False,
      "continuous_collision_qualified":False,
      "real_three_mixer_qualified":False,
      "artist_approved":False,
      "physical_rtx_verified":False,
      "remote_binary_publication_verified":False,
      "release_qualified":False,
    }
    receipt=work/"qualification-complete.json"
    with receipt.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--v7-bundles",type=Path,required=True)
    parser.add_argument("--v6-models",type=Path,required=True)
    parser.add_argument("--contact-archive",type=Path,required=True)
    parser.add_argument("--v6-source-archive",type=Path,required=True)
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--budget-per-stage-seconds",type=float,default=1200)
    a=parser.parse_args()
    result=execute(a.workspace,a.v7_bundles,a.v6_models,
                   a.contact_archive,a.v6_source_archive,
                   resume=a.resume,budget=a.budget_per_stage_seconds)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
