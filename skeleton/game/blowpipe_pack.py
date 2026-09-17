"""Named blowpipes."""

from __future__ import annotations

from typing import Any


class BlowpipePackError(ValueError):
    pass


PIPE = tuple(f"bp_{i:02d}" for i in range(12))


def blow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PIPE:
        raise BlowpipePackError(name)
    nxt = dict(state)
    nxt["blowpipe"] = name
    nxt["puff"] = int(nxt.get("puff", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
