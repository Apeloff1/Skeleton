"""Validate exact-run Unreal import evidence; never elevate to physical RTX or art approval."""
import argparse,json,re
from pathlib import Path

SCHEMA="skeleton.emerald.unreal-import.evidence.v1"
STAGES=("hatchling","scout","scholar","pathfinder","archivist")
HEX=re.compile(r"[0-9a-f]{64}\Z")
RUN=re.compile(r"[0-9a-f]{32}\Z")

def check(value,why):
    if not value:raise ValueError(why)

def verify(receipt,manifest,run_id):
    check(receipt.get("schema")==SCHEMA and RUN.fullmatch(run_id)
          and receipt.get("run_id")==run_id,"wrong or missing exact-run evidence")
    check(receipt.get("engine_editor_imported") is True and
          receipt.get("engine_compiled") is False and
          receipt.get("physical_rtx_verified") is False and
          receipt.get("artist_approved") is False and
          receipt.get("release_qualified") is False,"false-green claim or incomplete import")
    check(isinstance(receipt.get("engine_version"),str) and
          re.match(r"^5\.",receipt["engine_version"]),"unsupported Unreal version")
    rows=receipt.get("models")
    check(isinstance(rows,list) and len(rows)==5,"five separate skeletal imports required")
    check(tuple(x.get("stage") for x in rows)==STAGES,"import ordering differs")
    expected={x["stage"]:x for x in manifest["forms"]}
    for row in rows:
        name=row["stage"];bound=expected[name]
        check(row.get("source_sha256")==bound["sha256"] and HEX.fullmatch(bound["sha256"])
              and row.get("source_bytes")==bound["bytes"]
              and row.get("animation_count")==381 and row.get("source_animation_names_exact") is True and
              isinstance(row.get("skeletal_mesh"),str)
              and row["skeletal_mesh"].startswith("/Game/EmeraldV4/Qualification/"+name+"_")
              and isinstance(row.get("skeleton"),str)
              and row["skeleton"].startswith("/Game/")
              and isinstance(row.get("imported_paths"),list)
              and len(row["imported_paths"])>=382
              and row.get("artist_approved") is False,
              "incomplete or mismatched native skeletal import: "+name)
    return {"schema":"skeleton.emerald.unreal-v4.review.v1","run_id":run_id,
            "model_imports_consistent":True,"engine_version":receipt["engine_version"],
            "model_count":5,"animation_count":1905,
            "engine_compiled_independently":False,
            "physical_rtx_verified":False,"artist_approved":False,
            "continuous_collision_verified":False,"release_qualified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    args=p.parse_args()
    m=json.loads((args.repo/"assets/emerald/evolution-v4/publication-manifest.json").read_bytes())
    r=json.loads(args.receipt.read_bytes())
    print(json.dumps(verify(r,m,args.run_id),indent=2))

if __name__=="__main__":main()
