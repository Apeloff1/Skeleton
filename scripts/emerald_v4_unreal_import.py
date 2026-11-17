"""Run only inside an installed Unreal Editor Python environment with GLB importer.

Five exact original-donor V4 models and their 381 animations must import into
separate nonce-named editor paths; no art, physical RTX, release acceptance.
"""
import hashlib,json,os,re,sys,traceback,uuid,struct
from pathlib import Path
import unreal

run_id=os.environ.get("EMERALD_V4_RUN_ID","")
if not re.fullmatch(r"[a-f0-9]{32}",run_id):raise RuntimeError("signed operator run ID missing")
repo=Path(os.environ["EMERALD_V4_REPO"]).resolve()
assets=Path(os.environ["EMERALD_V4_ASSETS"]).resolve()
expected=json.loads((repo/"assets/emerald/evolution-v4/publication-manifest.json").read_text())
pin=json.loads((repo/"frontend/src/features/Jeeves/companion/atelier/evolutionPin.json").read_text())
def source_structure(file,stage,donor):
  with file.open('rb') as src:
    header=src.read(20)
    if len(header)!=20:raise RuntimeError('truncated GLB header')
    magic,version,length,jsonlen,tag=struct.unpack('<4sIIII',header)
    if magic!=b'glTF' or version!=2 or length!=file.stat().st_size or jsonlen>32*1024**2 or tag!=0x4e4f534a:raise RuntimeError('untrusted GLB structure')
    obj=json.loads(src.read(jsonlen))
  if obj.get('asset',{}).get('version')!='2.0' or obj.get('extras',{}).get('stage')!=stage or obj.get('extras',{}).get('donorSha256')!=donor:raise RuntimeError('GLB donor and stage metadata differ')
  skins=obj.get('skins',[])
  if len(skins)!=1 or len(skins[0].get('joints',[]))!=108:raise RuntimeError('weighted rig mismatch')
  names=[a.get('name') for a in obj.get('animations',[])]
  if len(names)!=381 or any(not isinstance(x,str) or len(x)>200 for x in names) or len(set(names))!=381:raise RuntimeError('incomplete animation catalogue')
  if names[-1]!='growth-'+stage+'-to-'+({'hatchling':'scout','scout':'scholar','scholar':'pathfinder','pathfinder':'archivist','archivist':'hoarder'}[stage]):raise RuntimeError('incorrect next-form growth target')
  if any('targets' not in x for x in obj.get('meshes',[{}])[0].get('primitives',[])):raise RuntimeError('missing morph targets')
  return names

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
    catalogue=source_structure(source,stage,expected['donor_sha256'])
    folder="/Game/EmeraldV4/Qualification/"+stage+"_"+actual[:12]+"_"+run_id[:8]
    task=unreal.AssetImportTask()
    task.set_editor_property("filename",str(source))
    task.set_editor_property("destination_path",folder)
    task.set_editor_property("automated",True)
    task.set_editor_property("replace_existing",False)
    task.set_editor_property("save",True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported=[str(p) for p in unreal.EditorAssetLibrary.list_assets(folder,recursive=True,include_folder=False)]
    objs=[unreal.EditorAssetLibrary.load_asset(p) for p in imported]
    meshes=[x for x in objs if isinstance(x,unreal.SkeletalMesh)]
    clips=[x for x in objs if isinstance(x,unreal.AnimSequence)]
    if len(meshes)!=1 or len(clips)!=381 or any(x is None for x in objs):
      raise RuntimeError("full weighted mesh and 381 clip importer contract failed: "+stage)
    skeleton=meshes[0].get_editor_property("skeleton")
    if skeleton is None or any(c.get_editor_property("skeleton")!=skeleton for c in clips):
      raise RuntimeError("imported animation skeleton mismatch: "+stage)
    def normalized(name):return re.sub('[^a-z0-9]+','_',name.lower()).strip('_')
    bound=set()
    for requested in catalogue:
      key=normalized(requested)
      matching=[a for a in clips if normalized(a.get_name())==key or normalized(a.get_name()).endswith('_'+key)]
      if len(matching)!=1:raise RuntimeError('missing or duplicate imported animation: '+requested)
      name=matching[0].get_path_name()
      if name in bound:raise RuntimeError('animation assigned to multiple source clips')
      bound.add(name)
    row={"stage":stage,"source_sha256":actual,"source_bytes":record["bytes"],
         "skeletal_mesh":meshes[0].get_path_name(),
         "animation_count":len(clips),"source_animation_names_exact":True,"skeleton":skeleton.get_path_name(),
         "imported_paths":imported,"artist_approved":False}
    result["models"].append(row)
  result["engine_editor_imported"]=len(result["models"])==5
except Exception as exc:
  result["error"]=str(exc);result["traceback"]=traceback.format_exc()
  unreal.log_error(str(exc))
finally:
  receipt.write_text(json.dumps(result,indent=2))
if not result["engine_editor_imported"]:raise RuntimeError("V4 exact engine import not qualified; inspect "+str(receipt))
