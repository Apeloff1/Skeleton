"""Held-out briefs scored on real builder results, plus negative controls.

Positive cases call ``build_playable_game`` and score its checker, core loop,
and playtest log. With playtest left off, a boot score of 1 is a failure of
the harness: nothing printed ``CORE_LOOP_OK``. Negative controls are built
from the real checker and the real core-loop executor and must stay at or
below ``LOW_BAR``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skeleton.automation.swarm.studio.playtester import score_build

LOW_BAR = 0.25
POSITIVE_BAR = 0.75

HELD_OUT_BRIEFS: tuple[dict[str, Any], ...] = (
    {
        "id": "held-out-container-horde",
        "fast": True,
        "expect_genre": "top_down_shooter",
        "brief": (
            "A small horde shooter between stacked containers. "
            "Fantasy: sodium lamps over a night freight yard. "
            "Core loop: move, aim, and clear the packs, then spend the salvage. "
            "Scope: small prototype."
        ),
    },
    {
        "id": "held-out-gantry-jump",
        "fast": False,
        "expect_genre": "platformer",
        "brief": (
            "A small side-scroll platform game on cable gantries. "
            "Fantasy: a dry dock above black water. "
            "Core loop: run and jump from gantry to gantry until the far bell. "
            "Scope: small prototype."
        ),
    },
)

BENCHMARK_BRIEFS = HELD_OUT_BRIEFS


def run_benchmark(*, fast: bool = False, workspace_root: Path | None = None) -> dict[str, Any]:
    """Score held-out builds and negative controls. ``ok`` is false when either bar misses."""
    del workspace_root  # builds use the builder's own temp dirs; kept for the CLI
    selected = [case for case in HELD_OUT_BRIEFS if case["fast"]] if fast else list(HELD_OUT_BRIEFS)
    from skeleton.forge.game_builder import build_playable_game
    from skeleton.forge.game_design_spec import GOLDEN_BRIEFS

    golden_text = {item["brief"] for item in GOLDEN_BRIEFS}
    positives = []
    for case in selected:
        if case["brief"] in golden_text:
            raise RuntimeError(f"{case['id']} repeats a golden brief")
        result = build_playable_game(case["brief"], playtest_mode="off")
        score = score_build(result)
        positives.append(
            {
                "id": case["id"],
                "kind": "held_out",
                "expect_genre": case["expect_genre"],
                "genre": (result.get("spec") or {}).get("genre"),
                "build_ok": bool(result.get("ok")),
                "score": score,
            }
        )
    negatives = _negative_controls()
    positive_ok = all(_positive_ok(case) for case in positives)
    negative_ok = all(case["score"]["total"] <= LOW_BAR and case["score"]["boots"] == 0 for case in negatives)
    totals = [case["score"]["total"] for case in positives]
    mean_total = sum(totals) / len(totals) if totals else 0.0
    return {
        "subset": "fast" if fast else "full",
        "ok": positive_ok and negative_ok and mean_total < 1.0,
        "mean_total": mean_total,
        "low_bar": LOW_BAR,
        "positive_bar": POSITIVE_BAR,
        "cases": positives,
        "negatives": negatives,
    }


def _positive_ok(case: Mapping[str, Any]) -> bool:
    score = case["score"]
    return (
        case["build_ok"] is True
        and case["genre"] == case["expect_genre"]
        and score["built"] == 1
        and score["loop_works"] == 1
        and score["spec_coverage"] == 1
        and score["boots"] == 0
        and score["total"] >= POSITIVE_BAR
        and score["total"] < 1.0
    )


def _negative_controls() -> list[dict[str, Any]]:
    from skeleton.forge.game_design_spec import compile_brief
    from skeleton.forge.gdscript_check import check_files
    from skeleton.forge.genre_project import execute_core_loop, loop_succeeded

    broken = "func _ready():\n\tprint('CORE_LOOP_OK'\n"
    problems = check_files({"scripts/autoloads/core_loop.gd": broken})
    marker = execute_core_loop({"encounters": "broken"}, "top_down_shooter")
    failed = {
        "ok": False,
        "spec": {"schema_version": "not-a-spec"},
        "check": {"ok": not problems, "problems": problems},
        "core_loop": {"passed": loop_succeeded(marker), "marker": marker},
        "playtest": {
            "passed": True,
            "status": "passed",
            "errors": [],
            "steps": [{"log_tail": "SCRIPT ERROR: Parse Error\n"}],
        },
        "proof": "CORE_LOOP_OK genre=top_down_shooter marker=dead",
        "files": {"scripts/autoloads/core_loop.gd": broken},
        "file_names": ["scripts/autoloads/core_loop.gd"],
    }
    empty_score = score_build(None)
    try:
        compile_brief("")
        empty_error = ""
    except ValueError as exc:
        empty_error = str(exc)
    return [
        {
            "id": "negative-checker-loop-and-log",
            "kind": "negative",
            "checker_problems": len(problems),
            "marker": marker,
            "score": score_build(failed),
        },
        {
            "id": "negative-empty-brief",
            "kind": "negative",
            "error": empty_error,
            "score": empty_score,
        },
    ]
