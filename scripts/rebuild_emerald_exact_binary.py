"""Recover the original Fold GLB byte-for-byte from the retained source lineage.

Explicit offline operation. No new geometry, repinning, network, or engine execution.
Only reviewed export scripts from the exact measured archive hashes are invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from recover_emerald_assets import copy_exact
from emerald_asset_preflight import PIN

# These hashes identify the retained inputs used in the successful exact rebuild.
SOURCES = (
    ("emerald-apex-strain-aware.zip", "emerald-apex-strain", 244593548, "825ffc59a103179e948c87ca6be5a618a37306acfe2a6e64ec3d1353482b6498"),
    ("emerald-apex-gpu-surface-upgrade.zip", "emerald-apex-gpu", 34390132, "4161e7be63036431a7326e27ca5edb41e55f615beea473c74ca5364936197452"),
    ("emerald-apex-multilevel-upgrade.zip", "emerald-apex-multilevel", 86215635, "6ec842dffb658524b04c6fa40c91c2c01d73aec6215e96aa4d5d485752a2bfc8"),
    ("emerald-artisan-assets-and-unreal.zip", "emerald-atelier-artisan", 201787837, "2f2c3b3cadd01f440da55cc31e696b1fe7f948a1d096b5b4ebbdbce04167b054"),
    ("emerald-atelier-fold-source.zip", "emerald-atelier-fold", 194733639, "093feccb25846b39eefe94a4385873e25df125371544545042c3d34b3fe879f5"),
    ("emerald-apex-continuum.zip", "emerald-apex-continuum", 190413585, "03c78cb282cf4937fb88cffa3444deab360518c543d3f4769d0b26791550a42d"),
)
STAGES = (
    ("emerald-apex-gpu", "Tools/export_candidate.py", "Models/emerald_sculpt_candidate.glb", "8adfb562e6b784b97e57a42e11b5347ab26379526d09806b3a60d1adcdcbc433"),
    ("emerald-apex-multilevel", "Tools/export_flank_retained.py", "Models/emerald_flank_study.glb", "5535732fedb393f79f6b319bf60b7a5834691270276c4cade8d7972ce17e3ec9"),
    ("emerald-atelier-artisan", "Tools/export_artisan.py", "Models/emerald_continuum.glb", "95541717327877a5be79fb3531e79334d423398450069d3369d0f951ac51da86"),
    ("emerald-atelier-fold", "Tools/bake_fold.py", "Models/emerald_continuum.glb", "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a"),
)
BASE_SHA = "377153261f91a4815cc8e3ffa2e3b9bbb633b4c82ef544edcc1b71cbe3e5c8ed"
PARTS = (
    ("emerald_continuum.glb.part01", 240000000, "5390c55b74eec7b9018a4acd6450b000e1badca41c646bd11cbbf96bf0bfdb53"),
    ("emerald_continuum.glb.part02", 223149740, "1820fac333e166539ce89d328f03e7f7e2be4c0c72d0c9b990619f49323aea39"),
)
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024**3
MAX_MEMBER = 512 * 1024**2
MAX_ENTRIES = 8192
CHUNK = 1024**2


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def require_hash(path, expected):
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}: {actual}")
    return actual


def safe_extract(archive, work, dirname):
    """Bounded extraction of known exact archives into a private new workspace."""
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ENTRIES:
            raise ValueError("archive entry count")
        if sum(a.file_size for a in entries) > MAX_ARCHIVE_UNCOMPRESSED:
            raise ValueError("archive expansion quota")
        prefixed = all(a.filename.startswith(dirname + "/") for a in entries)
        root = work if prefixed else work / dirname
        seen = set()
        for a in entries:
            p = PurePosixPath(a.filename)
            parts = a.filename.split("/")
            if (p.is_absolute() or any(x in ("", ".", "..") or ":" in x or x.endswith((".", " ")) for x in parts)
                or "\\" in a.filename or a.is_dir() or a.flag_bits & 1
                or stat.S_IFMT(a.external_attr >> 16) not in (0, stat.S_IFREG)
                or not 0 <= a.file_size <= MAX_MEMBER):
                raise ValueError("unsafe retained archive entry")
            key = p.as_posix().casefold()
            if key in seen:
                raise ValueError("duplicate archive entry")
            seen.add(key)
            target = root.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(a) as src, target.open("xb") as out:
                remaining = a.file_size
                while remaining:
                    block = src.read(min(CHUNK, remaining))
                    if not block:
                        raise ValueError("truncated archive member")
                    out.write(block)
                    remaining -= len(block)
                if src.read(1):
                    raise ValueError("excess archive member bytes")


def patch_retained_normal(work):
    # The archived PNG is the exact old encoder output, not a newly encoded image.
    script = work / "emerald-apex-multilevel/Tools/export_flank.py"
    src = script.read_text(encoding="utf-8")
    start, end = src.index(" orig="), src.index(" src=")
    if end <= start or "normal_combined.png" not in src[start:end]:
        raise ValueError("unexpected flank exporter layout")
    new = src[:start] + " normal=ROOT/'Art/normal_combined.png';w,h=Image.open(ROOT/'Art/flank_normal_native.png').size\n" + src[end:]
    (script.parent / "export_flank_retained.py").write_text(new, encoding="utf-8")


def check_pin(pin):
    if pin["modelBytes"] != sum(x[1] for x in PARTS) or pin["modelSha256"] != STAGES[-1][3]:
        raise ValueError("original binary pin changed; independent review required")


def rebuild(directory, destination, pin):
    check_pin(pin)
    directory = Path(directory).absolute()
    destination = Path(destination).absolute()
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix="emerald-exact-rebuild-") as name:
        work = Path(name)
        for filename, dirname, size, expected in SOURCES:
            snapshot = work / filename
            copy_exact(directory / filename, snapshot, size, expected)
            safe_extract(snapshot, work, dirname)
            snapshot.unlink()
        require_hash(work / "emerald-apex-strain/Models/emerald_relief.glb", BASE_SHA)
        motion = work / "emerald-apex-strain/Motion"
        motion.mkdir(exist_ok=True)
        with (motion / "ground_choreography.json").open("xb") as output:
            with (work / "emerald-apex-continuum/Motion/ground_choreography.json").open("rb") as source:
                shutil.copyfileobj(source, output, CHUNK)
        patch_retained_normal(work)
        # Do not inherit Python module lookup or alternate baseline overrides.
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "HOME", "LD_LIBRARY_PATH"}}
        env.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONNOUSERSITE="1",
                   EMERALD_BASE=str(work / "emerald-apex-strain"))
        report = []
        for dirname, script, output, sha in STAGES:
            folder = work / dirname
            subprocess.run([sys.executable, str(folder / script)], cwd=folder,
                           env=env, check=True, timeout=300)
            model = folder / output
            require_hash(model, sha)
            report.append({"stage": dirname, "bytes": model.stat().st_size, "sha256": sha})
        copy_exact(model, destination, pin["modelBytes"], pin["modelSha256"])
    return report


def assemble(directory, destination, pin, parts=PARTS):
    """Concatenate only the exact transfer slices; validate each and the whole."""
    check_pin(pin)
    directory, destination = Path(directory), Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix="emerald-exact-assembly-") as name:
        root = Path(name)
        combined = root / "model.glb"
        with combined.open("xb") as out:
            for filename, size, sha in parts:
                snap = root / filename
                copy_exact(directory / filename, snap, size, sha)
                with snap.open("rb") as source:
                    shutil.copyfileobj(source, out, CHUNK)
                snap.unlink()
        copy_exact(combined, destination, pin["modelBytes"], pin["modelSha256"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("assemble", "rebuild"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))["native"]
    stages = rebuild(args.directory, args.output, pin) if args.mode == "rebuild" else []
    if args.mode == "assemble":
        assemble(args.directory, args.output, pin)
    print(json.dumps({"mode": args.mode, "model_bytes": pin["modelBytes"],
                      "sha256": pin["modelSha256"], "stages": stages,
                      "engine_compiled": False, "physical_rtx_verified": False,
                      "artist_approved": False, "release_qualified": False}, indent=2))


if __name__ == "__main__":
    main()
