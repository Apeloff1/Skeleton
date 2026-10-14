"""House seal. Merkle over sampled roots. No coin."""

from __future__ import annotations

import hashlib
from typing import Sequence

from volume_forge.kernel import merkle_root

def root_of(rows: Sequence[dict[str, object]]) -> str:
    if not rows:
        raise ValueError("empty seal")
    leaves = [hashlib.sha256(f"{row['house']}/{row['organ']}|{row['root']}|{row['mass']}".encode()).digest() for row in rows]
    return merkle_root(leaves)
