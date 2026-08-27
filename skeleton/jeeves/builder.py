"""Jeeves-as-builder — designs the run before the forge emits it.

Tactical Jeeves coaches a live operator. This brain is the other half:
it reads the context cube, the dodeca oracle, and the compiled era pack,
then writes a BuildPlan the world generator and Godot emitter obey.

Deterministic given (era, tensor fingerprint, oracle index). No LLM.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
        }


class BuilderBrain:
    """Forge collaborator. Bind a pack, then plan(tensor, reading)."""

    def plan(
        self,
        pack: Dict[str, Any],
        *,
        tensor: Optional[ContextTensor] = None,
        reading: Optional[OracleReading] = None,
    ) -> BuildPlan:
        era = str(pack.get("era") or "extraction_now")
        cube = tensor or ContextTensor.from_era(era.split("~")[0])
        fp = cube.fingerprint()
        oracle_index = int(reading.index) if reading is not None else -1
        oracle_text = reading.text if reading is not None else "Signs point to a standard drop."
        seed_src = f"{era}|{fp}|{oracle_index}"
        seed = hashlib.sha256(seed_src.encode()).hexdigest()[:16]

        lethality = cube["lethality"]
        tempo = cube["tempo"]
        risk = cube["risk"]
        grind = cube["grind"]
        scarcity = cube["scarcity"]
        spectacle = cube["spectacle"]

        if grind >= 0.62 and grind >= lethality:
            bias = "loot"
        elif scarcity >= 0.75 and lethality >= 0.55:
            bias = "heat"
        elif tempo >= 0.72 or lethality >= 0.80:
            bias = "combat"
        else:
            bias = "balanced"

        spawn_weapon = tempo >= 0.75 or lethality < 0.20 or scarcity < 0.35
        extract_late = risk >= 0.70

        trash = 1 + int(round(_clamp(tempo) * 3))
        elite = (1 if lethality >= 0.50 else 0) + (1 if lethality >= 0.80 else 0)
        boss = 1 if (risk >= 0.75 and lethality >= 0.60) else 0
        if spectacle >= 0.80 and boss == 0:
            elite = max(elite, 1)

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
        ]
        briefing = (
            f"Jeeves / {era}: {oracle_text} "
            f"Drop {bias}-weighted. "
            + ("You spawn with a kit." if spawn_weapon else "Scavenge a barrel before the first fight.")
            + (" Extract is late — value the cores." if extract_late else " Extract is honest; don't greed.")
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
        )
