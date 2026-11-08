"""Injectable wrapper around the Godot binary.

Ported from ``scripts/certify_game_frontier_godot_import.py`` (GF-D): timeouts
and launch failures become machine-readable results instead of tracebacks.
"""
from __future__ import annotations

import subprocess
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
    return RunResult(r.returncode, r.stdout + "\n" + r.stderr, tuple(argv))


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
        """Export and require a newly created, nonempty regular artifact.

        This is source-level output custody, not evidence that the binary boots.
        Existing destinations are rejected rather than silently overwritten.
        The caller must keep the destination directory private to avoid races
        with another local process or untrusted filesystem actor.
        """
        import stat

        destination = Path(out)
        if not destination.is_absolute():
            destination = project / destination
        if not preset or not preset.strip() or "\\x00" in preset:
            raise ValueError("export preset must be nonempty")
        if not out or "\\x00" in out:
            raise ValueError("export output must be nonempty")
        try:
            destination.lstat()
        except FileNotFoundError:
            pass
        else:
            return RunResult(73, "Export destination already exists", ())
        result = self.export(project, preset, out, mode=mode, timeout=timeout)
        if not result.ok:
            return result
        try:
            info = destination.lstat()
        except OSError:
            return RunResult(74, "Godot reported success but export artifact is missing", result.argv)
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            return RunResult(74, "Godot export artifact is not a nonempty regular file", result.argv)
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
