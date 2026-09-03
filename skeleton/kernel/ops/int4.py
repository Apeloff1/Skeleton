"""INT4 pack / unpack. Two nibbles per byte. FireQ handle."""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump


def pack(xs: List[float], *, scale: float = 0.1) -> Tuple[List[int], float]:
    s = float(scale) or 0.1
    q = [max(-8, min(7, int(round(v / s)))) for v in xs]
    packed: List[int] = []
    for i in range(0, len(q), 2):
        a = q[i] & 0xF
        b = (q[i + 1] & 0xF) if i + 1 < len(q) else 0
        packed.append((b << 4) | a)
    bump(len(packed))
    return packed, s


def unpack(packed: List[int], scale: float, n: int) -> List[float]:
    out: List[float] = []
    for byte in packed:
        a = byte & 0xF
        b = (byte >> 4) & 0xF
        if a >= 8:
            a -= 16
        if b >= 8:
            b -= 16
        out.append(a * scale)
        if len(out) < n:
            out.append(b * scale)
    bump(len(out[:n]))
    return out[:n]
