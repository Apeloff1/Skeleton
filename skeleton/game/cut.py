"""Cut sets the cockpit era overlay. Numbers stay in data tables."""

from __future__ import annotations

from typing import Any

from skeleton.game.era_bind import ALLOWED_ERAS, HOUSE_ERA, bind_era


class CutError(ValueError):
    """Cut / era overlay contract violation."""


def cut(era: str | None = None, *, title: str = "NEXUS-EXTRACT") -> dict[str, Any]:
    name = str(era or HOUSE_ERA).strip().lower()
    if name not in ALLOWED_ERAS:
        raise CutError(f"unknown era: {era}")
    reference = bind_era(era=name, title=title, citation="#807")
    return {
        "kind": "cut",
        "overlay": name,
        "reference": reference,
        "retune": False,
        "stored_prose": 0,
    }


def plan_sees(overlay: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(overlay, dict) or overlay.get("kind") != "cut":
        raise CutError("cut overlay required")
    era = str(overlay["overlay"])
    return {
        "kind": "plan",
        "era": era,
        "reference": overlay["reference"],
        "stored_prose": 0,
    }
