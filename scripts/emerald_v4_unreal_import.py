"""Run only inside an installed Unreal Editor Python environment with GLB importer.

Five exact original-donor V4 models and their 381 animations must import into
separate nonce-named editor paths; no art, physical RTX, release acceptance.
"""
import hashlib,json,os,re,sys,traceback,uuid
from pathlib import Path
import unreal

run_id=os.environ.get("EMERALD_V4_RUN_ID","")
if not re.fullmatch(r"[a-f0-9]{32}",run_id):raise RuntimeError("signed operator run ID missing")
repo=Path(os.environ["EMERALD_V4_REPO"]).resolve()
assets=Path(os.environ["EMERALD_V4_ASSETS"]).resolve()
expected=json.loads((repo/"assets/emerald/evolution-v4/publication-manifest.json").read_text())
pin=json.loads((repo/"frontend/src/features/Jeeves/companion/atelier/evolutionPin.json").read_text())
result={"schema":"skeleton.emerald.unreal-import.evidence.v1","run_id":run_id,
        "engine_version":unreal.SystemLibrary.get_engine_version(),"models":[],
        "engine_compiled":False,"engine_editor_imported":False,"physical_rtx_verified":False,
        "artist_approved":False,"release_qualified":False}
receipt=Path(unreal.Paths.project_saved_dir())/"Emerald"/("v4_import_"+run_id+".json")
receipt.parent.mkdir(parents=True,exist_ok=True)
if receipt.exists():raise RuntimeError("refuse overwrite of run-scoped evidence")
try:
  if expected["donor_sha256"]!=pin["donorSha256"]:raise RuntimeError("donor mismatch")
  names=[f["stage"] for f in expected["forms"]]
  if names!=["hatchling","scout","scholar","pathfinder","archivist"]:raise RuntimeError("incorrect evolution order")
  for record in expected["forms"]:
    stage=record["stage"];identity=pin["forms"][stage]
    if record["sha256"]!=identity["sha256"] or record["bytes"]!=identity["bytes"] or identity["equipmentEnabled"] is not False:
      raise RuntimeError("unapproved stage identity or equipment")
    source=assets/(stage+".glb")
    if not source.is_file() or source.is_symlink() or source.stat().st_size!=record["bytes"]:
      raise RuntimeError("missing or incorrect staged original donor model: "+stage)
    with source.open("rb") as stream:actual=hashlib.file_digest(stream,"sha256").hexdigest()
    if actual!=record["sha256"]:raise RuntimeError("stage digest mismatch: "+stage)
    folder="/Game/EmeraldV4/Qualification/"+stage+"_"+actual[:12]+"_"+run_id[:8]
    task=unreal.AssetImportTask()
    task.set_editor_property("filename",str(source))
    task.set_editor_property("destination_path",folder)
    task.set_editor_property("automated",True)
    task.set_editor_property("replace_existing",False)
    task.set_editor_property("save",True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported=[str(p) for p in task.get_editor_property("imported_object_paths")]
    objs=[unreal.EditorAssetLibrary.load_asset(p) for p in imported]
    meshes=[x for x in objs if isinstance(x,unreal.SkeletalMesh)]
    clips=[x for x in objs if isinstance(x,unreal.AnimSequence)]
    if len(meshes)!=1 or len(clips)!=381 or any(x is None for x in objs):
      raise RuntimeError("full weighted mesh and 381 clip importer contract failed: "+stage)
    skeleton=meshes[0].get_editor_property("skeleton")
    if skeleton is None or any(c.get_editor_property("skeleton")!=skeleton for c in clips):
      raise RuntimeError("imported animation skeleton mismatch: "+stage)
    target_names=set()
    for item in clips:
      name=item.get_name()
      if name in target_names:raise RuntimeError("duplicate clip "+name)
      target_names.add(name)
    row={"stage":stage,"source_sha256":actual,"source_bytes":record["bytes"],
         "skeletal_mesh":meshes[0].get_path_name(),
         "animation_count":len(clips),"skeleton":skeleton.get_path_name(),
         "imported_paths":imported,"artist_approved":False}
    result["models"].append(row)
  result["engine_editor_imported"]=len(result["models"])==5
except Exception as exc:
  result["error"]=str(exc);result["traceback"]=traceback.format_exc()
  unreal.log_error(str(exc))
finally:
  receipt.write_text(json.dumps(result,indent=2))
if not result["engine_editor_imported"]:raise RuntimeError("V4 exact engine import not qualified; inspect "+str(receipt))
