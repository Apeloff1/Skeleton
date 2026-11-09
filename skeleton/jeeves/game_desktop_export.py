"""Original game desktop packages through a pinned, isolated Go compiler.

The generated executable embeds exact game files and serves them only to its
local player's browser. This is a native launcher with a browser renderer, not
a claim that an SDL renderer or a foreign operating system was executed here.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .game_console_build import BuildArtifact, ConsoleBuildResult

SCHEMA = "skeleton.game.desktop_export.v1"
GO_ROOT_ENV = "SKL_GAME_GO_ROOT"
MAX_SOURCE = 8 * 1024**2
MAX_FILE = 4 * 1024**2
MAX_ARTIFACT = 64 * 1024**2
TARGETS = {
    "windows-amd64": ("windows", "amd64", "pe32_plus", "Windows PC"),
    "linux-amd64": ("linux", "amd64", "elf64", "Linux x86-64"),
    "linux-arm64": ("linux", "arm64", "elf64", "Linux ARM64"),
    "darwin-amd64": ("darwin", "amd64", "mach_o_64", "macOS Intel"),
    "darwin-arm64": ("darwin", "arm64", "mach_o_64", "macOS Apple silicon"),
}
_SLOTS = threading.BoundedSemaphore(2)


class DesktopExportError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or PurePosixPath(value).is_absolute()
        or str(PurePosixPath(value)) != value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(character in value for character in ("\\", ":", "\x00"))
        or any(ord(character) < 32 for character in value)
    ):
        raise DesktopExportError("Desktop source paths must be exact safe relative paths")
    return value


def _hash_file(path: Path, maximum=128 * 1024**2) -> str:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022 or before.st_size > maximum:
            raise DesktopExportError("Desktop tooling must be bounded, non-group-writable regular files")
        digest, size = hashlib.sha256(), 0
        while chunk := stream.read(256 * 1024):
            size += len(chunk)
            if size > maximum:
                raise DesktopExportError("Desktop tooling changed beyond its byte bound")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        final = path.stat(follow_symlinks=False)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(final):
            raise DesktopExportError("Desktop tooling changed while its identity was inspected")
        return digest.hexdigest()


def _toolchain() -> dict[str, Any]:
    raw = os.environ.get(GO_ROOT_ENV)
    if not raw:
        raise DesktopExportError("Install an approved Go toolchain and configure SKL_GAME_GO_ROOT")
    root = Path(raw)
    if not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root:
        raise DesktopExportError("Go operator root must be a canonical absolute directory")
    binary = root / "bin/go"
    if binary.is_symlink() or not os.access(binary, os.X_OK):
        raise DesktopExportError("Configured Go compiler is not an executable regular operator file")
    version = (root / "VERSION").read_text().splitlines()[0]
    if not re.fullmatch(r"go1\.\d{1,3}(?:\.\d{1,3})?", version):
        raise DesktopExportError("Configured Go SDK version is unsupported")
    tools = root / "pkg/tool/linux_amd64"
    if not tools.is_dir():
        raise DesktopExportError("Desktop compiler SDK does not provide the Linux AMD64 build tools")
    identities = {"bin/go": _hash_file(binary)}
    for name in ("compile", "link", "asm"):
        path = tools / name
        identities[path.relative_to(root).as_posix()] = _hash_file(path)
    sandbox = Path("/usr/bin/bwrap")
    if not sandbox.is_file():
        raise DesktopExportError("Desktop builds require the installed bubblewrap sandbox")
    limiter = Path("/usr/bin/prlimit")
    if not limiter.is_file():
        raise DesktopExportError("Desktop builds require the installed resource-limit launcher")
    return {
        "root": str(root),
        "compiler": str(binary),
        "version": version,
        "tool_hashes": identities,
        "identity_digest": _sha(_canonical(identities)),
        "sandbox": str(sandbox),
        "sandbox_sha256": _hash_file(sandbox),
        "limiter": str(limiter),
        "limiter_sha256": _hash_file(limiter),
    }


@dataclass(frozen=True, slots=True)
class DesktopExportRequest:
    files: Mapping[str, str]
    target_id: str
    title: str = "Riverlight"
    entrypoint: str | None = None
    expected_source_digest: str | None = None
    timeout_seconds: int = 300

    def __post_init__(self):
        if self.target_id not in TARGETS:
            raise DesktopExportError("Select an exact registered desktop OS and architecture")
        if (
            not isinstance(self.title, str)
            or not 1 <= len(self.title) <= 120
            or any(ord(c) < 32 for c in self.title)
        ):
            raise DesktopExportError("Desktop game title must be bounded printable text")
        if type(self.timeout_seconds) is not int or not 10 <= self.timeout_seconds <= 300:
            raise DesktopExportError("Desktop build timeout must be within 10–300 seconds")
        if not isinstance(self.files, Mapping) or not 1 <= len(self.files) <= 128:
            raise DesktopExportError("Desktop exports support at most 128 original text assets")
        clean, total = {}, 0
        for name, content in self.files.items():
            name = _path(name)
            if not isinstance(content, str):
                raise DesktopExportError(
                    "Desktop source assets must be exact text; encode binary assets explicitly"
                )
            size = len(content.encode())
            total += size
            if size > MAX_FILE or total > MAX_SOURCE:
                raise DesktopExportError("Original desktop game source exceeds its bounded byte budget")
            clean[name] = content
        entry = self.entrypoint
        if entry is None:
            candidates = [name for name in clean if name.endswith("index.html")]
            entry = next(
                (name for name in candidates if "successor" in name),
                candidates[0] if len(candidates) == 1 else None,
            )
        if entry is None or _path(entry) not in clean:
            raise DesktopExportError("Desktop export requires an exact playable HTML entrypoint")
        from types import MappingProxyType

        object.__setattr__(self, "files", MappingProxyType(dict(sorted(clean.items()))))
        object.__setattr__(self, "entrypoint", entry)
        if self.expected_source_digest is not None and self.expected_source_digest != self.source_digest:
            raise DesktopExportError("Desktop source compare-and-swap digest differs")

    @property
    def source_digest(self) -> str:
        return _sha(_canonical({name: _sha(content.encode()) for name, content in self.files.items()}))

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:48] or "riverlight"


def desktop_export_catalog() -> list[dict[str, Any]]:
    try:
        tools = _toolchain()
        ready, reason = True, "Approved Go compiler and mandatory sandbox are installed"
    except (DesktopExportError, OSError) as exc:
        tools, ready, reason = None, False, str(exc)
    return [
        {
            "target_id": target,
            "label": row[3],
            "os": row[0],
            "architecture": row[1],
            "binary_format": row[2],
            "renderer": "browser",
            "portable_source_export": True,
            "binary_build_available": ready,
            "readiness": {"code": "toolchain_present" if ready else "toolchain_required", "message": reason},
            "toolchain": (
                None
                if tools is None
                else {"version": tools["version"], "identity_digest": tools["identity_digest"]}
            ),
            "requires_browser": True,
            "target_execution_verified": False,
        }
        for target, row in TARGETS.items()
    ]


def _source_zip(request: DesktopExportRequest) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in request.files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, content.encode())
    return output.getvalue()


def _go_source(request: DesktopExportRequest) -> str:
    metadata = {
        "title": request.title,
        "entrypoint": request.entrypoint,
        "source_digest": request.source_digest,
        "files": {
            name: {"bytes": len(content.encode()), "sha256": _sha(content.encode())}
            for name, content in request.files.items()
        },
    }
    return _GO_LAUNCHER.replace("__GAME_PAYLOAD__", base64.b64encode(_source_zip(request)).decode()).replace(
        "__GAME_METADATA__", base64.b64encode(_canonical(metadata)).decode()
    )


def _format(data: bytes, target: str) -> str:
    system, arch, expected, _ = TARGETS[target]
    if system == "linux":
        if (
            len(data) < 64
            or data[:6] != b"\x7fELF\x02\x01"
            or struct.unpack_from("<H", data, 18)[0] != (62 if arch == "amd64" else 183)
        ):
            raise DesktopExportError("Compiler output is not the requested ELF64 architecture")
    elif system == "windows":
        if len(data) < 256 or data[:2] != b"MZ":
            raise DesktopExportError("Compiler output is not a Windows PE executable")
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        if (
            offset > len(data) - 32
            or data[offset : offset + 4] != b"PE\0\0"
            or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664
            or struct.unpack_from("<H", data, offset + 24)[0] != 0x20B
        ):
            raise DesktopExportError("Compiler output is not Windows x86-64 PE32+")
    elif (
        len(data) < 32
        or data[:4] != b"\xcf\xfa\xed\xfe"
        or struct.unpack_from("<I", data, 4)[0] != (0x01000007 if arch == "amd64" else 0x0100000C)
    ):
        raise DesktopExportError("Compiler output is not the requested Mach-O64 architecture")
    return expected


def _manifest(request, tools, digest, length):
    return {
        "schema_version": SCHEMA,
        "target_id": request.target_id,
        "title": request.title,
        "source_digest": request.source_digest,
        "entrypoint": request.entrypoint,
        "renderer": "browser",
        "launcher_kind": "compiled_native_loopback_server",
        "compiler_version": tools["version"],
        "compiler_identity": tools["identity_digest"],
        "executable_sha256": digest,
        "executable_bytes": length,
        "target_execution_verified": False,
        "source_game_assets_copied": False,
        "local_save": "Private atomic player save under OS configuration directory, keyed by exact source identity",
        "network": "IPv4 loopback only; unpredictable per-process token path; no external service required",
    }


def _package(request: DesktopExportRequest, executable: bytes, tools: dict) -> BuildArtifact:
    system = TARGETS[request.target_id][0]
    executable_name = request.slug + (".exe" if system == "windows" else "")
    manifest = _manifest(request, tools, _sha(executable), len(executable))
    readme = (
        f"{request.title}\n\nBuilt for {TARGETS[request.target_id][3]}. Extract this archive before launching.\n"
        "The native launcher opens the original game in your installed browser. Gameplay assets are embedded; no hosted service is required.\n"
        "Use --no-open to print the private local URL without opening a browser, or --inspect for exact build identity.\n"
        "Native OS format was verified at build time. Foreign OS execution and platform signing/notarization were not performed.\n"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        files: dict[str, tuple[bytes, int]] = {
            "README.txt": (readme.encode(), 0o100644),
            "BUILD_IDENTITY.json": (_canonical(manifest), 0o100644),
        }
        if system == "darwin":
            bundle = request.slug + ".app/Contents/"
            files[bundle + "MacOS/" + request.slug] = (executable, 0o100755)
            import html

            plist = (
                f'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>'
                f"<key>CFBundleExecutable</key><string>{request.slug}</string><key>CFBundleIdentifier</key><string>games.skeleton.{request.slug}</string>"
                f"<key>CFBundleName</key><string>{html.escape(request.title)}</string><key>CFBundlePackageType</key><string>APPL</string>"
                "<key>CFBundleVersion</key><string>1</string><key>NSHighResolutionCapable</key><true/></dict></plist>"
            )
            files[bundle + "Info.plist"] = (plist.encode(), 0o100644)
        else:
            files[executable_name] = (executable, 0o100755)
            if system == "linux":
                desktop = f"[Desktop Entry]\nType=Application\nName={request.title}\nExec=./{request.slug}\nTerminal=false\nCategories=Game;\n"
                files[request.slug + ".desktop"] = (desktop.encode(), 0o100644)
        for name, (data, mode) in files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    data = output.getvalue()
    if len(data) > MAX_ARTIFACT:
        raise DesktopExportError("Packaged native game exceeds its artifact byte budget")
    return BuildArtifact(
        request.slug + "-" + request.target_id + ".zip",
        data,
        "zip",
        "compiled_os_architecture_and_exact_embedded_source",
    )


def _sandbox(tools, work: Path, target: str) -> list[str]:
    system, arch, _, _ = TARGETS[target]
    root = tools["root"]
    argv = [
        tools["sandbox"],
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for path in ("/lib", "/lib64", "/bin"):
        if Path(path).exists():
            argv.extend(("--ro-bind", path, path))
    argv.extend(("--dir", "/etc"))
    if Path("/etc/ld.so.cache").is_file():
        argv.extend(("--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"))
    argv.extend(
        (
            "--ro-bind",
            root,
            root,
            "--bind",
            str(work),
            "/work",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "67108864",
            "--tmpfs",
            "/tmp",
            "--chdir",
            "/work",
        )
    )
    values = {
        "GOROOT": root,
        "GOTOOLCHAIN": "local",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "GOENV": "off",
        "GOOS": system,
        "GOARCH": arch,
        "CGO_ENABLED": "0",
        "GOMAXPROCS": "2",
        "HOME": "/tmp",
        "GOCACHE": "/work/cache",
        "GOTMPDIR": "/work/tmp",
        "TMPDIR": "/work/tmp",
        "PATH": root + "/bin:/usr/bin:/bin",
        "LC_ALL": "C",
    }
    for name, value in values.items():
        argv.extend(("--setenv", name, value))
    return [
        *argv,
        "--",
        tools["compiler"],
        "build",
        "-p",
        "2",
        "-trimpath",
        "-buildvcs=false",
        "-ldflags=-s -w",
        "-o",
        "/work/game",
        "/work/main.go",
    ]


class DesktopExportRunner:
    @staticmethod
    def plan(request: DesktopExportRequest) -> dict[str, Any]:
        if not isinstance(request, DesktopExportRequest):
            raise DesktopExportError("Typed desktop request is required")
        tools = _toolchain()
        return {
            "schema_version": SCHEMA,
            "target_id": request.target_id,
            "source_digest": request.source_digest,
            "entrypoint": request.entrypoint,
            "renderer": "browser",
            "compiler_version": tools["version"],
            "toolchain_digest": tools["identity_digest"],
            "sandbox_required": True,
            "maximum_seconds": request.timeout_seconds,
            "target_execution_verified": False,
            "fixed_command": ["go", "build", "-p", "2", "-trimpath", "-buildvcs=false", "-ldflags=-s -w"],
        }

    def build(
        self,
        request: DesktopExportRequest,
        *,
        cancel: Callable[[], bool] | None = None,
        event: Callable[[dict[str, Any]], None] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> ConsoleBuildResult:
        if not isinstance(request, DesktopExportRequest):
            raise DesktopExportError("Typed desktop request is required")
        if not _SLOTS.acquire(blocking=False):
            raise DesktopExportError("Desktop compiler capacity is occupied")
        process = None
        try:
            work = Path(tempfile.mkdtemp(prefix="skeleton-desktop-build-"))
            os.chmod(work, 0o700)
        except BaseException:
            _SLOTS.release()
            raise
        started = time.monotonic()
        cleaned = True
        try:
            if cancel and cancel():
                raise DesktopExportError("Desktop build cancelled before compiler activation")
            if authorize:
                authorize()
            tools = _toolchain()
            source = _go_source(request)
            (work / "main.go").write_text(source)
            (work / "cache").mkdir()
            (work / "tmp").mkdir()
            log = work / "compiler.log"
            if event:
                event(
                    {
                        "type": "build_started",
                        "target_id": request.target_id,
                        "source_digest": request.source_digest,
                    }
                )

            with log.open("wb") as output:
                process = subprocess.Popen(
                    [
                        tools["limiter"],
                        "--core=0",
                        "--nofile=256",
                        "--fsize=268435456",
                        "--cpu=" + str(request.timeout_seconds + 10),
                        "--as=4294967296",
                        "--",
                        *_sandbox(tools, work, request.target_id),
                    ],
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                    close_fds=True,
                    start_new_session=True,
                )
                last_event = 0.0
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    if cancel and cancel():
                        raise DesktopExportError("Desktop build cancellation requested")
                    if elapsed > request.timeout_seconds:
                        raise DesktopExportError("Desktop compiler deadline exceeded")
                    if log.stat().st_size > 2 * 1024**2:
                        raise DesktopExportError("Compiler log exceeded its byte budget")
                    if elapsed - last_event > 1:
                        if authorize:
                            authorize()
                        sizes = sum(path.stat().st_size for path in work.rglob("*") if path.is_file())
                        if sizes > 1024**3:
                            raise DesktopExportError("Desktop compiler scratch exceeded 1 GiB")
                        if event:
                            event(
                                {
                                    "type": "build_running",
                                    "target_id": request.target_id,
                                    "elapsed_seconds": round(elapsed, 3),
                                    "scratch_bytes": sizes,
                                }
                            )
                        last_event = elapsed
                    time.sleep(0.05)
            text = log.read_bytes()[: 2 * 1024**2].decode(errors="replace")
            if process.returncode != 0:
                raise DesktopExportError("Isolated desktop compiler failed: " + text[-3000:])
            if authorize:
                authorize()
            if cancel and cancel():
                raise DesktopExportError("Desktop build cancelled before artifact publication")
            if _toolchain() != tools:
                raise DesktopExportError("Approved desktop toolchain changed during compilation")
            binary = work / "game"
            if binary.is_symlink() or not binary.is_file() or not 1 <= binary.stat().st_size <= MAX_ARTIFACT:
                raise DesktopExportError("Compiler produced no bounded regular game executable")
            executable = binary.read_bytes()
            kind = _format(executable, request.target_id)
            extension = ".exe" if TARGETS[request.target_id][0] == "windows" else ""
            artifacts = (
                BuildArtifact(
                    request.slug + "-" + request.target_id + extension,
                    executable,
                    kind,
                    "actual_compiler_exit_and_os_architecture",
                ),
                _package(request, executable, tools),
            )
            if authorize:
                authorize()
            if cancel and cancel():
                raise DesktopExportError("Desktop build cancelled before final artifact receipt")
            receipt = {
                "schema_version": SCHEMA,
                "target_id": request.target_id,
                "source_digest": request.source_digest,
                "compiler_identity": tools["identity_digest"],
                "compiler_version": tools["version"],
                "sandbox_sha256": tools["sandbox_sha256"],
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "compiler_exit_code": process.returncode,
                "renderer": "browser",
                "executable_sha256": _sha(executable),
                "target_execution_verified": False,
                "files": [a.as_dict() for a in artifacts],
            }
            if event:
                event({"type": "build_completed", **receipt})
            return ConsoleBuildResult("binary_ready", _canonical(receipt).decode(), artifacts)
        finally:
            if process is not None and process.poll() is None:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        continue
                    break
                cleaned = process.poll() is not None
            if cleaned:
                shutil.rmtree(work, ignore_errors=True)
                _SLOTS.release()
            # Unknown quiescence retains both capacity and its private tempdir.


_GO_LAUNCHER = r"""package main
import("archive/zip";"bytes";"context";"crypto/rand";"crypto/sha256";"encoding/base64";"encoding/hex";"encoding/json";"errors";"flag";"fmt";"io";"mime";"net";"net/http";"os";"os/exec";"os/signal";"path";"path/filepath";"runtime";"strings";"sync";"time")
const payload="__GAME_PAYLOAD__"
const metadata="__GAME_METADATA__"
type FileIdentity struct{Bytes int `json:"bytes"`; SHA string `json:"sha256"`}
type Manifest struct{Title string `json:"title"`; Entry string `json:"entrypoint"`; Digest string `json:"source_digest"`; Files map[string]FileIdentity `json:"files"`}
var saveMu sync.Mutex
func main(){if err:=run();err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}}
func run()error{
 noOpen:=flag.Bool("no-open",false,"Serve the exact game without opening a browser");inspect:=flag.Bool("inspect",false,"Print embedded build identity");flag.Parse()
 raw,e:=base64.StdEncoding.DecodeString(metadata);if e!=nil{return e};var m Manifest;if e=json.Unmarshal(raw,&m);e!=nil{return e}
 if *inspect{fmt.Println(string(raw));return nil}
 packed,e:=base64.StdEncoding.DecodeString(payload);if e!=nil{return e};zr,e:=zip.NewReader(bytes.NewReader(packed),int64(len(packed)));if e!=nil{return e}
 files:=map[string][]byte{};total:=0
 for _,f:=range zr.File{if f.FileInfo().IsDir(){return errors.New("unexpected embedded directory")};id,ok:=m.Files[f.Name];if !ok||f.Name!=path.Clean(f.Name)||strings.HasPrefix(f.Name,"/")||strings.Contains(f.Name,"\\")||strings.Contains(f.Name,":")||f.UncompressedSize64>4194304{return errors.New("invalid embedded source path or size")};if _,ok=files[f.Name];ok{return errors.New("duplicate embedded source")};r,e:=f.Open();if e!=nil{return e};data,e:=io.ReadAll(io.LimitReader(r,4194305));r.Close();if e!=nil{return e};h:=sha256.Sum256(data);if len(data)!=id.Bytes||hex.EncodeToString(h[:])!=id.SHA{return errors.New("embedded source identity differs")};total+=len(data);if total>8388608{return errors.New("game source exceeds its byte bound")};files[f.Name]=data}
 if len(files)!=len(m.Files)||files[m.Entry]==nil{return errors.New("incomplete embedded game")}
 tokenBytes:=make([]byte,32);if _,e=rand.Read(tokenBytes);e!=nil{return e};token:=hex.EncodeToString(tokenBytes);prefix:="/"+token+"/"
 listener,e:=net.Listen("tcp4","127.0.0.1:0");if e!=nil{return e};defer listener.Close();host:=listener.Addr().String();origin:="http://"+host
 config,e:=os.UserConfigDir();if e!=nil{return e};saveRoot:=filepath.Join(config,"SkeletonGames",m.Digest);if e=os.MkdirAll(saveRoot,0700);e!=nil{return e};saveFile:=filepath.Join(saveRoot,"save.json")
 server:=&http.Server{ReadHeaderTimeout:3*time.Second,ReadTimeout:10*time.Second,WriteTimeout:10*time.Second,IdleTimeout:30*time.Second,MaxHeaderBytes:16384}
 quit:=make(chan struct{},1);mux:=http.NewServeMux();server.Handler=mux
 mux.HandleFunc("/",func(w http.ResponseWriter,r *http.Request){
  w.Header().Set("X-Content-Type-Options","nosniff");w.Header().Set("Referrer-Policy","no-referrer");w.Header().Set("Cache-Control","no-store");w.Header().Set("Cross-Origin-Opener-Policy","same-origin");w.Header().Set("Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
  if r.Host!=host||!strings.HasPrefix(r.URL.Path,prefix){http.NotFound(w,r);return};if source:=r.Header.Get("Origin");source!=""&&source!=origin{http.Error(w,"foreign origin",403);return}
  name:=strings.TrimPrefix(r.URL.Path,prefix)
  if name=="api/save"{
   saveMu.Lock();defer saveMu.Unlock()
   if r.Method=="GET"{file,err:=os.Open(saveFile);if os.IsNotExist(err){w.Header().Set("Content-Type","application/json");w.Write([]byte("null"));return};if err!=nil{http.Error(w,"save unavailable",503);return};data,err:=io.ReadAll(io.LimitReader(file,1048577));file.Close();if err!=nil||len(data)>1048576||!json.Valid(data){http.Error(w,"save unavailable",503);return};w.Header().Set("Content-Type","application/json");w.Write(data);return}
   if r.Method!="PUT"{http.Error(w,"method not allowed",405);return};if r.Header.Get("Origin")!=origin{http.Error(w,"save requires the local game origin",403);return};data,err:=io.ReadAll(io.LimitReader(r.Body,1048577));if err!=nil||len(data)>1048576||!json.Valid(data){http.Error(w,"invalid bounded save",422);return}
   temporary,err:=os.CreateTemp(saveRoot,".save-");if err!=nil{http.Error(w,"save unavailable",503);return};tmp:=temporary.Name();defer os.Remove(tmp);err=temporary.Chmod(0600);if err==nil{_,err=temporary.Write(data)};if err==nil{err=temporary.Sync()};closeErr:=temporary.Close();if err==nil{err=closeErr};if err==nil{err=os.Rename(tmp,saveFile)};if err!=nil{http.Error(w,"save unavailable",503);return};w.Header().Set("Content-Type","application/json");w.Write([]byte("{\"saved\":true}"));return
  }
  if name=="api/quit"{if r.Method!="POST"||r.Header.Get("Origin")!=origin{http.Error(w,"quit requires the local game origin",403);return};select{case quit<-struct{}{}:default:};w.Write([]byte("{\"quitting\":true}"));return};if name=="api/identity"{if r.Method!="GET"{http.Error(w,"method not allowed",405);return};w.Header().Set("Content-Type","application/json");w.Write(raw);return}
  if r.Method!="GET"&&r.Method!="HEAD"{http.Error(w,"method not allowed",405);return};if name==""{name=m.Entry};if name!=path.Clean(name)||strings.Contains(name,"\\")||strings.HasPrefix(name,"/"){http.NotFound(w,r);return};data,ok:=files[name];if !ok{http.NotFound(w,r);return};kind:=mime.TypeByExtension(path.Ext(name));if kind==""{kind="application/octet-stream"};w.Header().Set("Content-Type",kind);if r.Method!="HEAD"{if strings.HasSuffix(name,".html"){bridge:=`<script>window.SkeletonDesktop={apiBase:`+fmt.Sprintf("%q",prefix+"api/")+`,readSave:async()=>{const r=await fetch(window.SkeletonDesktop.apiBase+"save");if(!r.ok)throw Error("Local save unavailable");return r.json()},writeSave:async state=>{const r=await fetch(window.SkeletonDesktop.apiBase+"save",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(state)});if(!r.ok)throw Error("Local save failed");return r.json()},quit:()=>fetch(window.SkeletonDesktop.apiBase+"quit",{method:"POST"})};</script>`;data=bytes.Replace(data,[]byte("</head>"),[]byte(bridge+"</head>"),1)};w.Write(data)}
 })
 url:=origin+prefix+m.Entry;fmt.Printf("%s\n%s\n",m.Title,url)
 if !*noOpen{var command *exec.Cmd;switch runtime.GOOS{case "darwin":command=exec.Command("/usr/bin/open",url);case "windows":command=exec.Command("rundll32.exe","url.dll,FileProtocolHandler",url);default:command=exec.Command("/usr/bin/xdg-open",url)};if err:=command.Start();err!=nil{fmt.Fprintln(os.Stderr,"Open the printed private URL in your browser:",err)}else{go command.Wait()}}
 stopped:=make(chan os.Signal,1);signal.Notify(stopped,os.Interrupt);defer signal.Stop(stopped)
 failures:=make(chan error,1);go func(){failures<-server.Serve(listener)}()
 select{case <-quit:ctx,cancel:=context.WithTimeout(context.Background(),3*time.Second);defer cancel();return server.Shutdown(ctx);case <-stopped:ctx,cancel:=context.WithTimeout(context.Background(),3*time.Second);defer cancel();return server.Shutdown(ctx);case err:=<-failures:if errors.Is(err,http.ErrServerClosed){return nil};return err}
}
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--target", choices=tuple(TARGETS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--title", default="Riverlight")
    args = parser.parse_args(argv)
    if args.catalog:
        print(json.dumps(desktop_export_catalog(), indent=2))
        return 0
    if args.project is None or args.target is None or args.output is None:
        parser.error("Provide --project --target --output")
    if args.project.is_symlink() or not 1 <= args.project.stat().st_size <= MAX_SOURCE:
        raise DesktopExportError("Input project must be a bounded regular JSON file")
    value = json.loads(args.project.read_text())
    files = value.get("files", value)
    if isinstance(files, list):
        files = {row["path"]: row["content"] for row in files}
    request = DesktopExportRequest(files, args.target, args.title)
    result = DesktopExportRunner().build(request)
    args.output.mkdir(parents=True, exist_ok=True)
    for artifact in result.artifacts:
        destination = args.output / artifact.name
        with destination.open("xb") as stream:
            stream.write(artifact.data)
        if artifact.format in {"elf64", "mach_o_64", "pe32_plus"}:
            os.chmod(destination, 0o700)
    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
