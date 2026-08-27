"""Jeeves-as-builder — designs the run before the forge emits it.

Tactical Jeeves coaches a live operator. This brain is the other half:
it reads the context cube, the dodeca oracle, and the compiled era pack,
then writes a BuildPlan the world generator and Godot emitter obey.

Closed loop: a prior walk (or a recalled forge-run tract) mutates mix,
bias, and extract-lateness, and is mixed into the seed so the next graph
is a different building. Deterministic given (era, tensor, oracle, walk).
No LLM. No weights.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.context.oracle import OracleReading
from skeleton.context.tensor import ContextTensor


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


@dataclass(frozen=True)
class BuildPlan:
    era: str
    seed: str
    tensor_fp: str
    oracle_index: int
    oracle_text: str
    briefing: str
    room_bias: str
    spawn_weapon: bool
    extract_late: bool
    enemy_mix: Dict[str, int]
    recipes: List[str]
    notes: List[str] = field(default_factory=list)
    adapt: str = "none"
    slack: float = 1.0
    authored: str = "local"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "seed": self.seed,
            "tensor_fp": self.tensor_fp,
            "oracle_index": self.oracle_index,
            "oracle_text": self.oracle_text,
            "briefing": self.briefing,
            "room_bias": self.room_bias,
            "spawn_weapon": self.spawn_weapon,
            "extract_late": self.extract_late,
            "enemy_mix": dict(self.enemy_mix),
            "recipes": list(self.recipes),
            "notes": list(self.notes),
            "adapt": self.adapt,
            "slack": round(self.slack, 4),
            "authored": self.authored,
        }


def _walk_from_cortex(cortex: Any, era: str) -> Optional[Dict[str, Any]]:
    if cortex is None or not hasattr(cortex, "recall"):
        return None
    rec = cortex.recall(f"forge run {era} extract hops cores bias")
    composed = (rec or {}).get("composed") or {}
    thought = composed.get("thought") or {}
    text = str(thought.get("text") or "").lower()
    if "forge run" not in text:
        return None
    extracted = "extract true" in text or " extracted" in text
    collapsed = "collapse" in text and "extract true" not in text
    hops = 0
    if "hops" in text:
        for tok in text.split():
            if tok.isdigit():
                hops = int(tok)
                break
    return {
        "extracted": extracted and not collapsed,
        "collapsed": collapsed,
        "t": 0.0,
        "fights": 0,
        "hops": hops,
        "from_recall": True,
    }


def adapt_from_walk(
    pack: Dict[str, Any],
    *,
    bias: str,
    spawn_weapon: bool,
    extract_late: bool,
    trash: int,
    elite: int,
    boss: int,
    walk: Optional[Dict[str, Any]],
) -> Tuple[str, bool, bool, int, int, int, str, float, List[str]]:
    """Mutate a plan from a prior walk. Falsifiable: same walk → same tag."""
    notes: List[str] = []
    collapse = float((pack.get("session") or {}).get("collapse_max") or 9999.0)
    if not walk:
        return bias, spawn_weapon, extract_late, trash, elite, boss, "none", 1.0, notes
    extracted = bool(walk.get("extracted"))
    collapsed = bool(walk.get("collapsed"))
    t = float(walk.get("t") or 0.0)
    fights = int(walk.get("fights") or 0)
    hops = int(walk.get("hops") or 0)
    slack = ((collapse - t) / collapse) if (extracted and collapse > 0 and t > 0) else (
        0.0 if (collapsed or not extracted) else 1.0
    )
    if collapsed or not extracted:
        extract_late = False
        spawn_weapon = True
        trash = max(1, trash - 1)
        boss = 0
        elite = max(0, elite - 1)
        bias = "loot"
        tag = "ease"
        notes.append("cortex: last walk failed — ease extract, arm the spawn")
    elif slack < 0.25:
        extract_late = False
        trash = max(1, trash - 1)
        tag = "tighten"
        notes.append(f"cortex: slack={slack:.2f} hops={hops} — drop late extract")
    elif slack > 0.80 and fights <= 1:
        elite = max(elite, 1)
        trash = min(6, trash + 1)
        tag = "harden"
        notes.append(f"cortex: slack={slack:.2f} fights={fights} — harden mix")
    else:
        tag = "hold"
        notes.append(f"cortex: slack={slack:.2f} — hold the last plan grain")
    return bias, spawn_weapon, extract_late, trash, elite, boss, tag, slack, notes


def _prune_mix(
    pack: Dict[str, Any], trash: int, elite: int, boss: int,
) -> Tuple[int, int, int, float, List[str]]:
    """Left-brain veto: sequential thermal kills must fit inside 70% of collapse."""
    from skeleton.forge.sim import simulate_encounter
    notes: List[str] = []
    collapse = float((pack.get("session") or {}).get("collapse_max") or 9999.0)
    budget = collapse * 0.70
    enemies = {str(e.get("id")): e for e in (pack.get("enemies") or [])}

    def span(tsh: int, elt: int, bs: int) -> Tuple[float, bool]:
        heat = 0.0
        tot = 0.0
        for tier, n in (("trash", tsh), ("elite", elt), ("boss", bs)):
            enemy = enemies.get(tier)
            if enemy is None or n <= 0:
                continue
            for _ in range(n):
                remaining = max(0.05, budget - tot)
                r = simulate_encounter(pack, enemy, mode="thermal", heat0=heat, max_t=remaining)
                tot += float(r.measured_ttk)
                heat = float(r.heat_end)
                if (not r.killed) or tot > budget:
                    return tot, False
        return tot, True

    dropped: List[str] = []
    while True:
        tot, ok = span(trash, elite, boss)
        if ok:
            if dropped:
                notes.append("left-veto dropped " + ",".join(dropped) + f" thermal_span={tot:.1f}s")
            else:
                notes.append(f"left-veto thermal_span={tot:.1f}s/{budget:.1f}s")
            return trash, elite, boss, tot, notes
        if boss:
            boss = 0
            dropped.append("boss")
            continue
        if elite:
            elite -= 1
            dropped.append("elite")
            continue
        if trash > 1:
            trash -= 1
            dropped.append("trash")
            continue
        notes.append(f"left-veto mix irreducible thermal_span={tot:.1f}s")
        return trash, elite, boss, tot, notes


def _bias_of(right: Any) -> str:
    tags = tuple(getattr(right, "tags", ()) or ())
    text = str(getattr(right, "text", "") or "").lower()
    for b in ("loot", "heat", "combat", "balanced"):
        if b in tags or f"bias={b}" in text:
            return b
    return "balanced"


def _mix_of(left: Any) -> Optional[Tuple[int, int, int]]:
    nums = tuple(getattr(left, "numbers", ()) or ())
    if len(nums) < 3:
        return None
    trash, elite, boss = int(nums[-3]), int(nums[-2]), int(nums[-1])
    if 0 <= trash <= 8 and 0 <= elite <= 4 and 0 <= boss <= 2:
        return trash, elite, boss
    return None


def _author(pack: Dict[str, Any], cube: ContextTensor, era: str, cortex: Any):
    ctx = {
        "era": era,
        "tensor": cube.as_dict() if hasattr(cube, "as_dict") else {},
        "pack_dps": pack.get("primary_dps"),
        "pack_ttk": pack.get("ttk"),
        "collapse_max": (pack.get("session") or {}).get("collapse_max"),
    }
    stim = f"plan {era} forge mix bias ttk extract"
    if cortex is not None:
        trace = cortex.think(stim, ctx)
        left, right, pfc = trace.left, trace.right, trace.pfc
        slots = getattr(cortex, "slots", None) or {}
        if left is None and "left" in slots:
            left = slots["left"].think(stim, ctx)
        if right is None and "right" in slots:
            right = slots["right"].think(stim, ctx)
        authored = "own" if getattr(trace, "used_own", False) else "cortex"
        amalgam = getattr(trace, "amalgam", None)
        if authored == "own" and amalgam is not None:
            if _mix_of(amalgam) is not None:
                left = amalgam
            if _bias_of(amalgam) != "balanced":
                right = amalgam
        return left, right, pfc, authored
    from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
    from skeleton.cortex.pfc import PrefrontalCortex
    left = LeftHemisphere().think(stim, ctx)
    right = RightHemisphere().think(stim, {**ctx, "left": left.to_dict()})
    pfc = PrefrontalCortex().think(stim, {**ctx, "left": left.to_dict(), "right": right.to_dict()})
    return left, right, pfc, "local"


class BuilderBrain:
    """Forge collaborator. Bind a pack, then plan(tensor, reading, walk)."""

    def plan(
        self,
        pack: Dict[str, Any],
        *,
        tensor: Optional[ContextTensor] = None,
        reading: Optional[OracleReading] = None,
        cortex: Any = None,
        last_walk: Optional[Dict[str, Any]] = None,
    ) -> BuildPlan:
        era = str(pack.get("era") or "extraction_now")
        cube = tensor or ContextTensor.from_era(era.split("~")[0])
        fp = cube.fingerprint()
        oracle_index = int(reading.index) if reading is not None else -1
        oracle_text = reading.text if reading is not None else "Signs point to a standard drop."

        left, right, pfc, authored = _author(pack, cube, era, cortex)
        bias = _bias_of(right)
        mix = _mix_of(left)
        lethality = cube["lethality"]
        tempo = cube["tempo"]
        risk = cube["risk"]
        scarcity = cube["scarcity"]
        if mix is not None:
            trash, elite, boss = mix
        else:
            trash = 1 + int(round(_clamp(tempo) * 3))
            elite = (1 if lethality >= 0.50 else 0) + (1 if lethality >= 0.80 else 0)
            boss = 1 if (risk >= 0.75 and lethality >= 0.60) else 0

        spawn_weapon = tempo >= 0.75 or lethality < 0.20 or scarcity < 0.35
        extract_late = risk >= 0.70
        if pfc is not None and (
            "veto" in (pfc.tags or ()) or (pfc.numbers and pfc.numbers[-1] >= 1.0)
        ):
            spawn_weapon = True
            extract_late = False

        walk = last_walk or _walk_from_cortex(cortex, era)
        bias, spawn_weapon, extract_late, trash, elite, boss, tag, slack, adapt_notes = adapt_from_walk(
            pack, bias=bias, spawn_weapon=spawn_weapon, extract_late=extract_late,
            trash=trash, elite=elite, boss=boss, walk=walk,
        )
        trash, elite, boss, thermal_span, veto_notes = _prune_mix(pack, trash, elite, boss)

        seed_src = f"{era}|{fp}|{oracle_index}"
        if tag != "none":
            seed_src += f"|{tag}|{int(extract_late)}|{trash}|{elite}|{boss}"
        seed = hashlib.sha256(seed_src.encode()).hexdigest()[:16]

        recipes = [r.get("id") for r in (pack.get("recipes") or []) if r.get("id")]
        if spawn_weapon:
            first = recipes[:1] or ["kinetic_basic"]
        else:
            first = recipes[:2] or ["kinetic_basic"]

        philosophy = (pack.get("meta") or {}).get("philosophy") or "risk_session_value"
        notes = [
            f"bias={bias}",
            f"mix trash={trash} elite={elite} boss={boss}",
            f"armed={int(spawn_weapon)} late_extract={int(extract_late)}",
            f"philosophy={philosophy}",
            f"adapt={tag} slack={slack:.2f}",
            f"thermal_span={thermal_span:.1f}s",
            f"authored={authored}",
        ] + adapt_notes + veto_notes
        briefing = (
            f"Jeeves / {era}: {oracle_text} "
            f"Drop {bias}-weighted. "
            + ("You spawn with a kit." if spawn_weapon else "Scavenge a barrel before the first fight.")
            + (" Extract is late — value the cores." if extract_late else " Extract is honest; don't greed.")
            + (f" Cortex {tag}." if tag != "none" else "")
            + f" Authored {authored}/{bias}."
        )
        return BuildPlan(
            era=era,
            seed=seed,
            tensor_fp=fp,
            oracle_index=oracle_index,
            oracle_text=oracle_text,
            briefing=briefing.strip(),
            room_bias=bias,
            spawn_weapon=spawn_weapon,
            extract_late=extract_late,
            enemy_mix={"trash": trash, "elite": elite, "boss": boss},
            recipes=first,
            notes=notes,
            adapt=tag,
            slack=slack,
            authored=authored,
        )
