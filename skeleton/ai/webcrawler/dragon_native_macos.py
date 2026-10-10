"""Build and execute actual original macOS C99 puzzle game on macOS hosts.

The output is a genuine Mach-O x86_64/ARM64 executable with independently
replayed original grid gameplay. This path is unavailable on Linux/Windows;
no fake cross-compiled macOS binary or developer SDK is included.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile,ZIP_DEFLATED
import json,os,platform,re,shutil,struct,subprocess,sys

from .dragon_native_production import (
    PortableGameDesign,ProductionRequest,_render,
    _path,_hash,_canonical,_zipinfo,_atomic_new,make_source_release,
)
from .dragon_native_desktop import (
    _puzzle_proof,_invoke,_selftest_stages,_hint_stages,REQUIRED_SOURCE_FILES,
)

SCHEMA="skeleton.ai.dragon.original_macos_executable.v1"
FLAGS=("-std=c99","-O2","-Wall","-Wextra","-Wpedantic",
       "-Iinclude","src/main.c","-o","dragon_game")
MACH64=0xfeedfacf
LC_MAIN=0x80000028
LC_UNIXTHREAD=5
MAX_EXE=4_000_000
MAX_PACKAGE=8_000_000


@dataclass(frozen=True)
class MacGameEvidence:
    schema:str
    target:str
    source_fingerprint:str
    source_sha256:str
    executable_sha256:str
    executable_bytes:int
    architecture:str
    macho_format:str
    native_compile_flags:tuple[str,...]
    compiler_identity:str
    shortest_grid_proofs:int
    native_runtime_stages:int
    native_hint_stages:int
    independent_replays:int
    native_star_grades:int
    executable_output_sha256:str
    actual_macos_host_executed:bool
    macos_hardware_certified:bool
    legal_scope:str


def macho64_format(blob:bytes)->str:
    """Check actual Mach-O 64-bit architecture, command bounds and entry."""
    if not isinstance(blob,bytes) or not 40<=len(blob)<=MAX_EXE:
        raise ValueError("original macOS native binary over budget or absent")
    if blob[:4]!=b"\xcf\xfa\xed\xfe":
        raise ValueError("not a 64-bit little-endian Mach-O executable")
    magic,cpu,subtype,kind,ncmds,commands_size,flags,reserved=struct.unpack_from(
        "<IIIIIIII",blob,0,
    )
    if magic!=MACH64 or cpu not in (0x01000007,0x0100000c) or kind!=2:
        raise ValueError("Mach-O file type or CPU architecture is unsupported")
    if not 1<=ncmds<=500 or not 8<=commands_size<=len(blob)-32:
        raise ValueError("unsafe Mach-O load command inventory")
    pos=32
    entry_found=False
    for _ in range(ncmds):
        if pos+8>len(blob):
            raise ValueError("truncated macOS load command")
        command,length=struct.unpack_from("<II",blob,pos)
        if length<8 or pos+length>len(blob) or pos+length>32+commands_size:
            raise ValueError("Mach-O load command crosses validated size")
        if command in (LC_MAIN,LC_UNIXTHREAD):
            entry_found=True
        pos+=length
    if pos!=32+commands_size or not entry_found:
        raise ValueError("Mach-O executable is missing valid bounded entry commands")
    arch="arm64" if cpu==0x0100000c else "x86_64"
    return "Mach-O 64-bit "+arch+" executable; source and host runtime tested"


def _local_host() -> str:
    if sys.platform!="darwin":
        raise OSError("real macOS original game builds require a macOS runner")
    arch=platform.machine().lower()
    if arch not in ("arm64","x86_64"):
        raise OSError("unrecognized native macOS host CPU architecture")
    return arch


def build_native_macos_game(spec:ProductionRequest,*,authorized:bool,
                            timeout_seconds:int=60)->tuple[bytes,dict]:
    if authorized is not True:
        raise PermissionError("operator must authorize original macOS game compilation")
    arch=_local_host()
    if type(timeout_seconds) is not int or not 5<=timeout_seconds<=120:
        raise ValueError("native macOS build timeout must be bounded")
    spec.validate()
    if (spec.targets!=("pc_macos",) or spec.style!="fixed_screen_puzzle" or
            spec.compile_roms or spec.require_compiled):
        raise ValueError("only original macOS C99 puzzle games have a native build adapter")
    compiler=shutil.which("cc")
    if not compiler:
        raise EnvironmentError("trusted macOS C compiler is unavailable")
    project=_render(spec,"pc_macos")
    source,_=make_source_release(project,spec)
    proof_receipt,files=_puzzle_proof(source)
    proof=json.loads(files["dragon-puzzle-proof.json"])
    with TemporaryDirectory(prefix="dragon-original-macos-") as temporary:
        root=Path(temporary)
        for name in REQUIRED_SOURCE_FILES:
            destination=root/_path(name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(files[name],encoding="utf-8")
        _invoke([compiler,*FLAGS],root=root,timeout=timeout_seconds)
        executable=root/"dragon_game"
        if (executable.is_symlink() or not executable.is_file() or
                executable.stat().st_size>MAX_EXE):
            raise ValueError("macOS native compiler did not produce an actual executable")
        binary=executable.read_bytes()
        identity=macho64_format(binary)
        if arch not in identity:
            raise ValueError("compiled Mach-O CPU does not match executing macOS host")
        completed=_invoke([str(executable),"--selftest"],root=root,timeout=timeout_seconds)
        _selftest_stages(completed.stdout,proof["stages"])
        hints=_invoke([str(executable),"--hint-selftest"],root=root,timeout=timeout_seconds)
        _hint_stages(hints.stdout,proof["stages"])
        grades=_invoke([str(executable),"--challenge-selftest"],root=root,
                       timeout=timeout_seconds)
        if (grades.stdout.count("PUZZLE_CHALLENGE_PASS level=")!=proof["stages"] or
                f'DRAGON_NATIVE_CHALLENGE PASS stages={proof["stages"]}' not in grades.stdout):
            raise ValueError("macOS compiled original game failed star-grade replay")
        from .dragon_native_puzzle import transformed_level,solve_grid
        from .dragon_native_puzzle_trace import simulate_grid,parse_native_state_line
        traces=[]
        for number in range(proof["stages"]):
            board=(tuple(proof["authored_level_rows"][number])
                   if proof.get("authoring_mode")=="authored" else
                   transformed_level(number,proof["seed"],proof["difficulty"],
                                     procedural=proof.get("procedural",False)))
            solution,_=solve_grid(board)
            for commands in (solution,"r"+solution,"su"+solution):
                expected=simulate_grid(board,commands,level=number+1)
                execution=_invoke(
                    [str(executable),"--simulate",str(number+1),commands],
                    root=root,timeout=timeout_seconds,
                )
                actual=parse_native_state_line(execution.stdout)
                if (actual["digest"]!=expected.digest or
                        actual["player"]!=expected.player or
                        actual["crates"]!=expected.crates or
                        actual["solved"]!=expected.solved):
                    raise ValueError("native macOS game physics differs from independent grid")
                traces.append(execution.stdout.strip())
    evidence=MacGameEvidence(
        schema=SCHEMA,target="pc_macos",
        source_fingerprint=proof_receipt["source_fingerprint"],
        source_sha256=_hash(source),
        executable_sha256=_hash(binary),executable_bytes=len(binary),
        architecture=arch,macho_format=identity,
        native_compile_flags=FLAGS,compiler_identity="macOS system cc",
        shortest_grid_proofs=proof["stages"],
        native_runtime_stages=proof["stages"],
        native_hint_stages=proof["stages"],
        independent_replays=len(traces),native_star_grades=proof["stages"],
        executable_output_sha256=_hash(_canonical(traces)),
        actual_macos_host_executed=True,
        macos_hardware_certified=False,
        legal_scope="operator-attested original source, not external license clearance",
    )
    archive=BytesIO()
    with ZipFile(archive,"w",ZIP_DEFLATED,compresslevel=9) as package:
        package.writestr(_zipinfo("source/native-source-release.zip"),source)
        package.writestr(_zipinfo("binary/dragon_game"),binary)
        package.writestr(_zipinfo("macos-build-evidence.json"),_canonical(asdict(evidence)))
    payload=archive.getvalue()
    if len(payload)>MAX_PACKAGE:
        raise ValueError("native macOS game output exceeds bounded artifact size")
    verify_native_macos_game(payload)
    return payload,asdict(evidence)


def verify_native_macos_game(package:bytes)->dict:
    """Structural audit of source/Mach-O/host report; no archive execution."""
    if not isinstance(package,bytes) or not 100<=len(package)<=MAX_PACKAGE:
        raise ValueError("native macOS release over budget or missing")
    expected={"source/native-source-release.zip","binary/dragon_game",
              "macos-build-evidence.json"}
    with ZipFile(BytesIO(package)) as archive:
        members=archive.infolist()
        if (len(members)!=3 or {x.filename for x in members}!=expected or
                any(x.flag_bits&1 or
                    ((x.external_attr>>16)&0o170000)==0o120000 or
                    x.file_size>MAX_EXE for x in members) or
                sum(x.file_size for x in members)>MAX_PACKAGE):
            raise ValueError("unsafe native macOS executable archive members")
        source=archive.read("source/native-source-release.zip")
        binary=archive.read("binary/dragon_game")
        report=json.loads(archive.read("macos-build-evidence.json"))
    native,inventory=_puzzle_proof(source)
    stages=json.loads(inventory["dragon-puzzle-proof.json"])["stages"]
    identity=macho64_format(binary)
    if (not isinstance(report,dict) or report.get("schema")!=SCHEMA or
            report.get("target")!="pc_macos" or native["target"]!="pc_macos" or
            report.get("source_fingerprint")!=native["source_fingerprint"] or
            report.get("source_sha256")!=_hash(source) or
            report.get("executable_sha256")!=_hash(binary) or
            report.get("executable_bytes")!=len(binary) or
            report.get("macho_format")!=identity or
            report.get("architecture") not in ("arm64","x86_64") or
            report["architecture"] not in identity or
            report.get("native_compile_flags")!=list(FLAGS) or
            report.get("compiler_identity")!="macOS system cc" or
            report.get("shortest_grid_proofs")!=stages or
            report.get("native_runtime_stages")!=stages or
            report.get("native_hint_stages")!=stages or
            report.get("independent_replays")!=stages*3 or
            report.get("native_star_grades")!=stages or
            not re.fullmatch(r"[a-f0-9]{64}",
                             str(report.get("executable_output_sha256",""))) or
            report.get("actual_macos_host_executed") is not True or
            report.get("macos_hardware_certified") is not False):
        raise ValueError("native original macOS source/runtime report failed verification")
    return {"schema":SCHEMA,"status":"macos_compiled_with_host_selftests",
            "architecture":report["architecture"],
            "executable_sha256":_hash(binary),"stages_replayed":stages,
            "scope":"host-reported executed C99 game; archive verification alone not secure provenance"}


def publish_macos_game(spec:ProductionRequest,destination:Path,*,
                       authorized:bool)->dict:
    if authorized is not True:
        raise PermissionError("macOS original game publication requires approval")
    root=Path(destination).expanduser().absolute()
    if any(path.is_symlink() for path in (root,*root.parents)):
        raise ValueError("symlinked native macOS game export directory")
    if root.exists() and not root.is_dir():
        raise ValueError("native macOS release path not a directory")
    bundle,receipt=build_native_macos_game(spec,authorized=True)
    name="dragon-original-macos-"+_hash(bundle)[:20]+".zip"
    root.mkdir(parents=True,exist_ok=True)
    _atomic_new(root/name,bundle)
    return {"status":"macos_host_game_built_and_tested","filename":name,
            "sha256":_hash(bundle),"evidence":receipt}


def main(argv:list[str]|None=None)->int:
    from argparse import ArgumentParser
    parser=ArgumentParser(description="Real original macOS standalone C99 game builder")
    sub=parser.add_subparsers(dest="command",required=True)
    build=sub.add_parser("build")
    build.add_argument("--title",default="Original Mac Dragon Puzzle")
    build.add_argument("--seed",type=int,default=1)
    build.add_argument("--stages",type=int,default=4)
    build.add_argument("--difficulty",type=int,default=4)
    build.add_argument("--attest-original-rights",action="store_true")
    build.add_argument("--authorize-local-build",action="store_true")
    build.add_argument("--out",type=Path,required=True)
    verify=sub.add_parser("verify")
    verify.add_argument("--archive",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=="verify":
        result=verify_native_macos_game(args.archive.read_bytes())
    else:
        request=ProductionRequest(
            title=args.title,style="fixed_screen_puzzle",
            targets=("pc_macos",),seed=args.seed,
            original_work_attested=args.attest_original_rights,
            portable_design=PortableGameDesign(stages=args.stages,
                                               difficulty=args.difficulty),
        )
        result=publish_macos_game(request,args.out,authorized=args.authorize_local_build)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
