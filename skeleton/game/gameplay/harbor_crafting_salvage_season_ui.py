"""Live original salvage championship using the same bounded playable UI."""
from __future__ import annotations

from typing import Any, Callable

from .harbor_crafting import HarborError
from .harbor_crafting_salvage_season import (
    append_salvage_round, start_salvage_season, verify_salvage_season,
)
from .harbor_crafting_salvage_ui import play_salvage_live


def play_season_live(source: Any, board: Any, *,
                     input_fn: Callable[[str], str] = input,
                     output_fn: Callable[[str], Any] = print) -> dict[str, Any]:
    save = start_salvage_season(source, board)
    for round_index, item in enumerate(save["board"]["rounds"]):
        output_fn("Round " + str(round_index + 1) + ": " + item["id"])
        report = play_salvage_live(source, item["board"], input_fn=input_fn,
                                   output_fn=output_fn)
        if not report["state"]["complete"]:
            output_fn("Round incomplete; championship save remains at last earned round")
            break
        try:
            save = append_salvage_round(save, report["actions"], expected_tip=save["tip"])
        except HarborError as exc:
            output_fn("Round rejected: " + str(exc))
            break
        output_fn("Earned season score: " + str(save["score"]))
    verify_salvage_season(save)
    return save
