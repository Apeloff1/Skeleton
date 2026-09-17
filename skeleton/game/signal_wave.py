"""Wave-4 mesh signals. Pointer only."""

from __future__ import annotations

from typing import Any


class SignalWaveError(ValueError):
    pass


SIG = tuple(f"sig_{i:02d}" for i in range(24))


def send(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SIG:
        raise SignalWaveError(name)
    nxt = dict(state)
    nxt["signal"] = name
    nxt["tokens"] = max(0, int(nxt.get("tokens", 8)) - (1 if SIG.index(name) % 2 else 0))
    nxt["stored_prose"] = 0
    return nxt


def recv(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SIG:
        raise SignalWaveError(name)
    nxt = dict(state)
    nxt["heard"] = name
    nxt["alert"] = int(nxt.get("alert", 0)) + (SIG.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
