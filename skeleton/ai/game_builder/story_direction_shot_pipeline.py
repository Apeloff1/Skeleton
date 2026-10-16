"""Evidence-bound movie/interactive shot direction across signed game scenes.

Uses the *canonical* character/face/voice/camera/timing/axis verifier.
Produces editor-usable measurements, never claimed rendered film or actor QA.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from statistics import median
from typing import Any

from skeleton.ai.game_builder.story_canon_fabric import verify_story_history
from skeleton.ai.game_builder.story_chapter_context import validate_chapter_history
from skeleton.ai.game_builder.story_continuity_assurance import validate_contract
from skeleton.ai.game_builder.story_cinematic_review import verify_cinematic_shots

SCHEMA = "skeleton.jeeves.cinematic_direction_audit.v1"
MOVEMENT = frozenset(("pan_to", "tilt", "dolly", "crane", "orbit",
                       "tracking", "handheld", "rack_focus"))
MAX_SCENES = 9999


class ShotDirectionError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def audit_cinematic_direction(
    bible: dict[str, Any], contract: dict[str, Any],
    scenes: list[dict[str, Any]], boards: Any, *, passes: int = 1,
) -> dict[str, Any]:
    if type(passes) is not int or not 1 <= passes <= 8:
        raise ShotDirectionError("cinematic review uses 1..8 bounded scrutiny passes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise ShotDirectionError("cinematic direction needs signed original source scenes")
    if not isinstance(boards, list) or len(boards) != len(scenes):
        raise ShotDirectionError("every authored cinematic scene needs one shot board")
    validate_contract(contract, bible)
    validation = verify_story_history(bible, scenes)
    if any("chapter" not in scene for scene in scenes):
        raise ShotDirectionError("cinematic production requires original chapter-scoped scenes")
    validate_chapter_history(scenes)
    by_scene: dict[int, list[dict[str, Any]]] = {}
    for row in boards:
        if not isinstance(row, dict) or set(row) != {"scene_sequence", "shots"}:
            raise ShotDirectionError("unrecognized cinematic shot-board entry")
        sequence = row["scene_sequence"]
        if type(sequence) is not int or sequence < 1 or sequence > len(scenes):
            raise ShotDirectionError("shot-board sequence is not an existing original scene")
        if sequence in by_scene:
            raise ShotDirectionError("duplicated cinematic scene board")
        by_scene[sequence] = row["shots"]
    if len(by_scene) != len(scenes):
        raise ShotDirectionError("missing chronological scene shot-board coverage")
    passes_seen = []
    latest = []
    whole_count = whole_duration = whole_dialogue = movement_count = 0
    for attempt in range(1, passes + 1):
        receipts = []
        for scene in scenes:
            shots = by_scene[scene["sequence"]]
            # Authoritative camera/actor/voice/style/dialogue/time verifier.
            receipt = verify_cinematic_shots(bible, contract, scene, shots)
            receipts.append(receipt["digest"])
            if attempt != 1:
                continue
            durations = [shot["duration_ms"] for shot in shots]
            cameras = Counter(shot["camera"] for shot in shots)
            edits = Counter(shot["cut"] for shot in shots)
            actors = Counter()
            for shot in shots:
                actors[shot["focus_character"]] += shot["duration_ms"]
            moving = sum(shot["camera"] in MOVEMENT for shot in shots)
            long_static = sum(
                shot["camera"] in ("fixed", "medium") and shot["duration_ms"] > 10000
                for shot in shots
            )
            items = []
            if len(shots) >= 4 and len(cameras) == 1:
                items.append("Review unvaried shot grammar; repetition may be intentional")
            if len(shots) >= 3 and sum(edits.values()) > 2*len(scene["dialogue"])+6:
                items.append("Evaluate editing frequency against actor intent and silence")
            if not moving and len(shots) >= 3:
                items.append("Evaluate camera movement only where dramatic motivation supports it")
            if long_static:
                items.append("Check sustained static takes for blocking and purposeful dramatic tension")
            latest.append({
                "scene_sequence": scene["sequence"],
                "signed_scene_sha256": scene["digest"],
                "pre_render_receipt_digest": receipt["digest"],
                "shot_count": receipt["shot_count"],
                "duration_ms": receipt["duration_ms"],
                "spoken_lines_source_covered": receipt["spoken_lines_verified"],
                "median_shot_duration_ms": median(durations),
                "shortest_shot_ms": min(durations),
                "longest_shot_ms": max(durations),
                "cameras": dict(sorted(cameras.items())),
                "cuts": dict(sorted(edits.items())),
                "moving_camera_shots": moving,
                "original_actor_screen_time_ms": dict(sorted(actors.items())),
                "recommended_editor_review": items,
                "actor_performance_video_evaluated": False,
                "original_music_audio_playback_evaluated": False,
                "visual_emotional_impact_verified": False,
            })
            whole_count += len(shots)
            whole_duration += receipt["duration_ms"]
            whole_dialogue += receipt["spoken_lines_verified"]
            movement_count += moving
        passes_seen.append({
            "pass": attempt, "verified_scenes": len(receipts),
            "shot_receipt_digest": _digest(receipts),
            "canonical_owning_film_verifier_used": True,
            "independent_human_screening": False,
        })
    return {
        "ok": True, "action": "direction-shots", "schema": SCHEMA,
        "source_identity_sha256": _digest({
            "bible": bible["digest"], "contract": contract["digest"],
            "story_history": validation["digest"], "boards": boards,
        }),
        "scrutiny_passes": passes,
        "repeatable_pre_render_receipts": passes_seen,
        "original_canon_scenes": len(scenes),
        "total_shots": whole_count,
        "total_timeline_ms": whole_duration,
        "source_spoken_lines_covered": whole_dialogue,
        "moving_camera_shots": movement_count,
        "per_scene": latest,
        "every_scene_exact_dialogue_source_covered": True,
        "actor_face_voice_and_grade_source_locked": True,
        "actual_rendered_video_screened": False,
        "actual_voice_and_lip_sync_verified": False,
        "book_or_hollywood_professional_quality_proven": False,
        "completed_game_playthrough_verified": False,
        "editorial_quality_floor_relaxed": False,
    }
