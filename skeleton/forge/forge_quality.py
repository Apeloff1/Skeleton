"""
Forge quality polish loop — bounded multi-signal artefact improvement.

Composes quality scoring with an optional file-repair callable across
bounded rounds. Used by forge.repair.polish_artefact; deliberately
separate from the VerificationLoop so GDD-stage floors and region
signals can shape acceptance without rewriting the verify core.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from skeleton.organism.quality_state import append_quality

PRODUCTION_THRESHOLD = 0.72
STAGING_THRESHOLD = 0.55


def _score_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Heuristic artefact scoring: completeness of expected fields."""
    expected = ("title", "summary", "content", "files")
    present = sum(1 for k in expected if item.get(k))
    completeness = present / len(expected)
    files = item.get("files") or {}
    file_bonus = min(len(files) / 10.0, 1.0) if isinstance(files, dict) else 0.0
    score = round(0.7 * completeness + 0.3 * file_bonus, 4)
    return {"score": score, "completeness": completeness, "file_count": len(files) if isinstance(files, dict) else 0}


def polish_loop(
    item: Mapping[str, Any],
    *,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages: tuple = (),
    regions: tuple = (),
    era: Optional[str] = None,
    max_rounds: int = 3,
    persist: bool = True,
    artefact_id: str = "",
    root=None,
    repair_files: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Bounded polish: score → optional file repair → re-score, until floor met."""
    current = dict(item)
    floor = max(0.5, 0.5 + 0.1 * stage_floor_grade)
    history: List[Dict[str, Any]] = []
    rounds = 0

    for rounds in range(1, max(1, int(max_rounds)) + 1):
        report = _score_item(current)
        history.append({"round": rounds, **report})
        if report["score"] >= floor:
            break
        if repair_files is not None and isinstance(current.get("files"), dict) and current["files"]:
            repaired = repair_files(current["files"], request=str(current.get("title") or ""), root=root)
            if repaired.get("changed"):
                current["files"] = dict(repaired.get("files") or current["files"])
            else:
                break  # no further gains available
        else:
            break

    final = _score_item(current)
    accepted = final["score"] >= floor
    result = {
        "kind": "forge-polish",
        "artefact_id": artefact_id,
        "accepted": accepted,
        "score": final["score"],
        "floor": floor,
        "rounds": rounds,
        "history": history,
        "stage_index": stage_index,
        "era": era,
        "regions": len(regions),
        "item": current,
    }
    if persist:
        append_quality({
            "kind": "quality",
            "surface": "forge_polish",
            "accepted": accepted,
            "reason": "floor_met" if accepted else "floor_missed",
            "score": final["score"],
            "summary": {"rounds": rounds, "files": final["file_count"]},
            "metadata": {"artefact_id": artefact_id, "stage_index": stage_index},
            "evidence": {"history": history},
        }, root=root)
    return result


def evaluate(item: Mapping[str, Any] | None = None, **_: Any) -> Dict[str, Any]:
    scored = _score_item(item or {})
    return {
        "kind": "forge-quality",
        "score": scored["score"],
        "ok": int(scored["score"] >= PRODUCTION_THRESHOLD),
        "stored_prose": 0,
    }


def summarize(rows: List[Mapping[str, Any]] | None = None, **_: Any) -> Dict[str, Any]:
    rows = list(rows or [])
    return {
        "kind": "forge-quality-sum",
        "n": len(rows),
        "stored_prose": 0,
    }


def persist_quality(row: Mapping[str, Any] | None = None, *, root=None, **_: Any) -> Dict[str, Any]:
    payload = dict(row or {})
    payload.setdefault("kind", "forge-quality")
    payload["stored_prose"] = 0
    try:
        append_quality(payload, root=root)
    except Exception:
        pass
    return payload
