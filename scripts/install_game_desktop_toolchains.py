"""Install pinned private operator tools for original game desktop/console builds.

Run explicitly on Linux AMD64. This downloads open-source build tools, not ROMs,
firmware, games or an external runtime. No tests or privileged installs run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

GO = {
    "version": "1.27.2",
    "url": "https://go.dev/dl/go1.27.2.linux-amd64.tar.gz",
    "sha256": "ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5",
    "filename": "go1.27.2.linux-amd64.tar.gz",
}
SDL = {
    "version": "2.32.4+dfsg-1",
    "url": "https://deb.debian.org/debian/pool/main/libs/libsdl2/libsdl2-dev_2.32.4+dfsg-1_amd64.deb",
    "sha256": "277dc6373473df2079ed44ac8661575b97b39fa263bfa424b0324c1501d21413",
    "filename": "libsdl2-dev.deb",
}
CC65_REPOSITORY = "https://github.com/cc65/cc65.git"
CC65_REVISION = "e47ac5060b28a8be899871c814644aa04d21c221"
RGBDS_REPOSITORY = "https://github.com/gbdev/rgbds.git"
RGBDS_REVISION = "6818759a8ca8cd11bf092aa052e2a992b52ac8e5"
RGBDS_DEPENDENCIES = (
    {
        "filename": "bison_3.8.2+dfsg-1+b2_amd64.deb",
        "url": "https://deb.debian.org/debian/pool/main/b/bison/bison_3.8.2+dfsg-1+b2_amd64.deb",
        "sha256": "ce6eb1f7aad18850e32d223a68f54bcbe756d74f138c8ec5460ad9d220f4d335",
    },
    {
        "filename": "m4_1.4.19-8_amd64.deb",
        "url": "https://deb.debian.org/debian/pool/main/m/m4/m4_1.4.19-8_amd64.deb",
        "sha256": "221b3e224708c1da2a1a88b6824380593579b2254ae7d914afa14cbd5d343334",
    },
    {
        "filename": "libpng-dev_1.6.48-1+deb13u5_amd64.deb",
        "url": "https://deb.debian.org/debian/pool/main/libp/libpng1.6/libpng-dev_1.6.48-1+deb13u5_amd64.deb",
        "sha256": "9027d5ace59ce266124c87054302805f49f9cb1ec4a6c8264a64596c7916fbff",
    },
)
MAX_ARCHIVE = 150 * 1024**2


def sha_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024**2):
            value.update(block)
    return value.hexdigest()


def download(root: Path, recipe: dict[str, str]) -> Path:
    destination = root / recipe["filename"]
    if destination.is_symlink():
        raise ValueError("Operator archive may not be a symlink")
    if not destination.exists():
        fd, name = tempfile.mkstemp(prefix=".download-", dir=root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                with urllib.request.urlopen(recipe["url"], timeout=60) as response:
                    total = 0
                    while block := response.read(1024**2):
                        total += len(block)
                        if total > MAX_ARCHIVE:
                            raise ValueError("Pinned tool archive exceeds its byte limit")
                        stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
            if sha_file(temporary) != recipe["sha256"]:
                raise ValueError("Downloaded operator archive differs from the pinned SHA-256")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    if not destination.is_file() or destination.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Operator archive must be a bounded regular file")
    if sha_file(destination) != recipe["sha256"]:
        raise ValueError("Existing archive differs from the pinned SHA-256")
    return destination


def private_root(value: str) -> Path:
    root = Path(value)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Operator root must be an absolute directory without a symlink")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if root.resolve() != root or root.stat().st_mode & 0o022:
        raise ValueError("Operator root must be canonical and not group/world writable")
    return root


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 600, env=None):
    return subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout)


def install_go(root: Path) -> dict:
    artifact = download(root, GO)
    destination = root / "go"
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix=".go-stage-", dir=root) as name:
            stage = Path(name)
            with tarfile.open(artifact) as archive:
                total = 0
                for member in archive.getmembers():
                    total += member.size
                    if total > 600 * 1024**2 or not member.name.startswith("go/"):
                        raise ValueError("Go archive has an unexpected layout or byte budget")
                    if member.issym() or member.islnk() or member.isdev():
                        raise ValueError("Pinned Go archive may contain only ordinary files/directories")
                archive.extractall(stage, filter="data")
            (stage / "go").replace(destination)
    if (
        destination.is_symlink()
        or (destination / "VERSION").read_text().splitlines()[0] != "go" + GO["version"]
    ):
        raise ValueError("Existing Go SDK does not match the pinned version")
    result = subprocess.run(
        [str(destination / "bin/go"), "version"], check=True, capture_output=True, text=True, timeout=15
    )
    binaries = [destination / "bin/go"] + [
        destination / "pkg/tool/linux_amd64" / name for name in ("compile", "link", "asm")
    ]
    return {
        "name": "go",
        **GO,
        "root": str(destination),
        "version_output": result.stdout.strip(),
        "tool_hashes": {str(path.relative_to(destination)): sha_file(path) for path in binaries},
        "license_path": str(destination / "LICENSE"),
    }


def install_sdl(root: Path) -> dict:
    artifact = download(root, SDL)
    destination = root / "sdl2"
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix=".sdl-stage-", dir=root) as name:
            stage = Path(name)
            run(["/usr/bin/dpkg-deb", "-x", str(artifact), str(stage)])
            stage.replace(destination)
    if destination.is_symlink() or not (destination / "usr/include/SDL2/SDL.h").is_file():
        raise ValueError("SDL SDK header layout is missing")
    library = Path("/lib/x86_64-linux-gnu/libSDL2-2.0.so.0")
    return {
        "name": "sdl2-dev",
        **SDL,
        "root": str(destination),
        "system_library": str(library),
        "system_library_sha256": sha_file(library) if library.is_file() else None,
        "status": "headers_and_runtime_present" if library.is_file() else "headers_present_runtime_missing",
        "license_path": str(destination / "usr/share/doc/libsdl2-dev/copyright"),
    }


def install_cc65(root: Path) -> dict:
    destination = root / "cc65"
    source = root / "cc65-source"
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("cc65 operator locations may not be symlinks")
    if not source.exists():
        run(["git", "clone", "--no-checkout", CC65_REPOSITORY, str(source)])
        run(["git", "checkout", "--detach", CC65_REVISION], cwd=source)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()
    if revision != CC65_REVISION:
        raise ValueError("cc65 source revision differs from the pinned commit")
    if not destination.exists():
        # Fetch retains operator proxy/CA settings; compilation receives no credentials.
        build_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        run(["make", "-j1"], cwd=source, env=build_env, timeout=900)
        run(["make", "install", "PREFIX=" + str(destination)], cwd=source, env=build_env)
    binaries = [destination / "bin" / name for name in ("cc65", "cl65", "ca65", "ld65", "od65", "ar65")]
    return {
        "name": "cc65",
        "repository": CC65_REPOSITORY,
        "revision": revision,
        "root": str(destination),
        "tool_hashes": {path.name: sha_file(path) for path in binaries},
        "license_path": str(source / "LICENSE"),
    }


def install_rgbds(root: Path) -> dict:
    destination, source, dependencies = root / "rgbds", root / "rgbds-source", root / "rgbds-deps"
    if any(path.is_symlink() for path in (destination, source, dependencies)):
        raise ValueError("RGBDS operator locations may not be symlinks")
    dependencies.mkdir(mode=0o700, exist_ok=True)
    for recipe in RGBDS_DEPENDENCIES:
        artifact = download(root, recipe)
        run(["/usr/bin/dpkg-deb", "-x", str(artifact), str(dependencies)])
    if not source.exists():
        run(["git", "clone", "--no-checkout", RGBDS_REPOSITORY, str(source)])
        run(["git", "checkout", "--detach", RGBDS_REVISION], cwd=source)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()
    if revision != RGBDS_REVISION:
        raise ValueError("RGBDS source revision differs from the pinned commit")
    if not destination.exists():
        environment = {
            "PATH": str(dependencies / "usr/bin") + ":/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "BISON_PKGDATADIR": str(dependencies / "usr/share/bison"),
            "M4": str(dependencies / "usr/bin/m4"),
        }
        run(
            [
                "make",
                "-j1",
                "CXXFLAGS=-O2 -DNDEBUG",
                "PNGCFLAGS=-I" + str(dependencies / "usr/include/libpng16"),
                "PNGLDFLAGS=-L/lib/x86_64-linux-gnu",
                "PNGLDLIBS=-l:libpng16.so.16",
            ],
            cwd=source,
            env=environment,
            timeout=900,
        )
        run(["make", "install", "PREFIX=" + str(destination)], cwd=source, env=environment)
    binaries = [destination / "bin" / name for name in ("rgbasm", "rgblink", "rgbfix", "rgbgfx")]
    return {
        "name": "rgbds",
        "repository": RGBDS_REPOSITORY,
        "revision": revision,
        "root": str(destination),
        "dependencies": RGBDS_DEPENDENCIES,
        "tool_hashes": {path.name: sha_file(path) for path in binaries},
        "license_path": str(source / "LICENSE"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Private absolute operator installation directory")
    parser.add_argument(
        "--cc65", action="store_true", help="Also compile pinned NES/C64/etc. cc65 assembler/compiler tools"
    )
    parser.add_argument(
        "--rgbds",
        action="store_true",
        help="Also compile pinned Game Boy RGBDS tools with private build headers",
    )
    args = parser.parse_args()
    os.umask(0o077)
    if os.uname().machine != "x86_64" or shutil.which("dpkg-deb") is None:
        parser.error("This pinned installer requires Linux AMD64 and dpkg-deb")
    root = private_root(args.root)
    results = [install_go(root), install_sdl(root)]
    if args.cc65:
        results.append(install_cc65(root))
    if args.rgbds:
        results.append(install_rgbds(root))
    sdk_roots = [str(root / "sdl2")]
    if args.cc65:
        sdk_roots.append(str(root / "cc65"))
    if args.rgbds:
        sdk_roots.append(str(root / "rgbds"))
    report = {
        "schema": "skeleton.game.operator_toolchains.v1",
        "downloads_are_build_tools_only": True,
        "tests_run": False,
        "tools": results,
        "configuration": {
            "SKL_GAME_GO_ROOT": str(root / "go"),
            "SKL_GAME_SDL2_SDK_ROOT": str(root / "sdl2"),
            "SKL_GAME_CONSOLE_SDK_ROOTS": json.dumps(sdk_roots),
        },
        "limitations": [
            "Browser-rendered desktop exports require a browser on the target OS",
            "SDL native builds require the matching system runtime",
            "Compilation does not prove execution on foreign operating systems",
        ],
    }
    (root / "desktop-toolchain-receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
