"""Held-out briefs scored for the bare builder and the studio swarm.

Each case runs ``build_playable_game`` twice: once with no hooks, once through
``StudioSession`` so the planner and QA hooks run. The report includes both
scores and the delta. Boots is ``not_measured`` when playtest is off, and that
dimension is left out of the mean. When a Godot binary is available, both
runs use ``playtest=require`` and a pass requires boots == 1.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skeleton.automation.swarm.studio.playtester import NOT_MEASURED, score_build

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


def playtest_plan() -> tuple[str, str | None]:
    """``require`` plus a binary when Godot is installed, otherwise ``off``."""
    from skeleton.forge.playtest import resolve_binary

    path, _source, _verified = resolve_binary()
    if path:
        return "require", path
    return "off", None


def run_benchmark(*, fast: bool = False, workspace_root: Path | None = None) -> dict[str, Any]:
    """Score studio against the bare builder. ``ok`` is false when a bar misses."""
    selected = [case for case in HELD_OUT_BRIEFS if case["fast"]] if fast else list(HELD_OUT_BRIEFS)
    root = Path(workspace_root) if workspace_root is not None else Path.cwd() / ".studio-eval"
    mode, binary = playtest_plan()
    require_boot = mode == "require"
    from skeleton.forge.game_builder import build_playable_game
    from skeleton.forge.game_design_spec import GOLDEN_BRIEFS

    golden_text = {item["brief"] for item in GOLDEN_BRIEFS}
    cases = []
    for case in selected:
        if case["brief"] in golden_text:
            raise RuntimeError(f"{case['id']} repeats a golden brief")
        bare = build_playable_game(case["brief"], playtest_mode=mode, binary=binary)
        studio = _run_studio(case["brief"], root / case["id"], mode, binary)
        bare_score = score_build(bare)
        studio_score = score_build(studio)
        additions = _additions(studio)
        cases.append(
            {
                "id": case["id"],
                "kind": "held_out",
                "expect_genre": case["expect_genre"],
                "playtest_mode": mode,
                "bare": {
                    "build_ok": bool(bare.get("ok")),
                    "genre": (bare.get("spec") or {}).get("genre"),
                    "score": bare_score,
                },
                "studio": {
                    "build_ok": bool(studio.get("ok")),
                    "genre": (studio.get("spec") or {}).get("genre"),
                    "score": studio_score,
                    "additions": additions,
                },
                "delta": _delta(studio_score, bare_score, additions),
            }
        )
    negatives = _negative_controls()
    positive_ok = all(_positive_ok(case, require_boot=require_boot) for case in cases)
    negative_ok = all(case["score"]["total"] <= LOW_BAR for case in negatives)
    totals = [case["studio"]["score"]["total"] for case in cases]
    bare_totals = [case["bare"]["score"]["total"] for case in cases]
    mean_total = sum(totals) / len(totals) if totals else 0.0
    bare_mean = sum(bare_totals) / len(bare_totals) if bare_totals else 0.0
    return {
        "subset": "fast" if fast else "full",
        "ok": positive_ok and negative_ok,
        "playtest_mode": mode,
        "godot": binary is not None,
        "mean_total": mean_total,
        "bare_mean_total": bare_mean,
        "mean_delta": mean_total - bare_mean,
        "low_bar": LOW_BAR,
        "positive_bar": POSITIVE_BAR,
        "cases": cases,
        "negatives": negatives,
    }


def _run_studio(brief: str, workspace: Path, mode: str, binary: str | None) -> dict[str, Any]:
    from skeleton.automation.swarm.studio.scheduler import StudioControls, StudioSession

    def builder(text: str, *, planner, qa, playtest_mode: str, out: str, deadline_s: float | None = None):
        from skeleton.forge.game_builder import build_playable_game

        kwargs: dict[str, Any] = {
            "planner": planner,
            "qa": qa,
            "playtest_mode": playtest_mode,
            "out": out,
            "overwrite": True,
            "binary": binary,
        }
        accepted = inspect.signature(build_playable_game).parameters
        if deadline_s is not None and "deadline_s" in accepted:
            kwargs["deadline_s"] = deadline_s
        elif deadline_s is not None and "deadline" in accepted:
            kwargs["deadline"] = deadline_s
        return build_playable_game(text, **kwargs)

    session = StudioSession(
        brief,
        workspace,
        controls=StudioControls(playtest_mode=mode),
        builder=builder,
    )
    session.run()
    return dict(session.build or {})


def _additions(result: Mapping[str, Any]) -> dict[str, int]:
    spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
    production = spec.get("production") if isinstance(spec.get("production"), Mapping) else {}
    qa = result.get("qa") if isinstance(result.get("qa"), Mapping) else {}
    return {
        "production_notes": 1 if production else 0,
        "qa_review": 1 if qa.get("schema_version") == "skeleton.studio.qa.v1" else 0,
    }


def _delta(studio: Mapping[str, Any], bare: Mapping[str, Any], additions: Mapping[str, int]) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "built": studio["built"] - bare["built"],
        "loop_works": studio["loop_works"] - bare["loop_works"],
        "spec_valid": studio["spec_valid"] - bare["spec_valid"],
        "total": studio["total"] - bare["total"],
        "production_notes": additions["production_notes"],
        "qa_review": additions["qa_review"],
    }
    if studio["boots"] == NOT_MEASURED or bare["boots"] == NOT_MEASURED:
        delta["boots"] = NOT_MEASURED
    else:
        delta["boots"] = studio["boots"] - bare["boots"]
    return delta


def _positive_ok(case: Mapping[str, Any], *, require_boot: bool) -> bool:
    for side in ("bare", "studio"):
        row = case[side]
        score = row["score"]
        if not (
            row["build_ok"] is True
            and row["genre"] == case["expect_genre"]
            and score["built"] == 1
            and score["loop_works"] == 1
            and score["spec_valid"] == 1
            and score["total"] >= POSITIVE_BAR
        ):
            return False
        if require_boot:
            if score["boots"] != 1:
                return False
        elif score["boots"] != NOT_MEASURED:
            return False
    additions = case["studio"]["additions"]
    return additions["production_notes"] == 1 and additions["qa_review"] == 1


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
            "score": score_build(None),
        },
    ]
