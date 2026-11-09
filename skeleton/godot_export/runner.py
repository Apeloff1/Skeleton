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
