"""Named attestations."""

from __future__ import annotations

from typing import Any


class AttestationPackError(ValueError):
    pass


ATT = tuple(f"at_{i:02d}" for i in range(8))


def seal(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ATT:
        raise AttestationPackError(name)
    nxt = dict(state)
    nxt["attestation"] = name
    nxt["sealed"] = 1
    nxt["stored_prose"] = 0
    return nxt
