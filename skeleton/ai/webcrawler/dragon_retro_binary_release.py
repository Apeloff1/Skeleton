"""Compile and attest THREE distinct original native historical games.

Emits genuinely cross-compiled Atari 2600 6507 cartridge (DASM), Apple II
6502 ProDOS-loadable program (cc65), and 32-bit Win32 GDI executable
(MinGW i686). No console SDKs, firmware, copyrighted ROMs or BIOS.

This is a local, opt-in trusted operator CLI. It is never invoked
automatically by the crawler or browser. It emits SHA256-grounded binaries,
a deterministic ZIP of binaries+original source and a truthful receipt.
A passed compiler/format gate IS NOT an emulator or hardware certification.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
from argparse import ArgumentParser
import json,os,shutil,subprocess

from .dragon_native_legacy_expansion import native_legacy_source

TARGETS = ("atari_2600","apple_ii","windows_95")
OUTPUTS = {
    "atari_2600":"build/dragon.bin",
    "apple_ii":"build/dragon.bin",
    "windows_95":"build/dragon.exe",
}
COMPILERS = {
    "atari_2600":"dasm",
    "apple_ii":"cl65",
    "windows_95":"i686-w64-mingw32-gcc",
}
MAX_SOURCE=100_000
MAX_BINARY=2_000_000
MAX_BUNDLE=7_000_000

@dataclass(frozen=True)
class BinaryReceipt:
    schema:str
    target:str
    seed:int
    compiler:str
    compiler_signature_sha256:str
    source_manifest_sha256:str
    source_file_count:int
    artifact_name:str
    artifact_bytes:int
    artifact_sha256:str
    binary_format:str
    native_compiler_pass:bool
    emulator_gameplay_pass:bool=False
    physical_hardware_pass:bool=False
    legal_distribution_approved:bool=False
    scope:str="cross-compiled native binary and static format only"

def _sha(data:bytes)->str:
    return sha256(data).hexdigest()

def identify_binary(target:str,payload:bytes)->str:
    """Fail closed on spoofed extensions, malformed machines and empty files."""
    if target=="atari_2600":
        # 6507 mirrors ROM window $F000..$FFFF to the 4KiB address space.
        # Physical reset/IRQ vectors must point inside the 4KiB ROM window.
        if len(payload)!=4096:
            raise ValueError("Atari 2600 must be exactly one 4KiB bank")
        reset=int.from_bytes(payload[4092:4094],"little")
        irq=int.from_bytes(payload[4094:4096],"little")
        if not (0xF000<=reset<=0xFFFF and 0xF000<=irq<=0xFFFF):
            raise ValueError("Atari 2600 reset or IRQ vector outside cartridge")
        if payload[0] not in (0x78,0xD8): # SEI or CLD bootstrap
            raise ValueError("Atari 2600 entry is not an original startup")
        return "atari2600_6507_4k"
    if target=="apple_ii":
        # Apple II cc65 targets a headerless ProDOS loader program; do not
        # label raw cc65 bytes as a .dsk/.po or bootable disk filesystem.
        if not 256<=len(payload)<=65535:
            raise ValueError("Apple II linked ProDOS program invalid size")
        if payload[:4]==b"PK\x03\x04" or payload[:2]==b"MZ":
            raise ValueError("Apple II output is not a native 6502 program")
        return "apple2_prodos_loadable"
    if target=="windows_95":
        if not 512<=len(payload)<=MAX_BINARY or payload[:2]!=b"MZ":
            raise ValueError("Win32 program lacks valid DOS/PE envelope")
        pos=int.from_bytes(payload[0x3c:0x40],"little")
        if pos<0x40 or pos+0x60>len(payload) or payload[pos:pos+4]!=b"PE\x00\x00":
            raise ValueError("Win32 program lacks valid PE header")
        machine=int.from_bytes(payload[pos+4:pos+6],"little")
        option=int.from_bytes(payload[pos+24:pos+26],"little")
        subsystem=int.from_bytes(payload[pos+24+68:pos+24+70],"little")
        if machine!=0x14c or option!=0x10b or subsystem!=2:
            raise ValueError("Win95 source must produce PE32 Intel GUI binary")
        return "win32_i386_pe32_gui"
    raise ValueError("unsupported native historical release target")

def _member(name:str,blob:bytes)->tuple[ZipInfo,bytes]:
    p=PurePosixPath(name)
    if (not name or p.is_absolute() or "\\" in name or
        ".." in p.parts or p.as_posix()!=name or len(name)>200):
        raise ValueError("unsafe historical game archive path")
    zi=ZipInfo(name,(1980,1,1,0,0,0))
    zi.compress_type=ZIP_DEFLATED
    zi.create_system=3
    zi.external_attr=0o644<<16
    return zi,blob

def build_original_hardware(root:Path,*,seed:int=2600)->dict:
    """Build all three, or raise. No partial success receipt is generated."""
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("seed must be a uint32 integer")
    root=Path(root)
    if root.is_symlink() or (
        root.exists() and (not root.is_dir() or any(root.iterdir()))
    ):
        raise ValueError("native hardware release directory must be empty")
    for target,tool in COMPILERS.items():
        if not shutil.which(tool):
            raise RuntimeError("native compiler not installed: "+tool)
    if not shutil.which("make"):
        raise RuntimeError("GNU make required for actual cross-compile")
    root.mkdir(parents=True,exist_ok=True)
    signatures={}
    for target,tool in COMPILERS.items():
        # DASM sends its version to stderr and may use nonzero exit status
        # for a version-only invocation; record the exact observed signature.
        command=[tool,"--version"] if tool!="dasm" else [tool]
        p=subprocess.run(command,capture_output=True,text=True,timeout=15)
        v=(p.stdout+p.stderr).strip()
        if not v or len(v)>5000:
            raise RuntimeError("compiler signature unavailable: "+target)
        signatures[target]=_sha(v.encode())
    records=[]
    all_files={}
    for target in TARGETS:
        sources=native_legacy_source(target,seed)
        stage=root/target
        stage.mkdir()
        manifest={}
        for path,body in sorted(sources.items()):
            if type(body) is not str or not body or len(body.encode())>MAX_SOURCE:
                raise ValueError("unsafe original game source")
            safe=PurePosixPath(path)
            if safe.is_absolute() or ".." in safe.parts or "\\" in path:
                raise ValueError("unsafe original game source path")
            content=body.encode("utf-8")
            dest=stage/path
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(content)
            manifest[path]=_sha(content)
            all_files[f"{target}/source/{path}"]=content
        cmd=["make","-C",str(stage.resolve()),"all"]
        clean_env={k:v for k,v in os.environ.items() if k not in (
            "LD_PRELOAD","DYLD_INSERT_LIBRARIES","PYTHONPATH","PYTHONHOME",
            "MAKEFLAGS","MFLAGS")}
        try:
            run=subprocess.run(cmd,timeout=100,capture_output=True,text=True,
                               env=clean_env,check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("native historical compiler timed out: "+target) from exc
        if run.returncode:
            raise RuntimeError("native compiler failed for "+target+": "+
                               (run.stdout+run.stderr)[-1400:])
        output=stage/OUTPUTS[target]
        if output.is_symlink() or not output.is_file():
            raise RuntimeError("native compiler did not produce "+target+" binary")
        binary=output.read_bytes()
        if not 1<=len(binary)<=MAX_BINARY:
            raise ValueError("native game output exceeds size budget")
        kind=identify_binary(target,binary)
        record=BinaryReceipt(
            schema="skeleton.ai.dragon.historical_compiled_artifact.v1",
            target=target,seed=seed,compiler=COMPILERS[target],
            compiler_signature_sha256=signatures[target],
            source_manifest_sha256=_sha(json.dumps(
                manifest,sort_keys=True,separators=(",",":")).encode()),
            source_file_count=len(manifest),
            artifact_name=OUTPUTS[target],
            artifact_bytes=len(binary),artifact_sha256=_sha(binary),
            binary_format=kind,native_compiler_pass=True,
        )
        records.append(asdict(record))
        all_files[f"{target}/{OUTPUTS[target]}"]=binary
    proof={
      "schema":"skeleton.ai.dragon.historical_native_bundle.v1",
      "targets":list(TARGETS),
      "source_and_binary_provenance":records,
      "compiler_pass_count":len(records),
      "emulator_controller_verified_count":0,
      "physical_hardware_verified_count":0,
      "distribution_approval_count":0,
      "claim_boundary":"actual native compiler/linker and static format only",
    }
    proof_bytes=(json.dumps(proof,sort_keys=True,indent=2)+"\n").encode()
    all_files["release-evidence.json"]=proof_bytes
    all_files["README.txt"]=(
      b"Original Dragon native hardware homebrew compiled with local cross "
      b"toolchains. These source and binary hashes evidence compiler success "
      b"only, not 2600 timing, Apple II ProDOS boot, Windows 95 compatibility, "
      b"controller play, audio, intellectual property or release approval.\n")
    zip_file=root/"dragon-original-hardware-compiled.zip"
    with ZipFile(zip_file,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        for path,body in sorted(all_files.items()):
            z.writestr(*_member(path,body))
    if zip_file.stat().st_size>MAX_BUNDLE:
        raise ValueError("historical game package exceeded bounded limit")
    envelope={
      "schema":"skeleton.ai.dragon.historical_release_envelope.v1",
      "records":records,
      "archive_sha256":_sha(zip_file.read_bytes()),
      "archive_size":zip_file.stat().st_size,
      "evidence_sha256":_sha(proof_bytes),
      "source_binaries_in_archive":len(records),
      "gameplay_playtested":False,
      "device_compatible":False,
      "release_approved":False,
    }
    (root/"dragon-original-hardware-compiled.json").write_text(
        json.dumps(envelope,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return envelope

def main()->None:
    ap=ArgumentParser(description="Build signed-by-hash historical native games")
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--seed",type=int,default=2600)
    args=ap.parse_args()
    result=build_original_hardware(args.out,seed=args.seed)
    print("DRAGON_HISTORICAL_NATIVE_BUILD_PASS",result["archive_sha256"])
    for r in result["records"]:
        print(r["target"],r["artifact_bytes"],r["artifact_sha256"])
    print("Emulator/device/legal distribution approval: NOT CLAIMED")

if __name__=="__main__":
    main()
