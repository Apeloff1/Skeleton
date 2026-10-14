"""Organ emitter. Unique coefficient per binding. Census is not this writer."""

from __future__ import annotations

import hashlib
from pathlib import Path

from volume_forge.catalog import HOUSES, ORGANS, VERBS
from volume_forge.kernel import SEED_FAMILY, STORED_PROSE

def _coeff(house: str, organ: str, verb: str, ordinal: int) -> int:
    return int(hashlib.sha256(f"{house}|{organ}|{verb}|{ordinal}|{SEED_FAMILY}".encode()).hexdigest()[:8], 16)

def render_module(house: str, organ: str) -> str:
    lines = [
        '"""Organ module. stored_prose=0."""',
        f"HOUSE = {house!r}",
        f"ORGAN = {organ!r}",
        "STORED_PROSE = 0",
        "MASS_CLIP = 1.1",
        "",
        "def _clip(proposed: float, prior: float) -> float:",
        "    ceiling = prior * MASS_CLIP",
        "    return ceiling if proposed > ceiling else proposed",
        "",
    ]
    names = []
    for verb_i, verb in enumerate(VERBS):
        fn = f"v_{verb}_{verb_i:02d}"
        names.append(fn)
        lines.append(f"def {fn}(prior: float) -> dict[str, object]:")
        lines.append(f"    coeff = {_coeff(house, organ, verb, verb_i)}")
        lines.append("    mass = _clip(prior * (1.0 + (coeff % 997) / 10000.0), prior)")
        lines.append(f"    return {{'house': HOUSE, 'organ': ORGAN, 'verb': {verb!r}, 'mass': mass, 'stored_prose': 0}}")
        lines.append("")
    lines.append("BINDINGS = (")
    lines.extend(f"    {fn}," for fn in names)
    lines.append(")")
    lines.append("")
    lines.append("def run(prior: float = 1.0) -> dict[str, object]:")
    lines.append("    mass = prior")
    lines.append("    last = {}")
    lines.append("    for fn in BINDINGS:")
    lines.append("        last = fn(mass)")
    lines.append("        mass = float(last['mass'])")
    lines.append("    return {'house': HOUSE, 'organ': ORGAN, 'mass': mass, 'steps': len(BINDINGS), 'stored_prose': 0, 'last': last}")
    return "\n".join(lines) + "\n"

def emit_tree(root: Path) -> dict[str, int]:
    root.mkdir(parents=True, exist_ok=True)
    files = lines = 0
    for house in HOUSES:
        house_dir = root / house
        house_dir.mkdir(parents=True, exist_ok=True)
        (house_dir / "__init__.py").write_text(f"HOUSE = {house!r}\n", encoding="utf-8")
        files += 1
        lines += 1
        for organ in ORGANS:
            text = render_module(house, organ)
            (house_dir / f"{organ}.py").write_text(text, encoding="utf-8")
            files += 1
            lines += text.count("\n")
    return {"files": files, "lines_estimated": lines}
