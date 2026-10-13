"""Real source-to-binary release builder for Dragon's standalone native puzzle.

Runs only from an explicit local/CI command with a strict allowlist:
native C99 CMake -> host executable -> native --selftest. Validates ELF,
Mach-O or PE magic, hashes exact source + artifact, produces a deterministic
ZIP and a provenance manifest. Does not run in HTTP requests or crawler work.
A passing selftest proves scripted level rules, NOT overall game enjoyment.
"""
from __future__ import annotations
from argparse import ArgumentParser
from dataclasses import asdict,dataclass
from hashlib import sha256
from pathlib import Path
from time import monotonic
from zipfile import ZIP_DEFLATED,ZipFile,ZipInfo
import json,os,platform,shutil,subprocess,sys

# Can run as a standalone Python file from an intentionally sparse checkout.
# Importing skeleton.ai's package initializer would pull in unrelated AI
# subsystems, defeating an offline/native-host isolated compilation pipeline.
if __package__:
    from .dragon_native_puzzle import emit_native_puzzle
else:
    from dragon_native_puzzle import emit_native_puzzle

RELEASE_NAME="dragon_game.exe" if sys.platform=="win32" else "dragon_game"
TARGETS={"linux":"pc_linux","windows":"pc_windows","darwin":"pc_macos"}
MAX_BINARY_BYTES=10_000_000
NATIVE_PASS="DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=4"

@dataclass(frozen=True)
class NativeRelease:
    schema:str
    host:str
    target:str
    game_style:str
    stage_count:int
    binary_format:str
    binary_sha256:str
    binary_size:int
    source_fingerprint:str
    source_file_count:int
    selftest_stdout_sha256:str
    selftest_stage_lines:int
    selftest_state:str
    artifact_zip_sha256:str
    artifact_zip_size:int
    claim_boundary:str="compiled executable + scripted native completion only; no player certification"

def host_target(system:str|None=None)->str:
    name=(system or platform.system()).lower()
    if name not in TARGETS:
        raise ValueError("Dragon native executable packaging supports Linux, Windows, and macOS")
    return TARGETS[name]

def format_for_bytes(binary:bytes,host:str)->str:
    if not isinstance(binary,bytes) or len(binary)<64 or len(binary)>MAX_BINARY_BYTES:
        raise ValueError("executable format or binary size invalid")
    if host=="linux" and binary.startswith(b"\x7fELF"):
        return "elf"
    if host=="windows" and binary[:2]==b"MZ":
        # PE header location is a little-endian DWORD at 0x3c.
        if len(binary)<128:
            raise ValueError("truncated native Windows executable")
        offset=int.from_bytes(binary[60:64],"little")
        if 64<=offset<=len(binary)-4 and binary[offset:offset+4]==b"PE\x00\x00":
            return "portable_executable"
    if host=="darwin" and binary[:4] in (
        bytes.fromhex("cffaedfe"),bytes.fromhex("feedfacf"),
        bytes.fromhex("cefaedfe"),bytes.fromhex("feedface"),
    ):
        return "mach_o"
    raise ValueError("binary does not match host executable format")

def _run(argv:list[str],*,root:Path,limit:int)->subprocess.CompletedProcess:
    if not 1<=len(argv)<=12 or not all(isinstance(v,str) for v in argv):
        raise ValueError("invalid native build invocation")
    return subprocess.run(argv,cwd=root,check=False,text=True,capture_output=True,
        timeout=limit,env={k:v for k,v in os.environ.items()
                           if k not in ("PYTHONPATH","LD_PRELOAD","DYLD_INSERT_LIBRARIES")})

def _zip_entry(name:str,body:bytes,*,executable:bool=False)->tuple[ZipInfo,bytes]:
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError("invalid native release archive member")
    info=ZipInfo(name,(1980,1,1,0,0,0))
    info.compress_type=ZIP_DEFLATED
    info.external_attr=((0o755 if executable else 0o644)<<16)
    info.create_system=3
    return info,body

