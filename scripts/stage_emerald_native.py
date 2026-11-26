"""Stage reviewed Emerald Unreal and GLB assets offline, without executing any archive content."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "frontend/src/features/Jeeves/companion/emeraldAssetPin.json"
TARGET = ROOT / "artifacts/emerald/native-v1"
PREFIX = "emerald-atelier-fold/"
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILE = 80 * 1024 * 1024
SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")

def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def check(path: Path, size: int, expected: str) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size or sha(path) != expected:
        raise ValueError("native input identity mismatch: " + path.name)

def member(name: str) -> PurePosixPath:
    if not name.startswith(PREFIX) or "\\" in name:
        raise ValueError("unexpected archive root")
    suffix = name[len(PREFIX):]
    p = PurePosixPath(suffix)
    if not suffix or p.is_absolute() or any(part in (".", "..") or not SAFE_NAME.fullmatch(part) for part in suffix.split("/")):
        raise ValueError("unsafe native member")
    return p

def verify_model(path: Path, pin: dict) -> None:
    check(path, pin["modelBytes"], pin["modelSha256"])
    with path.open("rb") as f:
        header = f.read(12)
        if header[:8] != b"glTF\x02\x00\x00\x00" or int.from_bytes(header[8:12],"little") != pin["modelBytes"]:
            raise ValueError("invalid GLB identity")
        size = int.from_bytes(f.read(4),"little")
        if size <= 0 or size > 32 * 1024 * 1024 or f.read(4) != b"JSON":
            raise ValueError("invalid GLB JSON chunk")
        gltf = json.loads(f.read(size))
    if len(gltf.get("animations",[])) != 380 or max((len(s.get("joints",[])) for s in gltf.get("skins",[])), default=0) != 108:
        raise ValueError("unexpected skeleton or animation contract")
    if any("uri" in b for b in gltf.get("buffers",[])) or any("uri" in i for i in gltf.get("images",[])):
        raise ValueError("external model dependencies are forbidden")

def stage(source: Path, model: Path, target: Path, pin: dict) -> None:
    check(source,pin["sourceBytes"],pin["sourceSha256"])
    verify_model(model,pin)
    if target.exists() or target.is_symlink():
        raise ValueError("native destination already exists; choose a clean deployment directory")
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".native-stage-",dir=target.parent))
    try:
        total = 0
        seen = set()
        with zipfile.ZipFile(source) as z:
            if len(z.infolist()) > 512:
                raise ValueError("too many archive entries")
            for entry in z.infolist():
                rel = member(entry.filename)
                key = rel.as_posix().casefold()
                mode = (entry.external_attr >> 16) & 0o170000
                if key in seen or mode not in (0,0o100000) or entry.is_dir() or entry.flag_bits & 1:
                    raise ValueError("unsafe or duplicate native archive member")
                seen.add(key);total += entry.file_size
                if entry.file_size > MAX_FILE or total > MAX_TOTAL:
                    raise ValueError("native archive quota exceeded")
                # Never extract caches, executables, saved receipts or unrelated analysis artifacts.
                if rel.parts[0] not in ("Art","Models","PaintKit","Unreal") or any(x in ("__pycache__","Saved","Binaries","Intermediate") for x in rel.parts):
                    continue
                if rel.suffix.lower() not in (".png",".gif",".json",".md",".npz",".glb",".ini",".uproject",".cs",".h",".cpp",".py",".ps1"):
                    continue
                destination = tmp.joinpath(*rel.parts)
                if destination == tmp / "Models/emerald_continuum.glb":
                    raise ValueError("unexpected embedded model")
                destination.parent.mkdir(parents=True,exist_ok=True)
                with z.open(entry) as src,destination.open("xb") as dst:
                    copied = 0
                    while block := src.read(1024*1024):
                        copied += len(block)
                        if copied > entry.file_size:
                            raise ValueError("native member overflow")
                        dst.write(block)
                    if copied != entry.file_size:
                        raise ValueError("native member truncated")
        shutil.copyfile(model,tmp/"Models/emerald_continuum.glb")
        verify_model(tmp/"Models/emerald_continuum.glb",pin)
        manifest = json.loads((tmp/"Models/manifest.json").read_text(encoding="utf-8"))
        if manifest.get("sha256") != pin["modelSha256"]:
            raise ValueError("native model manifest mismatch")
        for path in ("Unreal/EmeraldCrawler.uproject","Unreal/Tools/qualify.ps1","Unreal/Tools/build_unreal.ps1","Unreal/Tools/import_reference_volume.py","Art/basecolor.png","Art/normal.png","Art/orm.png"):
            if not (tmp/path).is_file():
                raise ValueError("missing native dependency: "+path)
        receipt = {"schema":1,"model_sha256":pin["modelSha256"],"source_sha256":pin["sourceSha256"],"equipment_enabled":False,"engine_compiled":False,"physical_rtx_verified":False,"artist_approved":False}
        (tmp/"skeleton_stage_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
        if target.exists() or target.is_symlink():
            raise ValueError("concurrent native installation")
        os.rename(tmp,target)
    finally:
        shutil.rmtree(tmp,ignore_errors=True)

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path);parser.add_argument("model",type=Path)
    args=parser.parse_args()
    stage(args.source,args.model,TARGET,json.loads(PIN.read_text(encoding="utf-8"))["native"])
    print("Staged native experiment. Compilation and RTX execution have NOT been qualified.")

if __name__=="__main__":
    main()
