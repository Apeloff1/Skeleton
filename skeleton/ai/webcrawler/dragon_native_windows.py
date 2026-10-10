"""Real original Windows native puzzle build using an audited C99 cross toolchain.

Outputs an actual x86_64 PE32+ Windows .exe, never a renamed ELF, script
wrapper, HTML app or fictitious ROM. Windows runtime behavior is NOT claimed:
on a Linux cross compiler the PE executable cannot be run and no Win32
compatibility or hardware certification has occurred. The original level
source and exact solution proofs are independently replayed before packing.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile,ZIP_DEFLATED
import json,os,re,shutil,subprocess,struct

from .dragon_native_production import (
    PortableGameDesign,ProductionRequest,_render,_hash,
    _path,_canonical,_zipinfo,_atomic_new,make_source_release,
)
from .dragon_native_desktop import _puzzle_proof,REQUIRED_SOURCE_FILES

SCHEMA="skeleton.ai.dragon.original_windows_executable.v1"
TOOL="x86_64-w64-mingw32-gcc"
ARGS=("-std=c99","-O2","-Wall","-Wextra","-Wpedantic",
      "-Iinclude","src/main.c","-o","dragon_game.exe")
MAX_EXE=4_000_000
MAX_ARCHIVE=8_000_000


@dataclass(frozen=True)
class WindowsBuildEvidence:
    schema:str
    request_id:str
    original_source_fingerprint:str
    original_source_sha256:str
    game_format:str
    windows_executable_sha256:str
    windows_executable_bytes:int
    cross_compiler:str
    fixed_compile_arguments:tuple[str,...]
    shortest_grid_levels_replayed:int
    host_execution_verified:bool
    windows_runtime_verified:bool
    user_rights_claim:str
    evidence_scope:str


def pe64_format(blob:bytes)->str:
    """Conservative PE32+ 64-bit executable structure, not runtime validation."""
    if not isinstance(blob,bytes) or len(blob)<512 or len(blob)>MAX_EXE:
        raise ValueError("native Windows executable size invalid")
    if blob[:2]!=b"MZ" or len(blob)<0x40:
        raise ValueError("Windows DOS/PE signature missing")
    offset=struct.unpack_from("<I",blob,0x3c)[0]
    if offset<64 or offset>min(len(blob)-0x40,32768):
        raise ValueError("unsafe Windows PE header offset")
    if blob[offset:offset+4]!=b"PE\0\0":
        raise ValueError("native Windows PE signature absent")
    machine,sections,_,_,_,optional_size,flags=struct.unpack_from(
        "<HHIIIHH",blob,offset+4,
    )
    if machine!=0x8664 or not 1<=sections<=96 or optional_size<112:
        raise ValueError("Windows binary is not supported native x86_64")
    if not flags&0x0002:
        raise ValueError("Windows PE image is not marked executable")
    optional=offset+24
    if optional+optional_size>len(blob):
        raise ValueError("truncated native Windows optional PE header")
    magic=struct.unpack_from("<H",blob,optional)[0]
    if magic!=0x20b:
        raise ValueError("Windows image is not PE32+")
    entry=struct.unpack_from("<I",blob,optional+16)[0]
    image_size=struct.unpack_from("<I",blob,optional+56)[0]
    if not entry or image_size<4096 or image_size>128_000_000:
        raise ValueError("Windows executable entry point or image bounds invalid")
    table=optional+optional_size
    if table+sections*40>len(blob):
        raise ValueError("truncated native Windows section table")
    return "PE32+ x86_64 native executable; runtime not verified"


def _compile_windows_game(spec:ProductionRequest,*,authorized:bool,
                          timeout_seconds:int=45)->tuple[bytes,dict]:
    if authorized is not True:
        raise PermissionError("explicit original Windows executable build authorization required")
    if type(timeout_seconds) is not int or not 5<=timeout_seconds<=120:
        raise ValueError("invalid native Windows cross-build time budget")
    spec.validate()
    if (spec.targets!=("pc_windows",) or spec.style!="fixed_screen_puzzle" or
            spec.compile_roms or spec.require_compiled):
        raise ValueError("bounded original Windows C99 puzzle request required")
    compiler=shutil.which(TOOL)
    if compiler is None:
        raise EnvironmentError("independent MinGW-w64 cross-compiler not installed")
    project=_render(spec,"pc_windows")
    source,_=make_source_release(project,spec)
    proof_receipt,inventory=_puzzle_proof(source)
    evidence=json.loads(inventory["dragon-puzzle-proof.json"])
    with TemporaryDirectory(prefix="dragon-original-win64-") as folder:
        root=Path(folder)
        for name in REQUIRED_SOURCE_FILES:
            file=root/_path(name)
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(inventory[name],encoding="utf-8")
        result=subprocess.run(
            [compiler,*ARGS],cwd=root,
            env={"PATH":os.environ.get("PATH",""),"HOME":str(root),"LC_ALL":"C"},
            stdin=subprocess.DEVNULL,capture_output=True,text=True,
            timeout=timeout_seconds,check=False,
        )
        if result.returncode!=0:
            raise RuntimeError("original Win64 compiler failed: "+(
                result.stderr or result.stdout or "no compiler diagnostics")[:600])
        if len(result.stdout)+len(result.stderr)>16000:
            raise ValueError("native Win64 compiler evidence exceeded budget")
        exe=root/"dragon_game.exe"
        if exe.is_symlink() or not exe.is_file() or exe.stat().st_size>MAX_EXE:
            raise RuntimeError("native Windows compiler produced no bounded regular executable")
        blob=exe.read_bytes()
    identity=pe64_format(blob)
    receipt=WindowsBuildEvidence(
        schema=SCHEMA,request_id=spec.request_id,
        original_source_fingerprint=proof_receipt["source_fingerprint"],
        original_source_sha256=_hash(source),
        game_format=identity,
        windows_executable_sha256=_hash(blob),
        windows_executable_bytes=len(blob),
        cross_compiler=TOOL,fixed_compile_arguments=ARGS,
        shortest_grid_levels_replayed=evidence["stages"],
        host_execution_verified=False,windows_runtime_verified=False,
        user_rights_claim="original-homebrew attested; legal clearance unverified",
        evidence_scope=(
            "actual x86_64 PE binary structurally checked, original C source and "
            "optimal authored levels reverified; NO Windows runtime/gameplay validation"
        ),
    )
    output=BytesIO()
    with ZipFile(output,"w",ZIP_DEFLATED,compresslevel=9) as archive:
        archive.writestr(_zipinfo("source/native-source-release.zip"),source)
        archive.writestr(_zipinfo("binary/dragon_game.exe"),blob)
        archive.writestr(_zipinfo("windows-build-evidence.json"),_canonical(asdict(receipt)))
    package=output.getvalue()
    if len(package)>MAX_ARCHIVE:
        raise ValueError("Windows game source/executable package exceeds budget")
    verify_windows_executable(package)
    return package,asdict(receipt)


def verify_windows_executable(package:bytes)->dict:
    """Independent source/PE/receipt audit; never execute an untrusted Windows exe."""
    if not isinstance(package,bytes) or not 100<=len(package)<=MAX_ARCHIVE:
        raise ValueError("invalid original Windows game release")
    expected={
        "source/native-source-release.zip","binary/dragon_game.exe",
        "windows-build-evidence.json",
    }
    with ZipFile(BytesIO(package)) as archive:
        members=archive.infolist()
        names=[x.filename for x in members]
        if (len(names)!=3 or set(names)!=expected or
                any(x.flag_bits&1 or
                    ((x.external_attr>>16)&0o170000)==0o120000 or
                    x.file_size>MAX_EXE for x in members) or
                sum(x.file_size for x in members)>MAX_ARCHIVE):
            raise ValueError("unsafe or unexpected native Windows archive contents")
        source=archive.read("source/native-source-release.zip")
        exe=archive.read("binary/dragon_game.exe")
        record=json.loads(archive.read("windows-build-evidence.json"))
    proof,inventory=_puzzle_proof(source)
    stages=json.loads(inventory["dragon-puzzle-proof.json"])["stages"]
    if (not isinstance(record,dict) or record.get("schema")!=SCHEMA or
            not re.fullmatch(r"[a-f0-9]{64}",str(record.get("request_id",""))) or
            record.get("original_source_fingerprint")!=proof["source_fingerprint"] or
            record.get("original_source_sha256")!=_hash(source) or
            record.get("windows_executable_sha256")!=_hash(exe) or
            record.get("windows_executable_bytes")!=len(exe) or
            record.get("game_format")!=pe64_format(exe) or
            record.get("cross_compiler")!=TOOL or
            record.get("fixed_compile_arguments")!=list(ARGS) or
            record.get("shortest_grid_levels_replayed")!=stages or
            record.get("host_execution_verified") is not False or
            record.get("windows_runtime_verified") is not False or
            record.get("user_rights_claim")!=
                "original-homebrew attested; legal clearance unverified"):
        raise ValueError("Windows native source, PE or compiler evidence differs")
    return {
        "schema":SCHEMA,"status":"native_windows_PE_structurally_verified",
        "request_id":record["request_id"],
        "exe_sha256":record["windows_executable_sha256"],
        "levels_proven":stages,
        "windows_runtime_tested":False,
        "proof_limit":"built real PE, did not run Windows game",
    }


def publish_windows_game(spec:ProductionRequest,destination:Path,*,
                         authorized:bool)->dict:
    if authorized is not True:
        raise PermissionError("Windows native game publication not approved")
    path=Path(destination).expanduser().absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("symlinked original Win64 game output directory")
    if path.exists() and not path.is_dir():
        raise ValueError("Windows native release path is not a directory")
    package,evidence=_compile_windows_game(spec,authorized=True)
    name="dragon-original-win64-"+_hash(package)[:20]+".zip"
    path.mkdir(parents=True,exist_ok=True)
    _atomic_new(path/name,package)
    return {
        "schema":SCHEMA,"status":"native_windows_executable_cross_compiled",
        "filename":name,"sha256":_hash(package),
        "evidence":evidence,"windows_runtime_tested":False,
    }


def main(argv:list[str]|None=None)->int:
    from argparse import ArgumentParser
    parser=ArgumentParser(description="Original Windows 64-bit standalone game build")
    cmd=parser.add_subparsers(dest="command",required=True)
    build=cmd.add_parser("build")
    build.add_argument("--title",default="Original Dragon Windows Puzzle")
    build.add_argument("--seed",type=int,default=1)
    build.add_argument("--stages",type=int,default=4)
    build.add_argument("--difficulty",type=int,default=4)
    build.add_argument("--out",type=Path,required=True)
    build.add_argument("--attest-original-rights",action="store_true")
    build.add_argument("--authorize-cross-compile",action="store_true")
    audit=cmd.add_parser("verify")
    audit.add_argument("--archive",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=="verify":
        result=verify_windows_executable(args.archive.read_bytes())
    else:
        spec=ProductionRequest(
            title=args.title,seed=args.seed,style="fixed_screen_puzzle",
            targets=("pc_windows",),
            original_work_attested=args.attest_original_rights,
            portable_design=PortableGameDesign(
                stages=args.stages,difficulty=args.difficulty,
            ),
        )
        result=publish_windows_game(
            spec,args.out,authorized=args.authorize_cross_compile,
        )
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