def build_native_release(root:Path,*,title:str="Original Dragon Puzzle Quest")->NativeRelease:
    if not shutil.which("cmake"):
        raise RuntimeError("CMake compiler toolchain is missing")
    root=Path(root)
    if root.exists() and (root.is_symlink() or any(root.iterdir())):
        raise ValueError("native release output must be an empty regular directory")
    host=platform.system().lower()
    target=host_target(host)
    if not isinstance(title,str) or not 1<=len(title)<=100 or any(
        ord(ch)<32 or ord(ch)==127 for ch in title
    ):
        raise ValueError("invalid native release title")
    # Only this pure-stdlib puzzle generator is required. Source emitted
    # here is exactly the source compiled, hashed and embedded in the proof.
    seed=int.from_bytes(sha256(title.encode("utf-8")).digest()[:4],"big")
    written=emit_native_puzzle(seed=seed,stages=4,difficulty=4)
    root.mkdir(parents=True,exist_ok=True)
    for name,body in written.items():
        candidate=root/name
        if candidate.is_absolute() or ".." in Path(name).parts or not isinstance(body,str):
            raise ValueError("unsafe native release source entry")
        candidate.parent.mkdir(parents=True,exist_ok=True)
        candidate.write_text(body,encoding="utf-8")
    source_fingerprint=sha256(json.dumps(
        written,sort_keys=True,separators=(",",":"),ensure_ascii=True,
        allow_nan=False
    ).encode("utf-8")).hexdigest()
    build_dir=root/"build"
    started=monotonic()
    cfg=_run(["cmake","-S",str(root.resolve()),"-B",str(build_dir.resolve()),
              "-DCMAKE_BUILD_TYPE=Release"],root=root,limit=90)
    if cfg.returncode:
        raise RuntimeError("native CMake configure failure: "+cfg.stderr[-1400:])
    built=_run(["cmake","--build",str(build_dir.resolve()),"--config","Release",
                "--parallel","2"],root=root,limit=140)
    if built.returncode:
        raise RuntimeError("native C99 compilation failure: "+built.stderr[-1400:])
    options=[
        build_dir/RELEASE_NAME,
        build_dir/"Release"/RELEASE_NAME,
    ]
    candidates=[p for p in options if p.is_file() and not p.is_symlink()]
    if len(candidates)!=1:
        raise RuntimeError("expected exactly one native host executable")
    executable=candidates[0]
    binary=executable.read_bytes()
    kind=format_for_bytes(binary,host)
    smoke=_run([str(executable.resolve()),"--selftest"],root=root,limit=20)
    if smoke.returncode or NATIVE_PASS not in smoke.stdout:
        raise RuntimeError("native puzzle selftest failed: "+
                           (smoke.stdout+smoke.stderr)[-1400:])
    if smoke.stdout.count("PUZZLE_STAGE_PASS level=")!=4:
        raise RuntimeError("native puzzle did not complete exactly four levels")
    if monotonic()-started>260:
        raise RuntimeError("native release build exceeded bounded host time budget")
    selftest_sha=sha256(smoke.stdout.encode()).hexdigest()
    metadata={
        "schema":"skeleton.ai.dragon.native_binary_release.v1",
        "host":host,"target":target,"game_style":"fixed_screen_puzzle",
        "stage_count":4,"binary_format":kind,
        "binary_sha256":sha256(binary).hexdigest(),
        "binary_size":len(binary),"source_fingerprint":source_fingerprint,
        "source_file_count":len(written),
        "selftest_stdout_sha256":selftest_sha,
        "selftest_stage_lines":4,"selftest_state":"native_selftest_passed",
        "claim_boundary":"compiled executable + scripted native completion only; no player certification",
    }
    release=root/"dragon-native-release.zip"
    manifest=json.dumps(metadata,sort_keys=True,indent=2,ensure_ascii=True).encode()+b"\n"
    if len(manifest)>10000:
        raise RuntimeError("release evidence manifest unexpectedly large")
    with ZipFile(release,"w",compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for entry,body in (
            _zip_entry(RELEASE_NAME,binary,executable=True),
            _zip_entry("native-release.json",manifest),
            _zip_entry("README.txt",(
                "ORIGINAL DRAGON NATIVE PUZZLE\n"
                "Game: "+RELEASE_NAME+"\n"
                "Play W/A/S/D, U undo, R restart, N next level, Q quit.\n"
                "Self-test: "+RELEASE_NAME+" --selftest\n"
                "This is a compiled native C game, not a browser demo.\n"
                "The self-test proves scripted rules, not human review.\n"
            ).encode()),
        ):
            archive.writestr(entry,body)
    archive_size=release.stat().st_size
    if archive_size>MAX_BINARY_BYTES+40000:
        raise RuntimeError("native binary ZIP exceeds release budget")
    receipt=NativeRelease(**metadata,
                          artifact_zip_sha256=sha256(release.read_bytes()).hexdigest(),
                          artifact_zip_size=archive_size)
    (root/"dragon-native-release.json").write_text(
        json.dumps(asdict(receipt),sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return receipt

def main()->None:
    p=ArgumentParser(description="Compile and verify real native Dragon C99 game")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--title",default="Original Dragon Puzzle Quest")
    args=p.parse_args()
    receipt=build_native_release(args.out,title=args.title)
    print("DRAGON_NATIVE_RELEASE_PASS",receipt.target,receipt.binary_format,
          receipt.binary_sha256,receipt.artifact_zip_sha256)
    print("Native verification claim:",receipt.claim_boundary)

if __name__=="__main__":
    main()
