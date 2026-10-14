"""Skeleton main tenfold stratum.

Bindings are 10x the 85,000 x10 shard. 200 shards do not fit this disk.
Measure shards. Project only after wc. Do not commit emit_x100.
"""

from __future__ import annotations

from pathlib import Path

SHARDS = 200
FUNCS_PER_SHARD = 850000
PRIOR_LINES = 153003200
SEED = 8847291
CLIP = 1.1


def _fn(shard: int, index: int) -> str:
    coeff = (SEED * 10007 + shard * 100003 + index * 97) & 0xFFFFFFFF
    return (
        f"def b_{shard:03d}_{index:06d}(prior: float) -> dict[str, object]:\n"
        f"    coeff = {coeff}\n"
        f"    proposed = prior * (1.0 + (coeff % 997) / 10000.0)\n"
        f"    ceiling = prior * {CLIP}\n"
        f"    if proposed < 0:\n"
        f"        raise ValueError('mass')\n"
        f"    mass = ceiling if proposed > ceiling else proposed\n"
        f"    return {{'shard': {shard}, 'index': {index}, 'coeff': coeff, 'mass': mass, 'stored_prose': 0}}\n\n"
    )


def render_shard(shard: int) -> str:
    parts = [
        '"""Skeleton x100 shard. stored_prose=0. clip 1.1."""\n',
        f"SHARD = {shard}\nSEED = {SEED}\nSTORED_PROSE = 0\nCLIP = {CLIP}\nFUNCS = {FUNCS_PER_SHARD}\n\n",
    ]
    parts.extend(_fn(shard, i) for i in range(FUNCS_PER_SHARD))
    parts.append("def run(prior: float = 1.0) -> dict[str, object]:\n    return b_%03d_000000(prior)\n" % shard)
    return "".join(parts)


def emit_some(root: Path, n: int = 1) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for shard in range(n):
        path = root / f"shard_{shard:03d}.py"
        path.write_text(render_shard(shard), encoding="utf-8")
        print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    import sys
    emit_some(Path(sys.argv[1] if len(sys.argv) > 1 else "emit_x100"), int(sys.argv[2]) if len(sys.argv) > 2 else 1)
