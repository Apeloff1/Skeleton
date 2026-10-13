"""Build a real original Atari Lynx cartridge with bounded compiler evidence.

This is an explicit operator/CI command, not a crawler-scheduled executable
or an automatic source-generated success claim. The package contains exact
source, binary, format check, provenance and no commercial game assets.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import argparse,json,os,shutil,subprocess

from .dragon_native_lynx import lynx_source

MAX_CARTRIDGE=1024*1024
MIN_CARTRIDGE=1024

@dataclass(frozen=True)
class LynxBuildReceipt:
    schema:str
    toolchain:str
    seed:int
    source_sha256:str
    cartridge_sha256:str
    cartridge_bytes:int
    lynx_header_magic:str
    lynx_header_version:int
    package_sha256:str
    package_bytes:int
    native_compiler_pass:bool=True
    emulator_controller_replay_pass:bool=False
    real_hardware_pass:bool=False
    physical_audio_verified:bool=False
    distribution_approved:bool=False

def _archive_member(name:str,payload:bytes)->tuple[ZipInfo,bytes]:
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError("unsafe Lynx package member path")
    info=ZipInfo(name,(1980,1,1,0,0,0))
    info.compress_type=ZIP_DEFLATED
    info.create_system=3
    info.external_attr=0o644<<16
    return info,payload

def build_lynx_cartridge(root:Path,*,seed:int=1989)->LynxBuildReceipt:
    if not shutil.which("cl65") or not shutil.which("make"):
        raise RuntimeError("real cc65 cl65 and GNU make required")
    source=lynx_source(seed)
    root=Path(root)
    if root.is_symlink() or (root.exists() and (
        not root.is_dir() or any(root.iterdir())
    )):
        raise ValueError("Lynx release directory must be empty and not a symlink")
    root.mkdir(parents=True,exist_ok=True)
    for relative,body in sorted(source.items()):
        destination=root/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(body,encoding="utf-8")
    cmd=["make","-C",str(root.resolve()),"all"]
    process=subprocess.run(cmd,capture_output=True,text=True,
        timeout=110,env={k:v for k,v in os.environ.items()
            if k not in ("LD_PRELOAD","DYLD_INSERT_LIBRARIES","PYTHONPATH")})
    if process.returncode:
        raise RuntimeError("Atari Lynx cc65 compile failed: "+
                           (process.stderr+process.stdout)[-1800:])
    cart_path=root/"build"/"dragon.lnx"
    if cart_path.is_symlink() or not cart_path.is_file():
        raise RuntimeError("Lynx cartridge file was not produced")
    binary=cart_path.read_bytes()
    if not MIN_CARTRIDGE<=len(binary)<=MAX_CARTRIDGE:
        raise ValueError("Lynx linked cartridge size outside bounded limits")
    if binary[:4]!=b"LYNX":
        raise ValueError("Lynx cartridge lacks standard LYNX header magic")
    if len(binary)<64:
        raise ValueError("Lynx header incomplete")
    version=int.from_bytes(binary[8:10],"little")
    if version not in (1,2):
        raise ValueError("Lynx cartridge header version unknown")
    code=source["src/main.c"].encode()
    meta={
      "schema":"skeleton.ai.dragon.native_lynx_build.v1",
      "toolchain":"cc65 cl65 -t lynx",
      "seed":seed,
      "source_sha256":sha256(code).hexdigest(),
      "cartridge_sha256":sha256(binary).hexdigest(),
      "cartridge_bytes":len(binary),
      "lynx_header_magic":"LYNX",
      "lynx_header_version":version,
      "native_compiler_pass":True,
      "emulator_controller_replay_pass":False,
      "real_hardware_pass":False,
      "physical_audio_verified":False,
      "distribution_approved":False
    }
    core_json=json.dumps(meta,sort_keys=True,indent=2).encode()+b"\n"
    out=root/"dragon-original-lynx.zip"
    with ZipFile(out,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        for entry,bytes_ in (
           _archive_member("dragon.lnx",binary),
           _archive_member("src/main.c",code),
           _archive_member("Makefile",source["Makefile"].encode()),
           _archive_member("source-compile-receipt.json",core_json),
           _archive_member("README.txt",(
             "Original Dragon Atari Lynx; independent CC65 native build."
             " Compile success does NOT imply emulator or hardware play."
             " Licensed game assets are not included.\n"
           ).encode()),
        ):
            z.writestr(entry,bytes_)
    receipt=LynxBuildReceipt(**meta,
        package_sha256=sha256(out.read_bytes()).hexdigest(),
        package_bytes=out.stat().st_size)
    (root/"dragon-lynx-release.json").write_text(
       json.dumps(asdict(receipt),sort_keys=True,indent=2)+"\n",
       encoding="utf-8")
    return receipt

def main()->None:
    parser=argparse.ArgumentParser(
       description="Build original native cc65 Lynx cartridge and source evidence")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=1989)
    a=parser.parse_args()
    receipt=build_lynx_cartridge(a.out,seed=a.seed)
    print("DRAGON_ORIGINAL_LYNX_BUILD_PASS",
          receipt.cartridge_sha256,receipt.package_sha256)
    print("Device and emulator verification: NOT CLAIMED")

if __name__=="__main__":
    main()
