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
from pathlib import Path, PurePosixPath
import os
import shutil
import subprocess
from time import monotonic
from tempfile import TemporaryDirectory
from threading import Thread

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
    "commodore_64": (("cl65", "-t", "c64", "-O", "-o", "build/dragon.prg", "src/main.c"),),
    "nes":(
        ("ca65","-o","build/dragon.o","src/main.s"),
        ("ld65","-C","nes.cfg","-o","build/dragon.nes","build/dragon.o"),
    ),
}
OUTPUTS={"game_boy":"build/dragon.gb","game_boy_color":"build/dragon.gbc","nes":"build/dragon.nes", "commodore_64":"build/dragon.prg"}

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
        if blob[0x148] > 8 or len(blob) != 32768 << blob[0x148]:
            return False
        if blob[0x147] != 0 or blob[0x149] != 0:
            return False
        checksum=0
        for b in blob[0x134:0x14D]:
            checksum=(checksum-b-1)&0xff
        global_checksum = (sum(blob[:0x14E]) + sum(blob[0x150:])) & 0xFFFF
        return blob[0x14D] == checksum and int.from_bytes(blob[0x14E:0x150], "big") == global_checksum
    if target_id == "commodore_64":
        # cc65 BASIC-loadable PRG: $0801 load address, a SYS entry line,
        # end-of-program marker and a machine-code entry inside the payload.
        if not 32 <= len(blob) <= 0xD000 - 0x0801 + 2 or blob[:2] != b"\x01\x08":
            return False
        next_line = int.from_bytes(blob[2:4], "little") - 0x0801 + 2
        if not 8 <= next_line < min(len(blob) - 2, 64):
            return False
        if blob[next_line - 1:next_line + 2] != b"\0\0\0" or blob[6] != 0x9E:
            return False
        entry = blob[7:next_line - 1].strip(b" ")
        return entry.isdigit() and next_line + 2 <= int(entry) - 0x0801 + 2 < len(blob)
    if target_id=="nes":
        if len(blob)<16 or blob[:4]!=b"NES\x1a":
            return False
        prg=blob[4]*16384
        chr=blob[5]*8192
        return (prg==32768 and chr==8192 and len(blob)==16+prg+chr
                and blob[6:16] == bytes(10))
    return False

MAX_BUILD_LOG_BYTES = 64 * 1024
MAX_BINARY_BYTES = 2_000_000


def _safe_member(root: Path, name: str) -> Path:
    """Reject traversal and every linked component, including broken links."""
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or ".." in path.parts or path.as_posix() != name or name == "."):
        raise ValueError("unsafe native project path")
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("native paths must not contain symlinks")
    return current


def _run_bounded(argv, *, cwd, env, timeout):
    """Drain diagnostics without retaining unlimited compiler output in RAM."""
    with subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as process:
        captured = bytearray()
        overflow = []
        def drain():
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                remaining = MAX_BUILD_LOG_BYTES - len(captured)
                captured.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.append(True)
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    break
        reader = Thread(target=drain, daemon=True)
        reader.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        finally:
            reader.join(timeout=1)
        if overflow:
            return 1, "compiler diagnostic output exceeded budget"
        return process.returncode, captured.decode("utf-8", errors="replace")


def compile_local(project:NativeProject,root:Path,*,authorized:bool,
                  timeout_seconds:int=25)->NativeBuildResult:
    if authorized is not True:
        raise PermissionError("explicit native compilation permission required")
    if not isinstance(project, NativeProject) or project.status!="source_generated" or project.target_id not in COMMANDS:
        raise ValueError("native compiler adapter not implemented")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 5<=timeout_seconds<=120:
        raise ValueError("invalid compiler time budget")
    root = Path(root).expanduser()
    if root.is_symlink():
        raise ValueError("native project root must not be a symlink")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("native project root must be a directory")
    # Freeze mutable caller data before validating or invoking a tool.
    sources = dict(project.files)
    if not sources or len(sources) > 128:
        raise ValueError("native source file budget exceeded")
    for name, data in sources.items():
        path = _safe_member(root, name)
        if PurePosixPath(name).parts[0] == "build":
            raise ValueError("generated sources cannot supply build artifacts")
        if not isinstance(data, str) or len(data.encode("utf-8")) > 120_000:
            raise ValueError("native source byte budget exceeded")
        if not path.is_file() or path.stat().st_size > 120_000:
            raise ValueError("native source tree is incomplete or exceeds budget")
        if path.read_text(encoding="utf-8") != data:
            raise ValueError("source tree changed since template generation")
    from .dragon_native_projects import digest
    if digest(sources) != project.digest:
        raise ValueError("native project source digest changed")
    _safe_member(root, OUTPUTS[project.target_id])
    commands = []
    for argv in COMMANDS[project.target_id]:
        executable = shutil.which(argv[0])
        if executable is None:
            return NativeBuildResult(project.target_id,"toolchain_missing","",
                                     "",0,0,0.0,argv[0]+" is not installed")
        commands.append((str(Path(executable).resolve()), *argv[1:]))
    start = monotonic()
    def failed(state, steps, message):
        return NativeBuildResult(project.target_id, state, "", "", 0, steps,
                                 monotonic() - start, message)
    # Compile only the verified snapshot. Existing object files and ROMs are
    # neither inputs nor evidence, and partial builds never replace a good ROM.
    with TemporaryDirectory(prefix=".dragon-build-", dir=root) as temporary:
        stage = Path(temporary)
        for name, data in sources.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(data, encoding="utf-8")
        (stage / "build").mkdir(exist_ok=True)
        for index, argv in enumerate(commands):
            remaining = timeout_seconds - (monotonic() - start)
            if remaining <= 0:
                return failed("timed_out", index, "toolchain timeout")
            try:
                code, diagnostic = _run_bounded(argv, cwd=stage, env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", ""),
                    "LC_ALL": "C",
                    **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {}),
                }, timeout=remaining)
            except subprocess.TimeoutExpired:
                return failed("timed_out", index + 1, "toolchain timeout")
            except OSError:
                return failed("compile_failed", index + 1, "native toolchain could not start")
            if code:
                return failed("compile_failed", index + 1, (diagnostic or "compiler failed")[:1200])
        output = _safe_member(stage, OUTPUTS[project.target_id])
        if not output.is_file():
            return failed("missing_binary", len(commands), "compiler wrote no verified native binary")
        if output.stat().st_size > MAX_BINARY_BYTES:
            return failed("invalid_binary", len(commands), "native binary exceeds byte budget")
        binary = output.read_bytes()
        if not _verify(project.target_id, binary):
            return failed("invalid_binary", len(commands), "native binary header/size invalid")
        destination = _safe_member(root, OUTPUTS[project.target_id])
        destination.parent.mkdir(exist_ok=True)
        os.replace(output, destination)
    return NativeBuildResult(project.target_id,"compiled_native",str(destination),
                             sha256(binary).hexdigest(),len(binary),len(commands),
                             monotonic()-start,"Native binary compiled; emulator playtest still required")
