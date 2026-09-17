"""Late-wave CLI hook. wave16+ live in cli_waveN.run."""

from __future__ import annotations

from typing import List


def try_wave(cmd: str, rest: List[str]) -> int | None:
    if not cmd.startswith("wave"):
        return None
    tail = cmd[4:]
    if not tail.isdigit() or int(tail) < 16:
        return None
    try:
        mod = __import__("skeleton.game.cli_" + cmd, fromlist=["run"])
    except ImportError:
        return None
    return int(mod.run(rest))
