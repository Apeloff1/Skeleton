"""Framework-free product adapters for Academy actions.

The HTTP Academy router remains the public compatibility surface. These helpers
give the governed product control plane the same durable data without importing
FastAPI route modules.
"""
from __future__ import annotations

from typing import Any


def _text(value: Any, *, field: str, default: str = "", max_length: int = 256) -> str:
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return normalized


def _limit(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("limit must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return parsed


def _public_exercise(row: dict[str, Any]) -> dict[str, Any]:
    """Remove answer material from a practice payload."""

    hidden = {
        "answer",
        "answers",
        "solution",
        "solutions",
        "expected_output",
        "reference_answer",
        "correct_answer",
    }
    return {key: value for key, value in row.items() if key not in hidden and key != "_id"}


async def continue_learning(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the most useful resumable Academy progress item for a user."""

    from core.databases import core_db

    user_id = _text(payload.get("user_id"), field="user_id", default="default_user")
    item_type = _text(payload.get("item_type"), field="item_type")
    query: dict[str, Any] = {"user_id": user_id}
    if item_type:
        query["item_type"] = item_type

    items = await core_db.user_progress.find(query, {"_id": 0}).sort(
        "updated_at", -1
    ).to_list(1000)
    active = next((item for item in items if item.get("status") != "completed"), None)
    latest = items[0] if items else None
    resume = active or latest

    return {
        "user_id": user_id,
        "item_type": item_type or None,
        "resume": resume,
        "total": len(items),
        "completed": sum(1 for item in items if item.get("status") == "completed"),
        "state": "resume_available" if resume else "new_learner",
    }


async def practice(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded, answer-free practice set from the canonical exercise store."""

    from core.databases import core_db

    track_id = _text(payload.get("track_id"), field="track_id")
    module_id = _text(payload.get("module_id"), field="module_id")
    limit = _limit(payload.get("limit"), default=10, maximum=50)

    query: dict[str, Any] = {}
    if track_id:
        query["track_id"] = track_id
    if module_id:
        query["module_id"] = module_id

    total = await core_db.exercises.count_documents(query)
    rows = await core_db.exercises.find(query, {"_id": 0}).sort("id", 1).limit(
        limit
    ).to_list(limit)

    return {
        "track_id": track_id or None,
        "module_id": module_id or None,
        "total_available": total,
        "count": len(rows),
        "exercises": [_public_exercise(dict(row)) for row in rows],
    }


async def progress(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate Academy item progress and quiz performance for one user."""

    from core.databases import core_db

    user_id = _text(payload.get("user_id"), field="user_id", default="default_user")
    item_type = _text(payload.get("item_type"), field="item_type")
    query: dict[str, Any] = {"user_id": user_id}
    if item_type:
        query["item_type"] = item_type

    items = await core_db.user_progress.find(query, {"_id": 0}).sort(
        "updated_at", -1
    ).to_list(1000)
    scores = await core_db.quiz_scores.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("played_at", -1).to_list(100)

    total_questions = sum(int(row.get("total_questions", 0) or 0) for row in scores)
    total_correct = sum(int(row.get("correct", 0) or 0) for row in scores)
    total_score = sum(int(row.get("score", 0) or 0) for row in scores)

    return {
        "user_id": user_id,
        "item_type": item_type or None,
        "items": items,
        "total": len(items),
        "completed": sum(1 for item in items if item.get("status") == "completed"),
        "quiz": {
            "sessions": len(scores),
            "total_score": total_score,
            "total_correct": total_correct,
            "total_questions": total_questions,
            "accuracy_pct": round(total_correct / max(total_questions, 1) * 100, 1),
            "recent": scores[:20],
        },
    }
