"""Install pinned private operator tools for original game desktop/console builds.

Run explicitly on Linux AMD64. This downloads open-source build tools, not ROMs,
firmware, games or an external runtime. No tests or privileged installs run.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

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
MAX_EXPANDED = 600 * 1024**2
MAX_FILES = 32768
MAX_LOG = 4 * 1024**2
TOOLS = ("go", "sdl2", "cc65", "rgbds")
_CACHE: Path | None = None
_DOWNLOAD = False
_LOG: Path | None = None
_COMMANDS: list[dict] = []
_ACQUISITIONS: list[dict] = []


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_EXPANDED:
            raise ValueError("Toolchain input is not a bounded regular file")
        total = 0
        while block := stream.read(1024**2):
            total += len(block)
            if total > MAX_EXPANDED:
                raise ValueError("Toolchain input exceeds its byte budget")
            digest.update(block)
        after = os.fstat(stream.fileno())
        identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(
            path.stat(follow_symlinks=False)
        ):
            raise ValueError("Toolchain input changed while hashing")
    return digest.hexdigest()


def private_root(value: str) -> Path:
    root = Path(value)
    if (
        not re.fullmatch(r"/[A-Za-z0-9._/-]{1,4095}", value)
        or str(root) != value
        or not root.is_absolute()
        or root.is_symlink()
        or root.resolve() != root
    ):
        raise ValueError("Operator directory must be canonical and absolute, without symlinks")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.stat()
    if not root.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("Operator directory must be owned by this user and not group/world writable")
    return root


def clean_environment(*, network=False):
    result = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "SOURCE_DATE_EPOCH": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
    }
    if network:
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "CURL_CA_BUNDLE",
            "GIT_SSL_CAINFO",
        ):
            if key in os.environ:
                result[key] = os.environ[key]
    return result


def _stop(process):
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # A failed make/git parent may exit while a descendant still owns the
    # output pipe. Terminate the entire exclusively created process group.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=3)


def run(
    command: list[str],
    *,
    cwd=None,
    timeout=600,
    env=None,
    network=False,
    capture=False,
    file_limit=MAX_EXPANDED,
):
    if network and not _DOWNLOAD:
        raise ValueError("Network acquisition requires explicit --download")
    environment = clean_environment(network=network)
    if env:
        environment.update(env)
    _COMMANDS.append({"program": Path(command[0]).name, "network_acquisition": network})
    bounded = [
        "/usr/bin/prlimit",
        "--fsize=" + str(file_limit),
        "--as=" + str(4 * 1024**3),
        "--nofile=256",
        "--",
        *command,
    ]
    process = subprocess.Popen(
        bounded,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    captured = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command[0], timeout)
                for selected, _ in selector.select(timeout=min(0.2, max(0.001, deadline - time.monotonic()))):
                    chunk = os.read(selected.fd, 65536)
                    if not chunk:
                        selector.unregister(selected.fileobj)
                        continue
                    if capture:
                        captured.extend(chunk)
                        if len(captured) > 1024**2:
                            raise ValueError("Operator identity output exceeds its byte budget")
                    if _LOG is not None:
                        descriptor = os.open(
                            _LOG,
                            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                            0o600,
                        )
                        with os.fdopen(descriptor, "ab") as output:
                            details = os.fstat(output.fileno())
                            if (
                                not stat.S_ISREG(details.st_mode)
                                or details.st_uid != os.geteuid()
                                or details.st_mode & 0o077
                            ):
                                raise ValueError("Installation log must be a private operator regular file")
                            output.seek(0, os.SEEK_END)
                            remaining = max(0, MAX_LOG - output.tell())
                            output.write(chunk[:remaining])
        result = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if result:
            raise RuntimeError("Pinned operator command failed; inspect the private bounded installation log")
    finally:
        _stop(process)
        if process.stdout:
            process.stdout.close()
    return bytes(captured).decode("utf-8").strip() if capture else None


def archive(root: Path, recipe: dict) -> Path:
    cache = _CACHE or root
    destination = cache / recipe["filename"]
    if destination.is_symlink():
        raise ValueError("Cached archive cannot be a symlink")
    if not destination.exists():
        if not _DOWNLOAD:
            raise ValueError(
                "Pinned archive is absent from --cache-root; supply the exact offline artifact or explicitly use --download"
            )
        descriptor, temporary_name = tempfile.mkstemp(prefix=".download-", dir=cache)
        temporary = Path(temporary_name)
        deadline = time.monotonic() + 300
        try:
            with os.fdopen(descriptor, "wb") as stream:
                with urllib.request.urlopen(recipe["url"], timeout=20) as response:
                    total = 0
                    while chunk := response.read(1024**2):
                        total += len(chunk)
                        if total > MAX_ARCHIVE or time.monotonic() >= deadline:
                            raise ValueError("Pinned archive acquisition exceeds its byte/time budget")
                        stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if sha_file(temporary) != recipe["sha256"]:
                raise ValueError("Acquired archive differs from its exact pinned SHA256")
            os.link(temporary, destination)
            _ACQUISITIONS.append({"filename": recipe["filename"], "sha256": recipe["sha256"]})
        finally:
            temporary.unlink(missing_ok=True)
    if (
        not destination.is_file()
        or destination.stat().st_mode & 0o022
        or destination.stat().st_uid not in {0, os.geteuid()}
        or destination.stat().st_size > MAX_ARCHIVE
        or sha_file(destination) != recipe["sha256"]
    ):
        raise ValueError("Cached archive differs from its exact pinned identity")
    return destination


def extract_tar(artifact: Path, destination: Path, *, prefix=None):
    with tarfile.open(artifact) as handle:
        total = 0
        names = set()
        for index, member in enumerate(handle):
            name = member.name.removeprefix("./").rstrip("/")
            if not name and member.isdir():
                continue
            path = PurePosixPath(name)
            if (
                index >= MAX_FILES
                or path.is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))
                or "\\" in name
                or len(name) > 512
            ):
                raise ValueError("Pinned archive contains an unsafe path or excessive file count")
            if prefix and not (name == prefix or name.startswith(prefix + "/")):
                raise ValueError("Pinned archive differs from its declared root layout")
            if name in names:
                raise ValueError("Pinned archive repeats a path")
            names.add(name)
            total += member.size
            if total > MAX_EXPANDED or member.size > MAX_ARCHIVE:
                raise ValueError("Pinned archive expansion exceeds capacity")
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError("Pinned archive contains a non-ordinary member")
            if member.issym():
                target = (destination / name).parent / member.linkname
                if PurePosixPath(member.linkname).is_absolute() or not target.resolve().is_relative_to(
                    destination.resolve()
                ):
                    raise ValueError("Pinned archive alias escapes its installation root")
        handle.extractall(destination, filter="data")


def extract_deb(artifact: Path, destination: Path):
    with tempfile.TemporaryDirectory(prefix=".deb-", dir=destination.parent) as name:
        tree = Path(name)
        # dpkg-deb -x performs no package scripts. The input is an exact pinned
        # public .deb; the resulting tree is inventoried before publication.
        run(["/usr/bin/dpkg-deb", "-x", str(artifact), str(tree)], timeout=60)
        # Development packages include linker aliases to their separately
        # installed host runtime. They grant no mounted SDK authority here.
        for folder, directories, files in os.walk(tree, followlinks=False):
            for filename in [*directories, *files]:
                path = Path(folder) / filename
                if path.is_symlink() and (not path.exists() or not path.resolve().is_relative_to(tree)):
                    path.unlink()
        inventory(tree)
        shutil.copytree(tree, destination, dirs_exist_ok=True, symlinks=True)


def _git(args, directory, *, network=False):
    return run(
        [
            "/usr/bin/git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            *args,
        ],
        cwd=directory,
        network=network,
        capture=True,
    )


def source(root: Path, tool: str, repository: str, revision: str):
    cache = _CACHE or root
    checkout = cache / (tool + "-source")
    if checkout.is_symlink():
        raise ValueError("Source cache cannot be a symlink")
    if not checkout.exists():
        if not _DOWNLOAD:
            raise ValueError(
                "Pinned source cache is absent; provide --cache-root or explicitly select --download"
            )
        checkout.mkdir(mode=0o700)
        _git(["init", "--bare", "."], checkout)
        _git(["fetch", "--depth", "1", "--no-tags", repository, revision], checkout, network=True)
    if (
        checkout.resolve() != checkout
        or checkout.stat().st_uid != os.geteuid()
        or checkout.stat().st_mode & 0o022
    ):
        raise ValueError("Source cache must be a canonical operator-owned directory")
    observed = _git(["rev-parse", "--verify", revision + "^{commit}"], checkout)
    if observed != revision:
        raise ValueError("Source cache does not contain the exact pinned commit")
    _git(["fsck", "--strict", "--no-reflogs"], checkout)
    snapshot = root / (tool + "-source.tar")
    run(
        [
            "/usr/bin/git",
            "-c",
            "core.attributesFile=/dev/null",
            "archive",
            "--format=tar",
            "--output=" + str(snapshot),
            revision,
        ],
        cwd=checkout,
        timeout=60,
        file_limit=MAX_ARCHIVE,
    )
    if snapshot.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Pinned source archive exceeds capacity")
    destination = root / (tool + "-source")
    destination.mkdir(mode=0o700)
    extract_tar(snapshot, destination)
    return destination, {
        "repository": repository,
        "revision": revision,
        "source_archive_sha256": sha_file(snapshot),
    }


def inventory(root: Path):
    result, total = {}, 0
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in sorted([*directories, *files]):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if relative in (".skeleton-toolchain.json", ".skeleton-toolchain-manifest.json"):
                continue
            info = path.lstat()
            if (
                len(result) >= MAX_FILES
                or len(relative) > 512
                or (not path.is_symlink() and info.st_mode & 0o022)
            ):
                raise ValueError("Installed SDK exceeds trusted path/count/mode limits")
            if path.is_symlink():
                if not path.resolve(strict=True).is_relative_to(root.resolve()):
                    raise ValueError("Installed SDK alias escapes its root")
                result[relative] = {"kind": "symlink", "target": os.readlink(path)}
            elif path.is_dir():
                result[relative] = {"kind": "directory", "mode": stat.S_IMODE(info.st_mode)}
            elif path.is_file():
                total += info.st_size
                if total > MAX_EXPANDED:
                    raise ValueError("Installed SDK exceeds its aggregate byte budget")
                result[relative] = {
                    "kind": "file",
                    "bytes": info.st_size,
                    "mode": stat.S_IMODE(info.st_mode),
                    "sha256": sha_file(path),
                }
            else:
                raise ValueError("Installed SDK contains a non-ordinary file")
    return result


def _pin(tool):
    if tool == "go":
        return GO
    if tool == "sdl2":
        return SDL
    return {
        "repository": CC65_REPOSITORY if tool == "cc65" else RGBDS_REPOSITORY,
        "revision": CC65_REVISION if tool == "cc65" else RGBDS_REVISION,
    }


def _receipt_json(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_LOG:
            raise ValueError("SDK receipt must be a bounded ordinary file")
        raw = stream.read(MAX_LOG + 1)
    if len(raw) > MAX_LOG:
        raise ValueError("SDK receipt changed beyond its capacity")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("SDK receipt must contain a JSON object")
    if canonical(value) != raw:
        raise ValueError("SDK receipt must retain its exact finite canonical JSON identity")
    return value


def verify_install(root: Path, tool: str):
    destination = root / tool
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Installed SDK path must be an ordinary operator directory")
    receipt_path = destination / ".skeleton-toolchain.json"
    manifest_path = destination / ".skeleton-toolchain-manifest.json"
    if (
        not receipt_path.is_file()
        or not manifest_path.is_file()
        or receipt_path.stat().st_size > MAX_LOG
        or manifest_path.stat().st_size > MAX_LOG
    ):
        raise ValueError("Existing SDK lacks bounded immutable installation receipts; choose a fresh --root")
    receipt = _receipt_json(receipt_path)
    expected = _receipt_json(manifest_path)
    if (
        receipt.get("schema_version") != "skeleton.game.operator_toolchain.v2"
        or receipt.get("tool") != tool
        or receipt.get("pin") != _pin(tool)
    ):
        raise ValueError("Existing SDK receipt differs from the pinned selected tool")
    if (
        hashlib.sha256(canonical(expected)).hexdigest() != receipt.get("manifest_digest")
        or inventory(destination) != expected
    ):
        raise ValueError("Installed SDK bytes/paths/modes differ from its immutable receipt")
    return receipt


def install_one(root: Path, tool: str):
    destination = root / tool
    if destination.exists() or destination.is_symlink():
        return verify_install(root, tool)
    if shutil.disk_usage(root).free < 2 * 1024**3:
        raise ValueError("Provisioning requires at least 2 GiB free before private staging")
    command_start = len(_COMMANDS)
    with tempfile.TemporaryDirectory(prefix=".tool-stage-", dir=root) as name:
        stage = Path(name)
        sdk = stage / tool
        source_identity = None
        if tool == "go":
            extract_tar(archive(root, GO), stage, prefix="go")
            expected = "go" + GO["version"]
            if (sdk / "VERSION").read_text().splitlines()[0] != expected:
                raise ValueError("Pinned Go SDK version layout differs")
            tools = ["bin/go", *["pkg/tool/linux_amd64/" + part for part in ("compile", "link", "asm")]]
            license_path = "LICENSE"
        elif tool == "sdl2":
            sdk.mkdir(mode=0o700)
            extract_deb(archive(root, SDL), sdk)
            tools = ["usr/include/SDL2/SDL.h"]
            license_path = "usr/share/doc/libsdl2-dev/copyright"
        else:
            upstream, source_identity = source(stage, tool, _pin(tool)["repository"], _pin(tool)["revision"])
            environment = {}
            arguments = ["/usr/bin/make", "-j1"]
            if tool == "rgbds":
                dependencies = stage / "rgbds-deps"
                dependencies.mkdir(mode=0o700)
                for recipe in RGBDS_DEPENDENCIES:
                    extract_deb(archive(root, recipe), dependencies)
                environment = {
                    "PATH": str(dependencies / "usr/bin") + ":/usr/bin:/bin",
                    "BISON_PKGDATADIR": str(dependencies / "usr/share/bison"),
                    "M4": str(dependencies / "usr/bin/m4"),
                }
                arguments.extend(
                    [
                        "CXXFLAGS=-O2 -DNDEBUG",
                        "PNGCFLAGS=-I" + str(dependencies / "usr/include/libpng16"),
                        "PNGLDFLAGS=-L/lib/x86_64-linux-gnu",
                        "PNGLDLIBS=-l:libpng16.so.16",
                    ]
                )
            run(arguments, cwd=upstream, timeout=900, env=environment)
            run(
                ["/usr/bin/make", "install", "PREFIX=" + str(sdk)], cwd=upstream, timeout=180, env=environment
            )
            names = (
                ("cc65", "cl65", "ca65", "ld65", "od65", "ar65")
                if tool == "cc65"
                else ("rgbasm", "rgblink", "rgbfix", "rgbgfx")
            )
            tools = ["bin/" + item for item in names]
            license_path = "share/licenses/" + tool + "/LICENSE"
            (sdk / license_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(upstream / "LICENSE", sdk / license_path)
        if not (sdk / license_path).is_file():
            raise ValueError("Pinned SDK license notice is missing")
        actual = inventory(sdk)
        tool_hashes = {relative: sha_file(sdk / relative) for relative in tools}
        if tool != "sdl2" and any(not os.access(sdk / relative, os.X_OK) for relative in tools):
            raise ValueError("Installed tool is not an executable regular file")
        receipt = {
            "schema_version": "skeleton.game.operator_toolchain.v2",
            "tool": tool,
            "pin": _pin(tool),
            "source": source_identity,
            "created_at": datetime.now(UTC).isoformat(),
            "root": str(destination),
            "tool_hashes": tool_hashes,
            "license_path": license_path,
            "manifest_digest": hashlib.sha256(canonical(actual)).hexdigest(),
            "file_count": len(actual),
            "commands": _COMMANDS[command_start:],
            "execution_scope": "Tool compilation only; no game/core/model execution or training",
            "automated_tests_run": False,
        }
        manifest_bytes = canonical(actual)
        if len(manifest_bytes) > MAX_LOG:
            raise ValueError("SDK inventory exceeds receipt capacity")
        (sdk / ".skeleton-toolchain-manifest.json").write_bytes(manifest_bytes)
        (sdk / ".skeleton-toolchain.json").write_bytes(canonical(receipt))
        verify_install(stage, tool)
        if destination.exists():
            raise ValueError("SDK destination appeared during private staging")
        sdk.replace(destination)
    return verify_install(root, tool)


def main(argv=None):
    global _CACHE, _DOWNLOAD, _LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Private absolute installation directory")
    parser.add_argument(
        "--tool",
        action="append",
        choices=TOOLS,
        help="Install only this explicit tool; repeat for additional tools",
    )
    parser.add_argument("--cc65", action="store_true", help="Compatibility selection for --tool cc65")
    parser.add_argument("--rgbds", action="store_true", help="Compatibility selection for --tool rgbds")
    parser.add_argument(
        "--cache-root", help="Existing absolute offline archive/source cache; defaults to ROOT/cache"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Explicitly acquire missing pinned public archives/source commits",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Read-only verify selected existing SDK receipts; no build/download",
    )
    args = parser.parse_args(argv)
    selected = list(
        dict.fromkeys(
            [*(args.tool or []), *(["cc65"] if args.cc65 else []), *(["rgbds"] if args.rgbds else [])]
        )
    )
    if not selected:
        parser.error(
            "Select at least one explicit --tool (or --cc65/--rgbds); no unrequested tools are acquired"
        )
    if args.inspect and args.download:
        parser.error("--inspect cannot acquire source or archives")
    if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
        parser.error("Pinned tool provisioning currently supports Linux AMD64 only")
    os.umask(0o077)
    try:
        if args.inspect:
            root = Path(args.root)
            if not root.is_absolute() or root.resolve() != root or root.is_symlink() or not root.is_dir():
                raise ValueError("Inspect requires an existing canonical installation root")
            records = [verify_install(root, tool) for tool in selected]
        else:
            for binary in (
                ["/usr/bin/prlimit"]
                + (
                    ["/usr/bin/git", "/usr/bin/make"]
                    if any(tool in selected for tool in ("cc65", "rgbds"))
                    else []
                )
                + (["/usr/bin/dpkg-deb"] if any(tool in selected for tool in ("sdl2", "rgbds")) else [])
            ):
                if not Path(binary).is_file() or not os.access(binary, os.X_OK):
                    raise ValueError(
                        "Install the host build prerequisite before provisioning: " + Path(binary).name
                    )
            root = private_root(args.root)
            _CACHE = private_root(args.cache_root or str(root / "cache"))
            _DOWNLOAD = bool(args.download)
            _LOG = root / "installation.private.log"
            if _LOG.is_symlink():
                raise ValueError("Installation log cannot be a symlink")
            descriptor = os.open(
                root / ".installation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
            )
            with os.fdopen(descriptor, "a+b") as lock:
                details = os.fstat(lock.fileno())
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_uid != os.geteuid()
                    or details.st_mode & 0o077
                ):
                    raise ValueError("Installation lock must be a private operator regular file")
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise ValueError(
                                "Another operator installation still holds the bounded lock"
                            ) from None
                        time.sleep(0.05)
                records = [install_one(root, tool) for tool in selected]
                # A later explicit install must not omit an already sealed SDK
                # from the operator's suggested configuration.
                for tool in TOOLS:
                    if tool not in selected and (root / tool / ".skeleton-toolchain.json").is_file():
                        records.append(verify_install(root, tool))
        installed = [row["tool"] for row in records]
        roots = [str(root / tool) for tool in installed if tool in ("sdl2", "cc65", "rgbds")]
        configuration = {"SKL_GAME_CONSOLE_SDK_ROOTS": json.dumps(roots)}
        if "sdl2" in installed:
            configuration["SKL_GAME_SDL2_SDK_ROOT"] = str(root / "sdl2")
        if "go" in installed:
            configuration["SKL_GAME_GO_ROOT"] = str(root / "go")
        report = {
            "schema": "skeleton.game.operator_toolchains.v2",
            "tools": records,
            "configuration": configuration,
            "network_acquisition_authorized": bool(args.download),
            "current_operation_commands": list(_COMMANDS),
            "current_archive_acquisitions": list(_ACQUISITIONS),
            "read_only_inspection": bool(args.inspect),
            "tests_run": False,
            "limitations": [
                "Host SDKs do not establish container/server build readiness",
                "Original source compilation does not prove foreign OS/hardware gameplay",
                "No ROMs, firmware, games or privileged host packages acquired",
            ],
        }
        if not args.inspect:
            data = json.dumps(report, indent=2) + "\n"
            descriptor, filename = tempfile.mkstemp(prefix=".receipt-", dir=root)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            Path(filename).replace(root / "desktop-toolchain-receipt.json")
        print(json.dumps(report, indent=2))
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        RecursionError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        print(json.dumps({"status": "toolchain_provisioning_rejected", "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
