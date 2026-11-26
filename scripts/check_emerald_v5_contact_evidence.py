"""Verify measured Scholar V5 contact receipts for consistency, not CCD proof."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"assets/emerald/evolution-v5/scholar-wingfold-r1"
SHA="3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877"

def require(x,why):
    if not x:raise ValueError(why)

def verify(before,expanded):
    require(before.get("schema")=="skeleton.emerald.scholar-wingfold-exact-audit.v1"
            and expanded.get("schema")=="skeleton.emerald.scholar-v5-expanded-contact.v1"
            and before.get("output_sha256")==expanded.get("candidate_sha256")==SHA
            and before.get("model_bytes")==113305100
            and before.get("source_donor_sha256")==expanded.get("donor_sha256"),
            "source or candidate identity differs")
    require(before.get("rig_joints")==108 and before.get("animation_clips")==381
            and before.get("corrected_terminal_joint_tracks")==760
            and before.get("unchanged_source_binary_prefix") is True
            and before.get("unchanged_all_mesh_and_material_bytes") is True
            and before.get("growth_endpoint_max_error_m",1) < 3e-6,
            "structural evidence incomplete")
    require(expanded.get("batch_completed")=={"a":True,"b":True,"c":True}
            and expanded.get("extra_sampled_poses")==24
            and expanded.get("earlier_poses")==7
            and expanded.get("total_sampled_poses")==31,
            "missing or duplicate sample batch")
    names=set()
    total_contacts=near_total=0
    for pose in expanded["poses"]:
        require(pose.get("batch") in ("a","b","c") and
                isinstance(pose.get("clip"),str) and
                pose["clip"].startswith(("ground-","takeoff-","orbit-","landing-")) and
                pose.get("fraction") in (.25,.5,.75) and
                type(pose.get("contacts")) is int and pose["contacts"]>=0 and
                type(pose.get("near_pairs")) is int and pose["near_pairs"]>=0,
                "invalid contact sample")
        key=(pose["clip"],pose["fraction"])
        require(key not in names,"duplicated pose evidence")
        names.add(key)
        total_contacts+=pose["contacts"]
        near_total+=pose["near_pairs"]
    require(len(names)==24 and
            total_contacts==expanded["extra_contact_count"]==0 and
            near_total==expanded["extra_near_pairs"]==16701,
            "sample counts inconsistent")
    old=before["sampled_poses"]
    require(len(old)==7 and all(row.get("contact_count")==0 for row in old),
            "earlier seven-pose clearance inconsistent")
    require(before.get("classified_triangles")==expanded.get("classified_triangles")==269919
            and before.get("unclassified_triangles")==expanded.get("unclassified_triangles")==449393
            and 269919+449393==719312,
            "incomplete anatomical coverage statement")
    for receipt in (before,expanded):
        require(receipt.get("release_qualified") is False and
                receipt.get("physical_rtx_verified") is False and
                receipt.get("artist_approved",receipt.get("artist_accepted")) is False,
                "false-positive release or artist evidence")
    require(before.get("full_continuous_collision_qualified") is False and
            expanded.get("full_continuous_collision_qualified") is False and
            before.get("equipment_enabled") is False and
            expanded.get("equipment_enabled") is False,
            "false continuous collision or optional equipment qualification")
    return {"candidate_sha256":SHA,"checked_pose_receipts":31,
            "classified_triangles":269919,"unclassified_triangles":449393,
            "observed_contacts":0,"near_pairs_in_extra_samples":16701,
            "receipt_consistency_passed":True,"independently_replayed_in_ci":False,
            "continuous_collision_qualified":False,
            "release_qualified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original",type=Path,default=FOLDER/"sampled-contact-receipt.json")
    p.add_argument("--expanded",type=Path,default=FOLDER/"expanded-contact-evidence.json")
    a=p.parse_args()
    print(json.dumps(verify(json.loads(a.original.read_bytes()),
                            json.loads(a.expanded.read_bytes())),indent=2))

if __name__=="__main__":
    main()
