"""Portable offline scene saves through the canonical scene replay engine."""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.offline_portable import (
    PortableGameError, export_verified, import_verified,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, verify_session

KIND = "skeleton.scene_travel.v1"


def export_scene_bundle(session: Any) -> dict[str, Any]:
    try:
        return export_verified(session, kind=KIND, verifier=verify_session)
    except PortableGameError as exc:
        raise SceneTravelError(str(exc)) from exc


def import_scene_bundle(bundle: Any) -> dict[str, Any]:
    try:
        return import_verified(bundle, kind=KIND, verifier=verify_session)
    except PortableGameError as exc:
        raise SceneTravelError(str(exc)) from exc
