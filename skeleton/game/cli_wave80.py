"""Wave-80 CLI hook."""

from __future__ import annotations

import json
from typing import List


def run(rest: List[str]) -> int:
    seed = 8847291
    i = 0
    while i < len(rest):
        if rest[i] == "--seed" and i + 1 < len(rest) and str(rest[i + 1]).isdigit():
            seed = int(rest[i + 1])
            i += 2
        else:
            i += 1
    try:
        from skeleton.game.wave80_more import play as more
        from skeleton.game.wave80_play import play
        first = play(seed=seed)
        second = more(seed=seed)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, "digest": first["digest"], "more": second["digest"], "packs": first["packs"], "sota_ready": False, "stored_prose": 0}, indent=2))
    return 0
