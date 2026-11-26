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

from recover_emerald_assets import copy_exact
from dragon_atelier_admit import inspect_glb, verify_peak_receipt

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "frontend/src/features/Jeeves/companion/emeraldAssetPin.json"
TARGET = ROOT / "artifacts/emerald/native-v1"
PREFIX = "emerald-atelier-fold/"
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILE = 80 * 1024 * 1024
SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
RESERVED = {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}

def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def member(name: str) -> PurePosixPath:
    if not name.startswith(PREFIX) or "\\" in name:
        raise ValueError("unexpected archive root")
    suffix = name[len(PREFIX):]
    p = PurePosixPath(suffix)
    if not suffix or p.is_absolute() or any(part in (".", "..") or not SAFE_NAME.fullmatch(part) for part in suffix.split("/")):
        raise ValueError("unsafe native member")
    if len(suffix) > 512 or any(part.endswith(".") or part.split(".")[0].upper() in RESERVED for part in p.parts):
        raise ValueError("unsafe Windows native member")
    return p

def verify_model(path: Path, pin: dict) -> None:
    verify_peak_receipt(inspect_glb(path, pin["modelSha256"]), pin)

def stage(source: Path, model: Path, target: Path, pin: dict) -> None:
    if os.path.lexists(target):
        raise ValueError("native destination already exists; choose a clean deployment directory")
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".native-stage-",dir=target.parent))
    try:
        # A private exact-byte snapshot prevents hash-then-reopen substitution.
        snapshot = tmp / ".source-custody.zip"
        copy_exact(source, snapshot, pin["sourceBytes"], pin["sourceSha256"])
        total = 0
        seen = set()
        with zipfile.ZipFile(snapshot) as z:
            if len(z.infolist()) > 512:
                raise ValueError("too many archive entries")
            for entry in z.infolist():
                mode = (entry.external_attr >> 16) & 0o170000
                if entry.flag_bits & 1:
                    raise ValueError("encrypted native archive member")
                if entry.is_dir():
                    if mode not in (0,0o040000) or entry.file_size != 0:
                        raise ValueError("unsafe directory entry")
                    if entry.filename == PREFIX:
                        continue
                    rel = member(entry.filename[:-1])
                    key = rel.as_posix().casefold()
                    if key in seen: raise ValueError("duplicate native archive member")
                    seen.add(key)
                    continue
                rel = member(entry.filename)
                key = rel.as_posix().casefold()
                if key in seen or mode not in (0,0o100000):
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
        snapshot.unlink()
        output_model = tmp/"Models/emerald_continuum.glb"
        if not output_model.parent.is_dir():
            raise ValueError("native source Models directory missing")
        copy_exact(model,output_model,pin["modelBytes"],pin["modelSha256"])
        verify_model(output_model,pin)
        manifest_path = tmp/"Models/manifest.json"
        if not manifest_path.is_file() or manifest_path.stat().st_size > 1024*1024:
            raise ValueError("missing or oversized model manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("sha256") != pin["modelSha256"]:
            raise ValueError("native model manifest mismatch")
        for path in ("Unreal/EmeraldCrawler.uproject","Unreal/Tools/qualify.ps1","Unreal/Tools/build_unreal.ps1","Unreal/Tools/import_reference_volume.py","Art/basecolor.png","Art/normal.png","Art/orm.png"):
            if not (tmp/path).is_file():
                raise ValueError("missing native dependency: "+path)
        inventory = []
        for path in sorted(tmp.rglob("*")):
            if path.is_file():
                inventory.append({"path":path.relative_to(tmp).as_posix(),"bytes":path.stat().st_size,"sha256":sha(path) if path != output_model else pin["modelSha256"]})
        receipt = {"schema":1,"files":inventory,"model_sha256":pin["modelSha256"],"source_sha256":pin["sourceSha256"],"equipment_enabled":False,"engine_compiled":False,"physical_rtx_verified":False,"artist_approved":False}
        (tmp/"skeleton_stage_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
        if os.path.lexists(target):
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
