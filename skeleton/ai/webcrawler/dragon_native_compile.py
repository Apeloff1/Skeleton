"""Opt-in native ROM compiler and format verifier for original source projects.

No subprocess runs during generation or web requests. This local CLI-only
step uses fixed argument vectors and a trusted installed toolchain. It
does NOT supply runtime network isolation; run on a separate restricted
runner if using it in an automated fleet. A header check is NOT equivalent
to an emulator/gameplay proof.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
from time import monotonic

from .dragon_native_projects import NativeProject

@dataclass(frozen=True)
class NativeBuildResult:
    target_id:str
    state:str
    binary_path:str
    binary_sha256:str
    bytes_written:int
    steps:int
    duration_seconds:float
    message:str

COMMANDS = {
    "game_boy":(
        ("rgbasm","-o","build/dragon.o","src/main.asm"),
        ("rgblink","-o","build/dragon.gb","build/dragon.o"),
        ("rgbfix","-v","-p","0","-t","DRAGONLAB","build/dragon.gb"),
    ),
    "game_boy_color":(
        ("rgbasm","-o","build/dragon.o","src/main.asm"),
        ("rgblink","-o","build/dragon.gbc","build/dragon.o"),
        ("rgbfix","-v","-p","0","-C","-t","DRAGONCGB","build/dragon.gbc"),
    ),
    "nes":(
        ("ca65","-o","build/dragon.o","src/main.s"),
        ("ld65","-C","nes.cfg","-o","build/dragon.nes","build/dragon.o"),
    ),
    "lynx":(
        ("cl65","-t","lynx","-O","-o","build/dragon.lnx","src/main.c"),
    ),
}
OUTPUTS={"game_boy":"build/dragon.gb","game_boy_color":"build/dragon.gbc","nes":"build/dragon.nes","lynx":"build/dragon.lnx"}

def _verify(target_id:str, blob:bytes)->bool:
    if target_id in ("game_boy","game_boy_color"):
        # Header, valid target ROM size and cartridge checksum. rgbfix inserts
        # the standard header; this checks byte-level structure not gameplay.
        if len(blob)<32768 or len(blob)%16384!=0:
            return False
        if target_id=="game_boy_color" and blob[0x143]!=0xC0:
            return False
        if target_id=="game_boy" and blob[0x143] not in (0,0x80):
            return False
        if blob[0x147] not in (0,1,2,3):
            return False
        checksum=0
        for b in blob[0x134:0x14D]:
            checksum=(checksum-b-1)&0xff
        return blob[0x14D]==checksum
    if target_id=="lynx":
        # Standard cc65 .lnx header: 64 bytes, LYNX magic, LE page size
        # and version. Content proof is structural only, not runtime play.
        if not 1024<=len(blob)<=524288+64 or blob[:4]!=b"LYNX":
            return False
        page=int.from_bytes(blob[4:6],"little")
        version=int.from_bytes(blob[8:10],"little")
        return page in (512,1024,2048) and version in (1,2)
    if target_id=="nes":
        if len(blob)<16 or blob[:4]!=b"NES\x1a":
            return False
        prg=blob[4]*16384
        chr=blob[5]*8192
        return prg==32768 and chr==8192 and len(blob)==16+prg+chr
    return False

def compile_local(project:NativeProject,root:Path,*,authorized:bool,
                  timeout_seconds:int=25)->NativeBuildResult:
    if not authorized:
        raise PermissionError("explicit native compilation permission required")
    if project.status!="source_generated" or project.target_id not in COMMANDS:
        raise ValueError("native compiler adapter not implemented")
    if not 5<=timeout_seconds<=120:
        raise ValueError("invalid compiler time budget")
    root=Path(root).resolve(strict=True)
    if any(not (root/p).is_file() or (root/p).is_symlink() for p in project.files):
        raise ValueError("native source tree is incomplete or contains symlinks")
    for p,data in project.files.items():
        if (root/p).read_text(encoding="utf-8")!=data:
            raise ValueError("source tree changed since template generation")
    for argv in COMMANDS[project.target_id]:
        if shutil.which(argv[0]) is None:
            return NativeBuildResult(project.target_id,"toolchain_missing","",
                                     "",0,0,0.0,argv[0]+" is not installed")
    (root/"build").mkdir(exist_ok=True)
    start=monotonic()
    for index,argv in enumerate(COMMANDS[project.target_id]):
        remain=timeout_seconds-(monotonic()-start)
        if remain<=0:
            return NativeBuildResult(project.target_id,"timed_out","",
                                     "",0,index,monotonic()-start,"toolchain timeout")
        try:
            result=subprocess.run(argv,cwd=root,env={
                "PATH":os.environ.get("PATH",""),
                "HOME":os.environ.get("HOME",""),
                "LC_ALL":"C",
            },capture_output=True,text=True,timeout=remain,check=False)
        except subprocess.TimeoutExpired:
            return NativeBuildResult(project.target_id,"timed_out","",
                                     "",0,index+1,monotonic()-start,"toolchain timeout")
        if result.returncode:
            return NativeBuildResult(project.target_id,"compile_failed","",
                                     "",0,index+1,monotonic()-start,
                                     (result.stderr or result.stdout or "compiler failed")[:1200])
    destination=root/OUTPUTS[project.target_id]
    if not destination.is_file() or destination.is_symlink():
        return NativeBuildResult(project.target_id,"missing_binary","",
                                 "",0,len(COMMANDS[project.target_id]),
                                 monotonic()-start,"compiler wrote no verified ROM")
    binary=destination.read_bytes()
    if len(binary)>2_000_000 or not _verify(project.target_id,binary):
        return NativeBuildResult(project.target_id,"invalid_binary","",
                                 "",0,len(COMMANDS[project.target_id]),
                                 monotonic()-start,"ROM header/size invalid")
    return NativeBuildResult(project.target_id,"compiled_native",str(destination),
                             sha256(binary).hexdigest(),len(binary),
                             len(COMMANDS[project.target_id]),
                             monotonic()-start,"Native ROM compiled; emulator playtest still required")
