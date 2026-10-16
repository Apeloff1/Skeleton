"""Consent-bound Dragon gameplay studies -> original Jeeves design handoffs.

This is an operator-attested intake for reviewed observations, not a ROM/video
extractor, copyright clearance, production certification, or weights trainer.
The canonical Dragon review/memory/forge contracts own all interpretation.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

SCHEMA = "skeleton.dragon.jeeves_study.v1"
HANDOFF_SCHEMA = "skeleton.dragon.jeeves_handoff.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_STUDY_BYTES = 512 * 1024


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _checked_dir(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("unsafe Dragon workbench directory")


def _database(root: Path, *, create: bool) -> sqlite3.Connection:
    base = root / ".jeeves"
    _checked_dir(base)
    if create:
        base.mkdir(exist_ok=True)
    path = base / "dragon_game_observations.sqlite3"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("unsafe Dragon observation database")
    if not create and not path.is_file():
        raise ValueError("no Dragon observations ingested for this project")
    if create:
        return sqlite3.connect(path)
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _packet(root: Path, source: str) -> tuple[dict[str, Any], str]:
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.game_cli import _load
    doc, source_sha = _read(root, source, MAX_STUDY_BYTES)
    fields = {"schema", "project", "owner", "game_label", "duration_ms",
              "capture_consent", "analysis_consent", "rights_attested",
              "observations"}
    if set(doc) != fields or doc["schema"] != SCHEMA:
        raise ValueError("invalid reviewed Dragon observation packet")
    if doc["project"] != _load(root)["name"]:
        raise ValueError("Dragon study belongs to a different game project")
    for name, limit in (("owner", 128), ("game_label", 200)):
        value = doc[name]
        if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.isprintable():
            raise ValueError("invalid Dragon " + name)
    if any(doc[key] is not True for key in (
        "capture_consent", "analysis_consent", "rights_attested"
    )):
        raise PermissionError("explicit consent and observation-rights attestation required")
    if type(doc["duration_ms"]) is not int or not 1 <= doc["duration_ms"] <= 1800000:
        raise ValueError("Dragon capture duration outside reviewed budget")
    if not isinstance(doc["observations"], list) or not 1 <= len(doc["observations"]) <= 2000:
        raise ValueError("Dragon reviewed observation count outside budget")
    return doc, source_sha


def _observations(doc: dict[str, Any]) -> tuple[Any, ...]:
    from skeleton.ai.webcrawler.dragon_game_builder_bridge import VisualEvent, ReviewedObservation
    from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic, PreferenceSignal
    rows = []
    for obj in doc["observations"]:
        keys = {"timestamp_ms", "source_frame_ms", "label", "confidence", "description",
                "mechanic", "preference", "user_confirmed", "reviewer_note"}
        if not isinstance(obj, dict) or set(obj) != keys:
            raise ValueError("Dragon reviewed event fields differ")
        for key in ("timestamp_ms", "source_frame_ms"):
            if type(obj[key]) is not int:
                raise ValueError("Dragon event timestamps must be integers")
        if type(obj["confidence"]) not in (int, float):
            raise ValueError("Dragon confidence must be a finite number")
        if type(obj["user_confirmed"]) is not bool:
            raise ValueError("Dragon user confirmation must be boolean")
        event = VisualEvent(obj["timestamp_ms"], obj["label"], obj["confidence"],
                            obj["description"], obj["source_frame_ms"])
        rows.append(ReviewedObservation(
            event, Mechanic(obj["mechanic"]), PreferenceSignal(obj["preference"]),
            obj["user_confirmed"], obj["reviewer_note"]))
    return tuple(rows)


def ingest(root: Path, *, source: str, approved_sha256: str | None) -> dict[str, Any]:
    """Validate before opening the database; ingest is idempotent and consent-gated."""
    doc, identity = _packet(root, source)
    if not isinstance(approved_sha256, str) or approved_sha256 != identity:
        raise PermissionError("dragon-ingest needs --approve matching source SHA-256")
    observations = _observations(doc)
    from skeleton.ai.webcrawler.dragon_game_builder_bridge import review_recording
    from skeleton.ai.webcrawler.dragon_game_mechanics import GameMechanicsMemory
    # Source may change between validation and write; reject before persisting.
    if _packet(root, source)[1] != identity:
        raise ValueError("Dragon source changed during ingestion")
    try:
        with _database(root, create=True) as db:
            memory = GameMechanicsMemory(db)
            session = review_recording(
                memory, owner=doc["owner"], game_label=doc["game_label"],
                duration_ms=doc["duration_ms"], observations=observations,
                capture_consent=True, analysis_consent=True, authorized=True)
            profile = memory.distill(doc["owner"], authorized=True)
    except sqlite3.DatabaseError as exc:
        raise ValueError("Dragon observation database unavailable") from exc
    return {"ok": True, "action": "dragon-ingest", "project": doc["project"],
            "session_sha256": session.session_id, "source_sha256": identity,
            "reviewed_events": len(observations), "taste_sha256": profile.fingerprint,
            "raw_video_retained": False, "rights_independently_verified": False,
            "trained_model_weights": False}


def _preview(root: Path, *, source: str, genre: str, target: str) -> dict[str, Any]:
    from skeleton.developer.game_cli import _load
    from skeleton.developer.jeeves_game_authoring import _config_identity
    from skeleton.ai.webcrawler.dragon_game_mechanics import GameMechanicsMemory
    from skeleton.ai.webcrawler.dragon_game_forge import DragonGameForge, GameDesignConstraint
    from skeleton.ai.webcrawler.dragon_game_builder_bridge import prepare_game_builder_handoff
    doc, source_sha = _packet(root, source)
    if not isinstance(genre, str) or not isinstance(target, str):
        raise ValueError("Dragon game forge needs --genre and --target")
    try:
        with _database(root, create=False) as db:
            memory = GameMechanicsMemory(db)
            constraints = GameDesignConstraint(
                genre=genre, target_platform=target,
                originality_notes=("Create new assets and original fictional content",))
            handoff = prepare_game_builder_handoff(
                memory, DragonGameForge(), owner=doc["owner"],
                constraints=constraints, authorized=True, human_approved=True)
            session_ids = {s.session_id for s in memory.sessions(doc["owner"], authorized=True)}
    except sqlite3.DatabaseError as exc:
        raise ValueError("Dragon observation database unavailable") from exc
    if not session_ids:
        raise ValueError("no Dragon sessions for the requested project owner")
    # Handoff belongs to the current project configuration and source evidence.
    data = {
        "schema": HANDOFF_SCHEMA, "project": doc["project"],
        "config_sha256": _config_identity(_load(root)),
        "source": source, "source_sha256": source_sha,
        "owner": doc["owner"], "supporting_session_ids": sorted(session_ids),
        "taste_sha256": handoff.taste_fingerprint,
        "review_sha256": handoff.review_fingerprint,
        "manifest_sha256": handoff.manifest_fingerprint,
        "genre": genre, "target": target,
        "prototype": asdict(handoff.prototype),
        "evaluation": asdict(handoff.evaluation),
        "original_assets_required": True,
        "independent_rights_review": False,
        "actual_model_training": False,
        "game_implementation_verified": False,
    }
    # Enums derive from str; normalize to JSON to match handoff verification.
    data = json.loads(json.dumps(data, allow_nan=False))
    return data


def plan(root: Path, *, source: str, genre: str, target: str) -> dict[str, Any]:
    packet = _preview(root, source=source, genre=genre, target=target)
    digest = _hash(packet)
    return {"ok": True, "action": "dragon-plan",
            "handoff_sha256": digest, "handoff": packet,
            "approved_for_model_context": False,
            "next": "dragon-adopt --source ... --genre ... --target ... --approve " + digest}


def _handoff_path(root: Path, digest: str) -> Path:
    if not isinstance(digest, str) or HEX.fullmatch(digest) is None:
        raise ValueError("invalid Dragon handoff identity")
    top = root / ".jeeves"
    folder = top / "dragon_handoffs"
    _checked_dir(top)
    _checked_dir(folder)
    return folder / (digest + ".json")


def adopt(root: Path, *, source: str, genre: str, target: str,
          approved_sha256: str | None) -> dict[str, Any]:
    packet = _preview(root, source=source, genre=genre, target=target)
    digest = _hash(packet)
    if approved_sha256 != digest:
        raise PermissionError("dragon-adopt needs --approve matching the complete handoff digest")
    from skeleton.developer.jeeves_game_authoring import _create_only
    target_file = _handoff_path(root, digest)
    _create_only(target_file, json.dumps(packet, sort_keys=True, indent=2,
                                         ensure_ascii=True).encode("utf-8") + b"\n")
    return {"ok": True, "action": "dragon-adopt", "handoff_sha256": digest,
            "path": str(target_file), "scope": "local-reviewed-original-design-context",
            "production_qualified": False, "model_training_performed": False}


def load_handoff(root: Path, digest: str) -> dict[str, Any]:
    """Fail-closed, exact-current-evidence lookup used by Jeeves model proposals."""
    location = _handoff_path(root, digest)
    if location.is_symlink() or not location.is_file() or location.stat().st_size > 64 * 1024:
        raise ValueError("Dragon approved handoff missing, unsafe or oversized")
    try:
        doc = json.loads(location.read_text("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid Dragon approved handoff") from exc
    if not isinstance(doc, dict) or _hash(doc) != digest:
        raise ValueError("Dragon approved handoff tampered")
    if doc != _preview(root, source=doc.get("source"),
                       genre=doc.get("genre"), target=doc.get("target")):
        raise ValueError("Dragon approved handoff stale relative to observed evidence")
    return doc
