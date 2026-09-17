"""Doctor cycle on the weakest critique axis. Does not retune live knobs."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.critique import AXES, critique, improve


BUMP = 0.05


class DoctorError(ValueError):
    """Doctor cycle contract violation."""


def doctor(scores: Mapping[str, Any] | None, *, seed: int) -> dict[str, Any]:
    card = improve(scores, seed=int(seed))
    taste = card["critique"]
    axis = str(taste["doctor"])
    if axis not in AXES:
        raise DoctorError("unknown doctor axis")
    regenerated = dict(taste["axes"])
    regenerated[axis] = min(1.0, regenerated[axis] + BUMP)
    after = critique(regenerated)
    return {
        "kind": "doctor",
        "before": taste,
        "after": after,
        "axis": axis,
        "retune": False,
        "live_knobs": False,
        "seed": int(seed),
        "stored_prose": 0,
    }
