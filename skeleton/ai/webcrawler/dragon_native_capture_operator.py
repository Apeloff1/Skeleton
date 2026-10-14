"""Build, execute and package original native graphical game footage.

This operator-only pipeline compiles a real SDL2 desktop executable, runs
the original generated C99 puzzle gameplay on a local Linux host with the
headless software renderer, and captures three actual BMP frames per stage.
It never watches the user's screen or records third-party commercial games.
The original source and per-frame contents are verified before release.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile,ZIP_DEFLATED
import json,os,re,shlex,shutil,struct,subprocess,sys

from .dragon_native_production import (
    ProductionRequest,_render,_path,_hash,_canonical,_zipinfo,
    _atomic_new,make_source_release,
)
from .dragon_native_desktop import (
    _puzzle_proof,_elf_format,_invoke,MAX_CAPTURE,
)

SCHEMA="skeleton.ai.dragon.original_gameplay_capture.v1"
MAX_FRAMES=24
MAX_FRAME=2_000_000
MAX_PACKAGE=16_000_000
MAX_EXPANDED=55_000_000
CAPTURE_PATTERN=re.compile(r"frames/level-(0[1-8])-frame-(0[0-2])\.bmp\Z")
LINE_PATTERN=re.compile(
    r"DRAGON_SDL_FRAME level=([1-8]) phase=([0-2]) moves=([0-9]{1,4}) digest=([a-f0-9]{8})\Z"
)

@dataclass(frozen=True)
class NativeCaptureFrame:
    stage:int
    phase:int
    name:str
    sha256:str
    byte_count:int
    reported_state_digest:str
    reported_moves:int


def _bitmap(raw:bytes)->None:
    """Reject fake BMPs/oversized frames and ensure actual 640x480 pixels."""
    if not isinstance(raw,bytes) or not 54<=len(raw)<=MAX_FRAME:
        raise ValueError("native gameplay frame outside bounded bitmap size")
    if raw[:2]!=b"BM":
        raise ValueError("native SDL2 frame lacks BMP signature")
    file_size=struct.unpack_from("<I",raw,2)[0]
    pixel_offset=struct.unpack_from("<I",raw,10)[0]
    dib_size=struct.unpack_from("<I",raw,14)[0]
    width,height=struct.unpack_from("<ii",raw,18)
    bit_depth=struct.unpack_from("<H",raw,28)[0]
    stride=((640*bit_depth+31)//32)*4
    if (file_size!=len(raw) or dib_size<40 or
            width!=640 or abs(height)!=480 or
            bit_depth not in (24,32) or
            pixel_offset<54 or pixel_offset>=len(raw) or
            pixel_offset+stride*480>len(raw)):
        raise ValueError("fake original gameplay bitmap dimensions or headers")


def _sdl_flags()->list[str]:
    if shutil.which("pkg-config") is None:
        raise EnvironmentError("SDL2 pkg-config is required for original game capture")
    result=subprocess.run(
        ["pkg-config","--cflags","--libs","sdl2"],
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10,
        check=False,
    )
    if result.returncode!=0 or len(result.stdout)>4096:
        raise EnvironmentError("SDL2 native development package not available")
    parsed=shlex.split(result.stdout.strip())
    allowed=("-I","-L","-l","-D","-pthread","-Wl,")
    if (not 1<=len(parsed)<=64 or
            any(not any(x.startswith(flag) for flag in allowed) or
                len(x)>300 or any(ch in x for ch in "\r\n\0")
                for x in parsed)):
        raise ValueError("SDL2 build flags exceed fixed allowlist")
    return parsed


def _capture_host()->None:
    if sys.platform!="linux":
        raise OSError("actual original SDL gameplay capture needs a trusted Linux build host")


def build_original_game_capture(spec:ProductionRequest,*,authorized:bool,
                                timeout_seconds:int=60)->tuple[bytes,dict]:
    if authorized is not True:
        raise PermissionError("original generated game capture requires local operator approval")
    _capture_host()
    if type(timeout_seconds) is not int or not 10<=timeout_seconds<=120:
        raise ValueError("native capture time budget must be between 10 and 120 seconds")
    spec.validate()
    if (spec.targets not in (("pc_linux",),("steam_deck",)) or
            spec.style!="fixed_screen_puzzle" or spec.compile_roms or spec.require_compiled):
        raise ValueError("SDL2 game capture is for admitted native original Linux puzzles")
    compiler=shutil.which("cc")
    if compiler is None:
        raise EnvironmentError("native C compiler not installed")
    extra=_sdl_flags()
    project=_render(spec,spec.targets[0])
    source,_=make_source_release(project,spec)
    original,inputs=_puzzle_proof(source)
    levels=json.loads(inputs["dragon-puzzle-proof.json"])["stages"]
    if not 1<=levels<=8:
        raise ValueError("original puzzle campaign has no bounded stages")
    with TemporaryDirectory(prefix="dragon-original-game-capture-") as temporary:
        root=Path(temporary)
        for name,body in project.files.items():
            destination=root/_path(name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(body,encoding="utf-8")
        argv=[compiler,"-std=c99","-O2","-Wall","-Wextra","-Wpedantic",
              "-Iinclude","src/graphics.c","-o","dragon_game_sdl",*extra]
        _invoke(argv,root=root,timeout=timeout_seconds)
        executable=root/"dragon_game_sdl"
        if executable.is_symlink() or not executable.is_file() or executable.stat().st_size>4_000_000:
            raise ValueError("native SDL2 game build emitted no verified executable")
        executable_bytes=executable.read_bytes()
        _elf_format(executable_bytes)
        frames_root=root/"frames"
        frames_root.mkdir()
        try:
            result=subprocess.run(
                [str(executable),"--capture-frames",str(frames_root)],
                cwd=root,env={
                    "PATH":os.environ.get("PATH",""),
                    "HOME":str(root),"LC_ALL":"C",
                    "SDL_VIDEODRIVER":"dummy","SDL_AUDIODRIVER":"dummy",
                },stdin=subprocess.DEVNULL,capture_output=True,text=True,
                timeout=timeout_seconds,check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("original game rendered frames exceeded time budget") from exc
        if result.returncode!=0 or len(result.stdout)+len(result.stderr)>MAX_CAPTURE:
            raise RuntimeError("native original game SDL2 pixel capture failed: "+
                               (result.stderr or result.stdout or "")[:500])
        lines=[line.strip() for line in result.stdout.splitlines() if line.strip()]
        if (len(lines)!=levels*3+1 or
                lines[-1]!=f"DRAGON_SDL_CAPTURE_PASS stages={levels} frames={levels*3}"):
            raise ValueError("actual game capture does not have all three stages of visual evidence")
        snapshots={}
        details=[]
        for index,line in enumerate(lines[:-1]):
            match=LINE_PATTERN.fullmatch(line)
            stage=index//3+1
            phase=index%3
            if not match or int(match[1])!=stage or int(match[2])!=phase:
                raise ValueError("game pixel capture frame order differs from gameplay")
            filename=f"frames/level-{stage:02d}-frame-{phase:02d}.bmp"
            disk=frames_root/filename.split("/")[-1]
            if disk.is_symlink() or not disk.is_file() or disk.stat().st_size>MAX_FRAME:
                raise ValueError("original game screenshot missing or unsafe")
            raw=disk.read_bytes()
            _bitmap(raw)
            snapshots[filename]=raw
            details.append(NativeCaptureFrame(
                stage,phase,filename,_hash(raw),len(raw),
                reported_state_digest=match[4],reported_moves=int(match[3]),
            ))
    receipt={
        "schema":SCHEMA,
        "target":spec.targets[0],
        "source_sha256":_hash(source),
        "source_fingerprint":original["source_fingerprint"],
        "native_sdl_binary_sha256":_hash(executable_bytes),
        "native_elf_format":_elf_format(executable_bytes),
        "capture_count":len(details),
        "stages":levels,
        "frames":[asdict(x) for x in details],
        "actual_original_game_renderer_executed":True,
        "verified_display_hardware":False,
        "scope":"locally executed original SDL2 software renderer, no user screen recording",
    }
    body=BytesIO()
    with ZipFile(body,"w",ZIP_DEFLATED,compresslevel=9) as archive:
        archive.writestr(_zipinfo("source/native-source-release.zip"),source)
        archive.writestr(_zipinfo("binary/dragon_game_sdl"),executable_bytes)
        for name in sorted(snapshots):
            archive.writestr(_zipinfo(name),snapshots[name])
        archive.writestr(_zipinfo("original-capture-evidence.json"),_canonical(receipt))
    package=body.getvalue()
    if len(package)>MAX_PACKAGE:
        raise ValueError("original game capture package exceeds compressed size budget")
    verify_original_capture(package)
    return package,receipt


def verify_original_capture(package:bytes)->dict:
    """Independent visual frame/source/binary hash replay; no archive execution."""
    if not isinstance(package,bytes) or not 100<=len(package)<=MAX_PACKAGE:
        raise ValueError("missing or unsafe native game capture archive")
    with ZipFile(BytesIO(package)) as archive:
        infos=archive.infolist()
        names=[entry.filename for entry in infos]
        if (len(names)!=len(set(names)) or len(names)<6 or len(names)>MAX_FRAMES+3 or
                any(x.flag_bits&1 or
                    ((x.external_attr>>16)&0o170000)==0o120000 or
                    x.file_size>4_000_000 for x in infos) or
                sum(x.file_size for x in infos)>MAX_EXPANDED):
            raise ValueError("original capture has unsafe or oversized members")
        receipt=json.loads(archive.read("original-capture-evidence.json"))
        source=archive.read("source/native-source-release.zip")
        binary=archive.read("binary/dragon_game_sdl")
        original,files=_puzzle_proof(source)
        proof=json.loads(files["dragon-puzzle-proof.json"])
        expected={"source/native-source-release.zip","binary/dragon_game_sdl",
                  "original-capture-evidence.json"}
        evidence=receipt.get("frames") if isinstance(receipt,dict) else None
        if (not isinstance(evidence,list) or len(evidence)!=proof["stages"]*3):
            raise ValueError("original game frame report incomplete")
        for sequence,item in enumerate(evidence):
            stage=sequence//3+1
            phase=sequence%3
            name=f"frames/level-{stage:02d}-frame-{phase:02d}.bmp"
            if not isinstance(item,dict) or item.get("name")!=name:
                raise ValueError("native frame ordering or name is not canonical")
            expected.add(name)
            raw=archive.read(name)
            _bitmap(raw)
            if (item.get("stage")!=stage or item.get("phase")!=phase or
                    item.get("sha256")!=_hash(raw) or
                    item.get("byte_count")!=len(raw) or
                    not re.fullmatch(r"[a-f0-9]{8}",
                                     str(item.get("reported_state_digest","")))):
                raise ValueError("original game rendered frame altered")
        if set(names)!=expected:
            raise ValueError("unrecognized user screen or foreign capture payload")
    if (receipt.get("schema")!=SCHEMA or
            receipt.get("target")!=original["target"] or
            receipt.get("source_sha256")!=_hash(source) or
            receipt.get("source_fingerprint")!=original["source_fingerprint"] or
            receipt.get("native_sdl_binary_sha256")!=_hash(binary) or
            receipt.get("native_elf_format")!=_elf_format(binary) or
            receipt.get("capture_count")!=proof["stages"]*3 or
            receipt.get("stages")!=proof["stages"] or
            receipt.get("actual_original_game_renderer_executed") is not True or
            receipt.get("verified_display_hardware") is not False):
        raise ValueError("native game capture source or executable evidence invalid")
    return {
        "schema":SCHEMA,"status":"original_game_frames_structurally_verified",
        "stages":proof["stages"],
        "frames_verified":len(evidence),
        "binary_sha256":_hash(binary),
        "scope":"original software renderer frames and host report, not certified video",
    }


def publish_original_capture(spec:ProductionRequest,destination:Path,*,
                             authorized:bool)->dict:
    if authorized is not True:
        raise PermissionError("local game footage publication requires approval")
    root=Path(destination).expanduser().absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("symlinked native video preview release destination")
    if root.exists() and not root.is_dir():
        raise ValueError("native game preview path not a directory")
    package,receipt=build_original_game_capture(spec,authorized=True)
    name="dragon-original-game-frames-"+_hash(package)[:20]+".zip"
    root.mkdir(parents=True,exist_ok=True)
    _atomic_new(root/name,package)
    return {"schema":SCHEMA,"status":"original_native_gameplay_frames_captured",
            "filename":name,"sha256":_hash(package),
            "frames":receipt["capture_count"],"stages":receipt["stages"]}


def main(argv:list[str]|None=None)->int:
    from argparse import ArgumentParser
    from .dragon_native_production import PortableGameDesign
    parser=ArgumentParser(description="Capture only Dragon original native SDL gameplay")
    build=parser.add_subparsers(dest="command",required=True)
    cmd=build.add_parser("capture")
    cmd.add_argument("--title",default="Original Dragon Gameplay Preview")
    cmd.add_argument("--seed",type=int,default=1)
    cmd.add_argument("--stages",type=int,default=3)
    cmd.add_argument("--difficulty",type=int,default=5)
    cmd.add_argument("--out",type=Path,required=True)
    cmd.add_argument("--attest-original-rights",action="store_true")
    cmd.add_argument("--authorize-local-capture",action="store_true")
    verify=build.add_parser("verify")
    verify.add_argument("--archive",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=="verify":
        report=verify_original_capture(args.archive.read_bytes())
    else:
        spec=ProductionRequest(
            title=args.title,style="fixed_screen_puzzle",
            targets=("pc_linux",),seed=args.seed,
            original_work_attested=args.attest_original_rights,
            portable_design=PortableGameDesign(stages=args.stages,
                                               difficulty=args.difficulty),
        )
        report=publish_original_capture(
            spec,args.out,authorized=args.authorize_local_capture,
        )
    print(json.dumps(report,sort_keys=True,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
