"""B100 structural arena. Sealed replays only. Never flips sota_ready."""

from __future__ import annotations

from typing import Any

from skeleton.game.conductor import execute
from skeleton.game.replay import record, verify
from skeleton.game.world_graph import place, walk


MAX_SEEDS = 8
DEFAULT_FAMILY = (8847291, 8847292, 8847293, 8847294)


class ArenaError(ValueError):
    """Arena contract violation."""


def run_arena(seeds: tuple[int, ...] | list[int] | None = None) -> dict[str, Any]:
    family = tuple(seeds or DEFAULT_FAMILY)
    if not family or len(family) > MAX_SEEDS:
        raise ArenaError("seed family out of range")
    rows = []
    for seed in family:
        trace = record(
            seed=int(seed),
            inputs=[
                {"t": 0, "verb": "attack"},
                {"t": 1, "verb": "defend"},
                {"t": 2, "verb": "wait"},
            ],
        )
        check = verify(trace.to_dict())
        graph = place(seed=int(seed), rooms=4)
        walked = walk(graph)
        rows.append(
            {
                "seed": int(seed),
                "digest": check["digest"],
                "frames": check["frames"],
                "extracted": walked["extracted"],
                "warp_count": walked["warp_count"],
            }
        )
    digests = {row["digest"] for row in rows}
    extracts = {row["extracted"] for row in rows}
    run = execute(seed=int(family[0]), forges=3)
    return {
        "kind": "arena",
        "n": len(rows),
        "rows": rows,
        "unique_digests": len(digests),
        "extract_ok": extracts == {1},
        "conductor_ok": bool(run.get("ok")),
        "evidence": "eval-partial",
        "sota_ready": False,
        "law": "batch_complete_is_not_sota",
        "stored_prose": 0,
        "ok": True,
    }
