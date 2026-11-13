"""skeleton/gameforge/steps.py

Pure, deterministic implementations of the seven GameForge steps.
Randomness is derived from a seed via SHA-256 so runs are reproducible.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple

from .eras import Era
from .errors import BudgetError, InputError
from .plans import (
    AssetSpec, CockpitPlan, Control, ExportPlan, EXPORT_TARGETS, Feature, MassPlan, Mechanic, PrototypePlan,
    Region, SnowballPlan, VisionPlan, VisionRequest, WorldPlan, slugify,
)
from .safety import screen_paths, screen_script, screen_text

_GENRE_LOOPS: Dict[str, Tuple[str, ...]] = {
    "platformer": ("run", "jump", "collect", "reach_goal"),
    "puzzle": ("observe", "manipulate", "solve"),
    "rpg": ("explore", "fight", "loot", "level_up"),
    "shooter": ("move", "aim", "shoot", "survive"),
    "strategy": ("gather", "build", "command", "conquer"),
    "racing": ("steer", "boost", "overtake", "finish"),
    "adventure": ("explore", "talk", "solve", "progress"),
    "sandbox": ("gather", "craft", "build", "share"),
}
_VERB_KEYS = {
    "run": "Left/Right", "jump": "Space", "collect": "E", "reach_goal": "Enter", "observe": "Tab",
    "manipulate": "Mouse1", "solve": "Enter", "explore": "WASD", "fight": "Mouse1", "loot": "E",
    "level_up": "L", "move": "WASD", "aim": "Mouse", "shoot": "Mouse1", "survive": "Shift",
    "gather": "G", "build": "B", "command": "Mouse2", "conquer": "C", "steer": "A/D", "boost": "Shift",
    "overtake": "W", "finish": "Enter", "talk": "T", "progress": "Enter", "craft": "R", "share": "P",
}


def seeded_int(seed: str, *parts: object, mod: int) -> int:
    h = hashlib.sha256(":".join([seed, *map(str, parts)]).encode()).digest()
    return int.from_bytes(h[:8], "big") % mod


def vision(req: VisionRequest) -> VisionPlan:
    screen_text("vision", req.title, req.pitch, *req.pillars)
    if not req.title.strip() or not req.pitch.strip():
        raise InputError("title and pitch required", step="vision")
    pillars = req.pillars or ("fun",)
    plan = VisionPlan(slugify(req.title), req.title.strip(), req.pitch.strip(), req.genre, req.era,
                      tuple(p.strip().lower() for p in pillars), req.target_minutes)
    plan.validate()
    return plan


def snowball(v: VisionPlan) -> SnowballPlan:
    loop = _GENRE_LOOPS[v.genre]
    feats: List[Feature] = []
    for i, beat in enumerate(loop):
        pillar = v.pillars[i % len(v.pillars)]
        prio = 1 if i < 2 else (2 if i < 3 else 3)
        cost = 1 + seeded_int(v.game_id, "cost", beat, mod=5)
        feats.append(Feature(f"f_{beat}", pillar, prio, cost))
    for p in v.pillars:
        feats.append(Feature(f"f_pillar_{slugify(p).replace('-', '_')}", p, 2, 2))
    feats.sort(key=lambda f: f.key)
    dedup: Dict[str, Feature] = {}
    for f in feats:
        dedup.setdefault(f.key, f)
    plan = SnowballPlan(v.game_id, loop, tuple(dedup.values()))
    plan.validate(v)
    return plan


def prototype(v: VisionPlan, s: SnowballPlan) -> PrototypePlan:
    mechs: List[Mechanic] = []
    for f in s.features:
        if f.priority > 2:
            continue
        beat = f.key[2:]
        verbs = (beat,) if beat in _VERB_KEYS else ()
        mechs.append(Mechanic(f"m_{beat}", f.key, verbs))
    seconds = min(v.target_minutes * 60, 30 * len(mechs))
    plan = PrototypePlan(v.game_id, tuple(mechs), seconds)
    plan.validate(s)
    return plan


_KIND_SIZES = {"sprite": 4096, "tile": 2048, "sound": 16384, "music": 131072, "script": 1024,
               "level": 8192, "model": 65536, "shader": 2048}


def mass_forge(v: VisionPlan, p: PrototypePlan, era: Era, budget_bytes: int) -> MassPlan:
    if budget_bytes <= 0:
        raise BudgetError("budget must be positive", step="mass_forge")
    wanted: List[AssetSpec] = []
    for m in p.mechanics:
        base = m.key[2:]
        wanted.append(AssetSpec(f"scripts/{base}.gs", "script", _KIND_SIZES["script"], (m.feature,)))
        wanted.append(AssetSpec(f"sprites/{base}.png", "sprite", _KIND_SIZES["sprite"], (m.feature,)))
        wanted.append(AssetSpec(f"sounds/{base}.wav", "sound", _KIND_SIZES["sound"], (m.feature,)))
    wanted.append(AssetSpec("music/theme.ogg", "music", _KIND_SIZES["music"], ("theme",)))
    if era.allows("model"):
        wanted.append(AssetSpec("models/hero.glb", "model", _KIND_SIZES["model"], ("hero",)))
    wanted = [a for a in wanted if era.allows(a.kind)]
    # clip lowest value first: music, models, sounds, then sprites; scripts are essential
    order = {"music": 0, "model": 1, "sound": 2, "sprite": 3, "tile": 3, "level": 4, "shader": 1, "script": 9}
    total = sum(a.size for a in wanted)
    clipped: List[str] = []
    for a in sorted(wanted, key=lambda a: (order[a.kind], a.path)):
        if total <= budget_bytes:
            break
        if a.kind == "script":
            break
        total -= a.size
        clipped.append(a.path)
    if total > budget_bytes:
        raise BudgetError(f"essential assets need {total} bytes > budget {budget_bytes}", step="mass_forge",
                          detail={"needed": total, "budget": budget_bytes})
    keep = tuple(sorted((a for a in wanted if a.path not in clipped), key=lambda a: a.path))
    plan = MassPlan(v.game_id, keep, budget_bytes, tuple(sorted(clipped)))
    plan.validate()
    return plan


def world(v: VisionPlan, era: Era, regions: int = 5) -> WorldPlan:
    if not (1 <= regions <= 64):
        raise InputError("regions must be 1..64", step="world")
    seed = seeded_int(v.game_id, "world", era.key, mod=2 ** 31)
    keys = [f"r{i:02d}" for i in range(regions)]
    per = max(1, era.max_entities // (regions * 2))
    out: List[Region] = []
    for i, k in enumerate(keys):
        nbrs = set()
        if i > 0:
            nbrs.add(keys[i - 1])
        extra = seeded_int(str(seed), k, mod=regions)
        if extra != i:
            nbrs.add(keys[extra])
        ents = 1 + seeded_int(str(seed), k, "ents", mod=per)
        out.append(Region(k, tuple(sorted(nbrs)), ents))
    plan = WorldPlan(v.game_id, seed, tuple(out), keys[0])
    plan.validate(era.max_entities)
    return plan


def cockpit(v: VisionPlan, p: PrototypePlan) -> CockpitPlan:
    verbs = sorted({vb for m in p.mechanics for vb in m.verbs})
    used: Dict[str, str] = {}
    controls: List[Control] = []
    for vb in verbs:
        key = _VERB_KEYS.get(vb, vb.upper())
        if key in used:
            key = f"{key}+{vb[0].upper()}"
        used[key] = vb
        controls.append(Control(vb, key))
    controls.append(Control("pause", "Escape"))
    hud = ("health", "score") if v.genre not in ("puzzle",) else ("moves", "timer")
    plan = CockpitPlan(v.game_id, tuple(controls), hud, ("remappable_controls", "subtitles", "colorblind_palette"))
    plan.validate(p)
    return plan


def render_artifacts(v: VisionPlan, mass: MassPlan, w: WorldPlan, c: CockpitPlan) -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    for a in mass.assets:
        if a.kind == "script":
            src = f"# {a.path} for {v.game_id}\non_tick(state) -> state\n"
            screen_script("export", a.path, src)
            files[a.path] = src.encode()
        else:
            files[a.path] = hashlib.sha256(f"{v.game_id}:{a.path}".encode()).digest() * (a.size // 32)
    files["world.txt"] = "\n".join(f"{r.key} {r.entities} {','.join(r.neighbors)}" for r in w.regions).encode()
    files["controls.txt"] = "\n".join(f"{x.action}={x.binding}" for x in c.controls).encode()
    return dict(sorted(files.items()))


def export(v: VisionPlan, files: Dict[str, bytes], target: str) -> ExportPlan:
    if target not in EXPORT_TARGETS:
        raise InputError(f"unknown export target {target!r}", step="export")
    screen_paths("export", files)
    return ExportPlan(v.game_id, target, tuple(sorted(files)))
