"""Game Spec card. Questionnaire fields only. Conflicts listed, never dropped."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.era_bind import HOUSE_ERA, bind_era
from skeleton.game.intent import compile_intent


FIELDS = ("loop", "combat", "economy", "forge", "emit", "quality")


class SpecError(ValueError):
    """Game spec contract violation."""


def compile_spec(
    vision: str,
    *,
    era: str = HOUSE_ERA,
    answers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blob = str(vision or "").strip()
    if not blob:
        raise SpecError("vision required")
    intent = compile_intent(blob)
    raw = dict(answers or {})
    chosen = [field for field in FIELDS if field in intent["fields"] or raw.get(field)]
    if not chosen:
        chosen = ["loop"]
    conflicts = list(intent["conflicts"])
    if "emit" in chosen and raw.get("engine") in {"unity", "phaser"}:
        conflicts.append("emit-engine")
    reference = bind_era(era=era, title="NEXUS-EXTRACT", citation="#807")
    return {
        "kind": "game-spec",
        "fields": chosen,
        "conflicts": conflicts,
        "intent": intent,
        "reference": reference,
        "seed_family": 8847291,
        "stored_prose": 0,
        "ok": True,
    }
