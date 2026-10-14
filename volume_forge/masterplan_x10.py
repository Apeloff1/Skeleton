"""Tenfold masterplan emitter. 200 shards, 85000 bindings. Do not commit emit100."""

from __future__ import annotations

from pathlib import Path

SHARDS = 200
FUNCS = 85000
SEED = 8847291
CLIP = 1.1

def render_shard(shard: int) -> str:
    parts = [f'"""X10 shard {shard}. stored_prose=0."""\nSHARD = {shard}\nSTORED_PROSE = 0\nCLIP = {CLIP}\nFUNCS = {FUNCS}\n\n']
    for index in range(FUNCS):
        coeff = (SEED * 10007 + shard * 100003 + index * 97) & 0xFFFFFFFF
        parts.append(
            f"def b_{shard:03d}_{index:05d}(prior: float) -> dict[str, object]:\n"
            f"    coeff = {coeff}\n"
            f"    proposed = prior * (1.0 + (coeff % 997) / 10000.0)\n"
            f"    ceiling = prior * {CLIP}\n"
            f"    mass = ceiling if proposed > ceiling else proposed\n"
            f"    return {{'shard': {shard}, 'index': {index}, 'mass': mass, 'stored_prose': 0}}\n\n"
        )
    return "".join(parts)

def emit(root: Path) -> dict[str, int]:
    root.mkdir(parents=True, exist_ok=True)
    lines = 0
    for shard in range(SHARDS):
        text = render_shard(shard)
        (root / f"shard_{shard:03d}.py").write_text(text, encoding="utf-8")
        lines += text.count("\n")
    return {"files": SHARDS, "lines_written": lines}
