"""QA scoring for a ``build_playable_game`` result.

Scores come from the checker, the core-loop marker, and the Godot playtest
log. A boot is 1 only when the playtest passed and the log contains
``CORE_LOOP_OK`` plus the builder's proof line. When playtest did not run,
boots is ``not_measured`` and is left out of the mean. ``spec_valid`` checks
the design-spec schema. This module does not simulate a game.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

QA_SCHEMA = "skeleton.studio.qa.v1"
CORE_LOOP_OK = "CORE_LOOP_OK"
NOT_MEASURED = "not_measured"
_GENRES = frozenset({"top_down_shooter", "platformer", "rpg_roguelike"})


def review_build(build: Mapping[str, Any]) -> dict[str, Any]:
    """File issues against checker problems, the core loop, and the Godot log."""
    issues: list[dict[str, str]] = []
    check = build.get("check") if isinstance(build.get("check"), Mapping) else {}
    problems = [str(item) for item in (check.get("problems") or []) if str(item).strip()]
    check_ok = bool(check.get("ok")) and not problems
    if not check_ok:
        for problem in problems or ["checker failed"]:
            issues.append({"severity": "blocker", "source": "checker", "detail": problem[:300]})
    core = build.get("core_loop") if isinstance(build.get("core_loop"), Mapping) else {}
    marker = str(core.get("marker") or "")
    loop_ok = bool(core.get("passed")) and bool(marker.strip())
    if not loop_ok:
        issues.append({"severity": "blocker", "source": "core_loop", "detail": f"marker {marker!r}"[:300]})
    play = build.get("playtest") if isinstance(build.get("playtest"), Mapping) else None
    log = _log_text(play)
    proof = str(build.get("proof") or "")
    if play is None:
        issues.append({"severity": "info", "source": "playtest", "detail": "playtest not run"})
    elif play.get("status") == "unavailable":
        reason = str(play.get("reason") or play.get("status") or "unavailable")
        issues.append({"severity": "info", "source": "playtest", "detail": f"godot binary unavailable: {reason}"[:300]})
    else:
        if play.get("passed") is not True:
            errors = [str(item) for item in (play.get("errors") or []) if str(item).strip()]
            for error in errors or ["playtest failed"]:
                issues.append({"severity": "blocker", "source": "playtest", "detail": error[:300]})
        if CORE_LOOP_OK not in log:
            issues.append({"severity": "blocker", "source": "playtest", "detail": "CORE_LOOP_OK missing from godot log"})
        elif proof and proof not in log:
            issues.append({"severity": "blocker", "source": "playtest", "detail": "proof line missing from godot log"})
    blockers = [item for item in issues if item["severity"] == "blocker"]
    passed = not blockers and check_ok and loop_ok
    return {
        "schema_version": QA_SCHEMA,
        "passed": passed,
        "issues": issues,
        "summary": "no blockers" if passed else f"{len(blockers)} blockers",
        "score": score_build(build),
    }


def score_build(build: Mapping[str, Any] | None) -> dict[str, Any]:
    """Score one build result. Empty and failed results stay low."""
    if not isinstance(build, Mapping):
        return _score(0, 0, 0, 0)
    names = set()
    files = build.get("files") if isinstance(build.get("files"), Mapping) else {}
    names.update(str(name) for name in files)
    for name in build.get("file_names") or []:
        names.add(str(name))
    check = build.get("check") if isinstance(build.get("check"), Mapping) else {}
    problems = [str(item) for item in (check.get("problems") or []) if str(item).strip()]
    check_ok = bool(check.get("ok")) and not problems
    built = 1 if "project.godot" in names and check_ok else 0
    core = build.get("core_loop") if isinstance(build.get("core_loop"), Mapping) else {}
    loop_works = 1 if bool(core.get("passed")) and str(core.get("marker") or "").strip() else 0
    boots = _boots(build)
    spec = build.get("spec") if isinstance(build.get("spec"), Mapping) else {}
    spec_ok = (
        spec.get("schema_version") == "skeleton.game_design_spec.v1"
        and spec.get("engine") == "godot4"
        and spec.get("genre") in _GENRES
        and isinstance(spec.get("spec_id"), str)
        and len(spec.get("spec_id") or "") == 64
    )
    return _score(built, boots, loop_works, 1 if spec_ok else 0)


def _boots(build: Mapping[str, Any]) -> int | str:
    """1 or 0 when a playtest ran. ``not_measured`` when it did not."""
    play = build.get("playtest") if isinstance(build.get("playtest"), Mapping) else None
    if play is None or play.get("status") in {"unavailable", "off"}:
        return NOT_MEASURED
    if play.get("status") is None and "passed" not in play and not play.get("steps") and not play.get("errors"):
        return NOT_MEASURED
    log = _log_text(play)
    proof = str(build.get("proof") or "")
    if (
        play.get("passed") is True
        and CORE_LOOP_OK in log
        and (not proof or proof in log)
    ):
        return 1
    return 0


def _score(built: int, boots: int | str, loop_works: int, spec_valid: int) -> dict[str, Any]:
    measured = [built, loop_works, spec_valid]
    if boots != NOT_MEASURED:
        measured.append(boots)
    total = sum(measured) / len(measured)
    return {
        "built": built,
        "boots": boots,
        "loop_works": loop_works,
        "spec_valid": spec_valid,
        "total": total,
    }


def _log_text(report: Mapping[str, Any] | None) -> str:
    if not isinstance(report, Mapping):
        return ""
    chunks = []
    for step in report.get("steps") or []:
        if isinstance(step, Mapping):
            chunks.append(str(step.get("log_tail") or ""))
    return "\n".join(chunks)
