"""Injectable wrapper around the Godot binary.

Ported from ``scripts/certify_game_frontier_godot_import.py`` (GF-D): timeouts
and launch failures become machine-readable results instead of tracebacks.
"""
from __future__ import annotations

import subprocess
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

TAIL = 1500


@dataclass(frozen=True)
class RunResult:
    code: int
    output: str
    argv: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def timed_out(self) -> bool:
        return self.code == 124

    @property
    def launch_failed(self) -> bool:
        return self.code == 127


Exec = Callable[[Sequence[str], Path, int], RunResult]


def _decode(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


def subprocess_exec(argv: Sequence[str], cwd: Path, timeout: int) -> RunResult:
    try:
        r = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        out = _decode(exc.stdout)[-TAIL:] + "\n" + _decode(exc.stderr)[-TAIL:] + "\nGodot timed out"
        return RunResult(124, out, tuple(argv))
    except OSError as exc:
        return RunResult(127, "Godot launch failed: " + type(exc).__name__, tuple(argv))
    output = (r.stdout or "") + "\n" + (r.stderr or "")
    return RunResult(r.returncode, output[-TAIL:], tuple(argv))


class GodotRunner:
    def __init__(self, godot: str, exec_fn: Exec = subprocess_exec, headless: bool = True) -> None:
        self.godot = godot
        self.exec_fn = exec_fn
        self.headless = headless

    def argv(self, args: Sequence[str]) -> list[str]:
        base = [self.godot]
        if self.headless:
            base.append("--headless")
        return base + list(args)

    def run(self, args: Sequence[str], cwd: Path, timeout: int = 180) -> RunResult:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
            raise ValueError("Godot timeout must be finite and within (0, 3600]")
        if not isinstance(cwd, Path):
            raise TypeError("Godot working directory must be a Path")
        return self.exec_fn(self.argv(args), cwd, timeout)

    def version(self, cwd: Path) -> RunResult:
        return self.exec_fn([self.godot, "--version"], cwd, 30)

    def import_project(self, project: Path, timeout: int = 180) -> RunResult:
        return self.run(["--path", str(project), "--import"], project, timeout)

    def check_script(self, project: Path, res: str, timeout: int = 60) -> RunResult:
        return self.run(["--path", str(project), "--check-only", "--script", res], project, timeout)

    def export(self, project: Path, preset: str, out: str, mode: str = "release", timeout: int = 600) -> RunResult:
        if mode not in ("release", "debug", "pack"):
            raise ValueError(f"bad export mode {mode}")
        return self.run(["--path", str(project), f"--export-{mode}", preset, out], project, timeout)

    def export_verified(
        self,
        project: Path,
        preset: str,
        out: str,
        mode: str = "release",
        timeout: int = 600,
    ) -> RunResult:
        """Fail closed if the engine does not publish one stable new artifact.

        Only a trusted private POSIX workspace is supported here. This does
        not sign the executable, attest its runtime or certify a release.
        """
        import os
        import stat

        if (type(preset) is not str or not preset.strip()
                or "\x00" in preset or "\n" in preset or "\r" in preset
                or len(preset) > 256):
            raise ValueError("invalid bounded Godot export preset")
        if (type(out) is not str or not out or "\x00" in out
                or "\n" in out or "\r" in out or len(out) > 2048):
            raise ValueError("invalid bounded Godot export destination")
        if type(timeout) is not int or not 1 <= timeout <= 1800:
            raise ValueError("invalid finite Godot export timeout")
        if mode not in ("release", "debug", "pack"):
            raise ValueError("invalid Godot export mode")
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or not hasattr(os, "O_DIRECTORY")
                or os.open not in os.supports_dir_fd):
            raise ValueError("descriptor-backed Godot export unavailable")

        path = Path(out)
        if any(part in (".", "..") for part in out.replace("\\", "/").split("/")):
            raise ValueError("export destination contains traversal")
        destination = path if path.is_absolute() else Path(project) / path
        destination = Path(os.path.abspath(destination))
        # Open parent directory one component at a time. Never follow an
        # existing symlink or create a directory as part of verification.
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        fd = os.open("/", flags)
        try:
            for part in destination.parts[1:-1]:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            try:
                os.stat(destination.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                return RunResult(73, "Export destination already exists", ())
        finally:
            os.close(fd)

        result = self.export(project, preset, out, mode=mode, timeout=timeout)
        if not result.ok:
            return result

        fd = os.open("/", flags)
        try:
            for part in destination.parts[1:-1]:
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            try:
                handle = os.open(destination.name, os.O_RDONLY | os.O_NOFOLLOW |
                                 getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
            except OSError:
                return RunResult(74, "Godot export artifact is missing or unsafe", result.argv)
            try:
                before = os.fstat(handle)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or not 0 < before.st_size <= 100 * 1024 * 1024):
                    return RunResult(74, "Godot export artifact is not a bounded unique regular file", result.argv)
                from hashlib import sha256
                h = sha256()
                size = 0
                while size <= 100 * 1024 * 1024:
                    chunk = os.read(handle, min(1024 * 1024, 100 * 1024 * 1024 - size + 1))
                    if not chunk:
                        break
                    size += len(chunk)
                    h.update(chunk)
                after = os.fstat(handle)
                try:
                    current = os.stat(destination.name, dir_fd=fd, follow_symlinks=False)
                except OSError:
                    return RunResult(74, "Godot export artifact disappeared during verification", result.argv)
                fields = ("st_dev", "st_ino", "st_mode", "st_nlink",
                          "st_size", "st_mtime_ns", "st_ctime_ns")
                identity = lambda info: tuple(getattr(info, field) for field in fields)
                if (size != before.st_size or identity(before) != identity(after)
                        or identity(after) != identity(current)
                        or not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
                    return RunResult(74, "Godot export artifact changed during verification", result.argv)
                # The digest is computed for custody validation, not elevated to
                # a release proof without a separately reviewed manifest.
                _ = h.hexdigest()
            finally:
                os.close(handle)
        except OSError:
            return RunResult(74, "Godot export artifact directory became unsafe", result.argv)
        finally:
            os.close(fd)
        return result

    def play_scene(
        self,
        project: Path,
        scene: str,
        *,
        frames: int = 120,
        timeout: int = 90,
    ) -> RunResult:
        """Execute a real Godot scene for a bounded number of engine frames.

        This is a native smoke boundary, not evidence of human input, gameplay
        completion, saved state, or a standalone exported executable.
        The caller must inspect the returned process result and engine output.
        """
        if not isinstance(scene, str) or not scene.startswith("res://"):
            raise ValueError("scene must be a res:// resource path")
        resource = scene[6:]
        parts = resource.split("/")
        if (
            not resource
            or len(resource) > 512
            or any(part in ("", ".", "..") for part in parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in resource)
            or "\\" in resource
            or not resource.endswith(".tscn")
        ):
            raise ValueError("scene must be a canonical .tscn resource path")
        if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= 36000:
            raise ValueError("frames must be an integer in [1, 36000]")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
            raise ValueError("timeout must be an integer in [1, 3600]")
        return self.run(
            ["--path", str(project), "--quit-after", str(frames), scene],
            project,
            timeout,
        )
