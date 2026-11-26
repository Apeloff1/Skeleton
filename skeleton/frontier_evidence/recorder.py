"""Software session for the native recorder.

The session tracks save-slot identity and a signed scene id, and exposes
start, stop, resume, plus a manifest a UI can call. It refuses to start
unless both ids are present. Installer activation and hardware capture stay
outside this session.
"""

from __future__ import annotations

import re

from skeleton.frontier_evidence.common import EvidenceRejected, seal

SCHEMA = "skeleton.frontier_evidence.recorder_manifest.v1"
_SLOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class RecorderSessionError(EvidenceRejected):
    """Recorder software session refused the request."""


class RecorderSession:
    """In-memory software session. Not an installer and not a device binding."""

    def __init__(self, save_slot_id: str, signed_scene_id: str) -> None:
        self.save_slot_id = save_slot_id
        self.signed_scene_id = signed_scene_id
        self.state = "recording"
        self._events = ["start"]

    def stop(self) -> dict:
        if self.state != "recording":
            raise RecorderSessionError("stop requires an active recording")
        self.state = "stopped"
        self._events.append("stop")
        return self.manifest()

    def resume(self) -> dict:
        if self.state != "stopped":
            raise RecorderSessionError("resume requires a stopped session")
        self.state = "recording"
        self._events.append("resume")
        return self.manifest()

    def manifest(self) -> dict:
        """UI-callable snapshot of the software session."""
        return seal(
            {
                "schema": SCHEMA,
                "save_slot_id": self.save_slot_id,
                "signed_scene_id": self.signed_scene_id,
                "state": self.state,
                "events": list(self._events),
                "software_session": "ready",
                "installer_and_hardware_activation": "open",
                "authority": "software_recorder_session_not_device_or_installer",
            }
        )


def start(
    *,
    save_slot_id: str | None = None,
    signed_scene_id: str | None = None,
) -> RecorderSession:
    """Start a software recorder session. Both ids are mandatory."""
    if not isinstance(save_slot_id, str) or _SLOT.fullmatch(save_slot_id) is None:
        raise RecorderSessionError("save slot id required")
    if not isinstance(signed_scene_id, str) or _SHA256_HEX.fullmatch(signed_scene_id) is None:
        raise RecorderSessionError("signed scene id must be a 64-character lowercase SHA-256 hex digest")
    return RecorderSession(save_slot_id, signed_scene_id)
