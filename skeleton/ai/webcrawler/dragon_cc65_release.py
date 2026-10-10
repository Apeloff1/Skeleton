"""Source-bound cc65 retro native build artifacts with explicit assurance levels.

PET/Plus4/Atmos: links original target-native game with installed cc65 runtime.
BBC: when the package lacks bbc.lib, compiles a BBC 6502 object only and
must label it *unlinked*. Never calls object an executable or ROM image.

Invoked by trusted CLI/CI, never automatically by an HTTP API or crawler.
Requires explicit empty output root and a local preinstalled cc65.
"""
from __future__ import annotations
from argparse import ArgumentParser
from dataclasses import asdict,dataclass
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json,os,shutil,subprocess

from .dragon_native_cc65_classics import CLASSICS
from .dragon_native_projects import render_native_project
from .dragon_game_mechanics import Mechanic

@dataclass(frozen=True)
class ClassicBuildReceipt:
    schema:str
    target:str
    toolchain_target:str
    status:str
    compiled_artifact:str
    artifact_size:int
    artifact_sha256:str
    source_fingerprint:str
    source_sha256:str
    compiler_signature_sha256:str
    target_library_present:bool
    emulator_verified:bool=False
    device_verified:bool=False
    filesystem_container_verified:bool=False
    scope:str="native cc65 compile/link only; no emulator or hardware evidence"

def _exec(argv:list[str],root:Path,timeout:int=90)->subprocess.CompletedProcess[str]:
    if len(argv)>14 or not argv or not all(type(x) is str and x for x in argv):
        raise ValueError("invalid native tool invocation")
    return subprocess.run(argv,cwd=root,timeout=timeout,text=True,
                          capture_output=True,check=False)

def _lib_present(target:str)->bool:
    command=_exec(["cl65","--print-target-path"],Path.cwd(),15)
    candidates=[]
    if command.returncode==0 and command.stdout.strip():
        path=Path(command.stdout.strip()).resolve()
        candidates.extend([path.parent/"lib"/(target+".lib"),
                           path/"lib"/(target+".lib")])
    for variable in ("CC65_HOME","LD65_LIB"):
        if os.environ.get(variable):
            path=Path(os.environ[variable])
            candidates.extend([path/(target+".lib"),path/"lib"/(target+".lib")])
    return any(x.is_file() for x in candidates)

def _safe_member(name:str,body:bytes)->tuple[ZipInfo,bytes]:
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError("unsafe native release archive member")
    record=ZipInfo(name,(1980,1,1,0,0,0))
    record.compress_type=ZIP_DEFLATED
    record.create_system=3
    record.external_attr=0o644<<16
    return record,body

def compile_classics(root:Path)->tuple[ClassicBuildReceipt,...]:
    if not shutil.which("cl65") or not shutil.which("make"):
        raise RuntimeError("cc65 C compiler, target libraries and make required")
    root=Path(root)
    if root.exists() and (root.is_symlink() or not root.is_dir() or any(root.iterdir())):
        raise ValueError("retro game release requires an empty output directory")
    root.mkdir(parents=True,exist_ok=True)
    signature=_exec(["cl65","--version"],root,10)
    if signature.returncode!=0:
        raise RuntimeError("native compiler version unavailable")
    version=signature.stdout+signature.stderr
    if not version.strip():
        raise RuntimeError("empty native compiler version")
    compiler_sha=sha256(version.encode()).hexdigest()
    receipts=[]
    for target,kind in sorted(CLASSICS.items()):
        folder=root/target
        folder.mkdir()
        project=render_native_project(
            title="Original Dragon 6502 Maze",target_id=target,
            style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
            mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
        )
        if project.status!="source_generated":
            raise RuntimeError("unexpected native source status")
        for name,body in project.files.items():
            file=folder/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(body,encoding="utf-8")
        runtime_present=_lib_present(kind.cc65)
        if not runtime_present:
            # cc65 installed but shipped without platform CRT. A raw native
            # object is useful compiler evidence, but is NOT a launchable game.
            output=folder/"build"/"dragon.o"
            output.parent.mkdir(exist_ok=True)
            result=_exec(["cl65","-c","-t",kind.cc65,"-o",
                          str(output.resolve()),"src/main.c"],folder,90)
            state="native_6502_object_compiled_unlinked"
        else:
            result=_exec(["make","all"],folder,120)
            output=folder/"build"/("dragon."+kind.output)
            state="native_6502_program_linked"
        if result.returncode:
            raise RuntimeError("cc65 "+target+" build failed: "+
                               (result.stdout+result.stderr)[-2500:])
        if not output.is_file() or output.is_symlink():
            raise RuntimeError("native target output absent or symlinked")
        bits=output.read_bytes()
        if not 128<len(bits)<=250_000:
            raise RuntimeError("unexpected native artifact size")
        sha=sha256(bits).hexdigest()
        src=sha256(project.files["src/main.c"].encode()).hexdigest()
        record=ClassicBuildReceipt(
            "skeleton.ai.dragon.cc65_build_receipt.v1",
            target,kind.cc65,state,output.relative_to(root).as_posix(),
            len(bits),sha,project.digest,src,compiler_sha,runtime_present,
        )
        receipts.append(record)
        (folder/"dragon-cc65-build-receipt.json").write_text(
            json.dumps(asdict(record),sort_keys=True,indent=2)+"\n")
    manifest={"schema":"skeleton.ai.dragon.cc65_bundle.v1",
              "compiler_signature_sha256":compiler_sha,
              "records":[asdict(x) for x in receipts],
              "linked_count":sum(x.status=="native_6502_program_linked" for x in receipts),
              "unlinked_count":sum(x.status=="native_6502_object_compiled_unlinked" for x in receipts),
              "emulator_or_physical_play_confirmed":False}
    manifest_text=json.dumps(manifest,sort_keys=True,indent=2)+"\n"
    (root/"dragon-cc65-build-bundle.json").write_text(manifest_text)
    zipfile=root/"dragon-original-cc65-builds.zip"
    with ZipFile(zipfile,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        items=[("dragon-cc65-build-bundle.json",manifest_text.encode())]
        for receipt in receipts:
            items.extend([
                (receipt.compiled_artifact,(root/receipt.compiled_artifact).read_bytes()),
                (receipt.target+"/dragon-cc65-build-receipt.json",
                 (root/receipt.target/"dragon-cc65-build-receipt.json").read_bytes()),
                (receipt.target+"/src/main.c",
                 (root/receipt.target/"src/main.c").read_bytes()),
                (receipt.target+"/Makefile",
                 (root/receipt.target/"Makefile").read_bytes()),
                (receipt.target+"/README.port.md",
                 (root/receipt.target/"README.port.md").read_bytes()),
            ])
        for path,body in sorted(items):
            header,payload=_safe_member(path,body)
            z.writestr(header,payload)
    if zipfile.stat().st_size>1_000_000:
        raise RuntimeError("native cc65 artifact archive size cap")
    print("DRAGON_NATIVE_CC65_BUILD",manifest["linked_count"],
          "LINKED",manifest["unlinked_count"],"OBJECT_ONLY")
    return tuple(receipts)

def main()->None:
    arg=ArgumentParser(description="Real native cc65 compiler/linker receipts")
    arg.add_argument("--out",type=Path,required=True)
    flags=arg.parse_args()
    compile_classics(flags.out)

if __name__=="__main__":
    main()
