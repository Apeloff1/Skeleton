"""Review recorded original V6/V7 archive hashes without claiming CI reexecuted ZIPs."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import audit_emerald_v7_original_zip_pair as original

DEFAULT=Path(__file__).resolve().parents[1]/"assets/emerald/evolution-v7/independent-original-zip-custody-20261117.json"
PREFIX={
 "pathfinder":"6b6e4f45eee5f5fd7c58599298fff2e84aa5920364acde7197ea8a91369a4c60",
 "archivist":"eec290d8759efcd53c2e74bb8425fc2f1d118e79a0e7ec306018341fb5d414a5",
}

def require(condition,why):
 if not condition:raise ValueError(why)

def verify(record):
 require(record.get("schema")=="skeleton.emerald.v7.original-binary-custody-independent.v1"
         and record.get("all_models_exact_sha") is True
         and record.get("source_geometry_material_skin_prefix_retained") is True
         and record.get("new_animation_streams_per_stage")==1
         and record.get("modified_quaternion_keys_per_stage")==160
         and record.get("actual_source_byte_rechecked") is True,
         "recorded source audit lacks original model evidence")
 forms=record.get("models")
 require(isinstance(forms,list) and [x.get("stage") for x in forms]==list(original.STAGES),
         "missing or repeated original donor model")
 for form in forms:
  stage=form["stage"]
  for version in ("v6","v7"):
   source=form.get(version,{})
   size,sha,archive_size,archive_sha=original.FILES[stage][version]
   require((source.get("bytes"),source.get("sha256"),
            source.get("zip_bytes"),source.get("zip_sha256"))==
           (size,sha,archive_size,archive_sha),
           "source original V6/V7 ZIP or GLB digest differs")
  require(form.get("original_binary_prefix_sha256")==PREFIX[stage]
          and all(form.get(flag) is True for flag in (
              "original_binary_prefix_identical","source_mesh_skin_material_nodes_exact",
              "growth_animation_exact"))
          and form.get("total_animation_clips")==381
          and form.get("rig_joints")==108
          and form.get("new_animation_accessors")==1
          and form.get("new_animation_views")==1
          and form.get("modified_clip")=="orbit-02"
          and form.get("modified_keyframes")==160,
          "original model prefix, rig or 160-key orbit change differs")
 require(all(record.get(flag) is False for flag in (
     "full_continuous_collision_qualified",
     "artist_approved","physical_rtx_verified","remote_git_binary_verified",
     "release_qualified")),
     "original model hashes used to fake physical or launch approval")
 return {"schema":"skeleton.emerald.v7.original-zip-ledger-consistency.v1",
         "recorded_original_v6_v7_zip_count":4,
         "recorded_complete_glb_models":4,
         "one_reviewed_160_key_tail_track_per_v7_form":True,
         "recorded_evidence_consistent":True,
         "actual_four_zips_replayed_by_source_only_ci":False,
         "remote_git_binary_verified":False,
         "full_continuous_collision_qualified":False,
         "artist_approved":False,"physical_rtx_verified":False,
         "release_qualified":False}

if __name__=="__main__":
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--receipt",type=Path,default=DEFAULT)
 a=p.parse_args()
 print(json.dumps(verify(json.loads(a.receipt.read_bytes())),indent=2))
