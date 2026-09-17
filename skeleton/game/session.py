"""Compose replay + AI + harbor + clipped mass + era bind into one digest."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from skeleton.game.ai_policy import run_policy
from skeleton.game.era_bind import HOUSE_ERA, bind_era
from skeleton.game.harbor import Harbor
from skeleton.game.mass import observe_mass, trajectory
from skeleton.game.mechanics import AIBehaviorSpec
from skeleton.game.pack import validate_pack
from skeleton.game.replay import record


SESSION_KIND = "skeleton.game.session"


def _dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def run_session(
    *,
    seed: int | str,
    inputs: list[Mapping[str, Any]] | None = None,
    pack: Mapping[str, Any] | None = None,
    era: str = HOUSE_ERA,
    mass0: float = 1.0,
    forges: int = 3,
) -> dict[str, Any]:
    default_pack = {
        "combat": {"style": "turn_based", "include_magic": True},
        "economy": {"currencies": ["scrap", "parts"]},
        "progression": {"style": "linear", "max_level": 20},
        "ai": {
            "entity_type": "stalker",
            "behaviors": ["patrol", "chase"],
            "aggression_level": 0.6,
            "intelligence_level": 0.4,
        },
    }
    pack_card = validate_pack(pack or default_pack)
    trace = record(seed=seed, inputs=list(inputs or []), spec=pack or {}, hz=60)
    ai_spec = AIBehaviorSpec(
        entity_type=str(pack_card["ai_entity"] or "stalker"),
        behaviors=("patrol", "chase"),
        aggression_level=0.6,
        intelligence_level=0.4,
    )
    ai_frames = run_policy(ai_spec, seed=int(trace.seed), ticks=max(1, len(trace.frames)))
    harbor = Harbor(weights={"scrap": 0.6, "parts": 0.4})
    harbor.put("scrap", 2).put("parts", 1).take("scrap", 1)
    mass_path = trajectory(mass0, forges)
    mass_card = observe_mass(g=mass_path[-1], g0=mass_path[0], citation="#807")
    reference = bind_era(era=era, title="NEXUS-EXTRACT", citation="#807")
    body: dict[str, Any] = {
        "kind": SESSION_KIND,
        "replay_digest": trace.digest,
        "ai": ai_frames,
        "harbor": harbor.snapshot(),
        "mass": mass_card,
        "trajectory": mass_path,
        "reference": reference,
        "pack": pack_card,
        "frames": len(trace.frames),
        "stored_prose": 0,
    }
    body["digest"] = hashlib.sha256(_dumps(body).encode("utf-8")).hexdigest()
    body["ok"] = True
    return body
