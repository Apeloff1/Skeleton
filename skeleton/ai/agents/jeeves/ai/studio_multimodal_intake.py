"""Local-first, source-hashed multimodal augmentation for Jeeves Studio.

This is not an image, video or audio inference implementation. A trusted app
decoder writes an independently reviewed transcript/description as UTF-8 text.
Both the media and the sidecar are read from an approved host root, SHA-256
verified and admitted to the existing StudioEvidenceJournal before a local
Jeeves model may reason over their descriptive content.

No network, hosted model, implicit license, execution grant or weight mutation.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import stat
from typing import Any

from .studio_interaction_contract import (
    HEX, JeevesStudioController, StudioInteractionError, identifier, digest,
)

MAX_MEDIA_BYTES = 64 * 1024 * 1024
MAX_OBSERVATION_BYTES = 16 * 1024
TYPE_SUFFIXES: dict[str, frozenset[str]] = {
    "image": frozenset({".png", ".jpg", ".jpeg", ".webp"}),
    "audio": frozenset({".wav", ".flac", ".ogg", ".mp3"}),
    "video": frozenset({".mp4", ".webm"}),
    "text": frozenset({".txt", ".md", ".json"}),
    "3d": frozenset({".glb", ".gltf", ".obj"}),
    "scene": frozenset({".tscn", ".scn", ".json"}),
    "motion": frozenset({".bvh", ".anim", ".json"}),
}


def _read_pinned(root: Path, name: str, expected: str, limit: int) -> bytes:
    """Read an exact, bounded, non-symlink file inside the host-owned root."""
    if not isinstance(root, Path):
        raise StudioInteractionError("an approved pathlib root is mandatory")
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise StudioInteractionError("media root must be an absolute real directory")
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise StudioInteractionError("media path must be relative to the approved root")
    parts = Path(name).parts
    if not parts or any(part in ("..", ".", "") for part in parts):
        raise StudioInteractionError("relative media path traverses the approved root")
    if not isinstance(expected, str) or not HEX.fullmatch(expected):
        raise StudioInteractionError("independently pinned media SHA-256 required")
    base = root.resolve(strict=True)
    file = root / name
    try:
        if not file.resolve(strict=True).is_relative_to(base):
            raise StudioInteractionError("media path escapes the approved root")
        for part in parts[:-1]:
            base = base / part
            if base.is_symlink():
                raise StudioInteractionError("symlink media directories are not allowed")
        if file.is_symlink():
            raise StudioInteractionError("symlink media file is not allowed")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(file, flags)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode)
                    or not 1 <= before.st_size <= limit):
                raise StudioInteractionError("media must be a bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as source:
                data = source.read(limit + 1)
            after = os.fstat(fd)
            if (len(data) != before.st_size or len(data) > limit
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_size != after.st_size
                    or before.st_ino != after.st_ino):
                raise StudioInteractionError("media changed during admission")
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        raise StudioInteractionError("pinned media is inaccessible") from exc
    if sha256(data).hexdigest() != expected:
        raise StudioInteractionError("pinned media SHA-256 differs from actual file")
    return data


def admit_reviewed_media(
    controller: JeevesStudioController, *,
    root: Path, file_name: str, expected_sha256: str,
    source_id: str, modality: str, rights_scope: str,
    sidecar_name: str | None = None,
    sidecar_sha256: str | None = None,
    decoder_id: str | None = None,
    reviewer_id: str | None = None,
) -> dict[str, Any]:
    """Pin source bytes and optionally admit a human-reviewed decode.

    A real engine/media pipeline owns decoding. A reviewed sidecar is a
    representation of the admitted source, not proof that its statements are
    true or that Jeeves has native video/audio/vision weights.
    """
    if not isinstance(controller, JeevesStudioController):
        raise TypeError("host-owned native Jeeves studio controller required")
    identifier(source_id, "media source")
    if modality not in TYPE_SUFFIXES:
        raise StudioInteractionError("unknown multimodal production type")
    if not isinstance(file_name, str) or Path(file_name).suffix.lower() not in TYPE_SUFFIXES[modality]:
        raise StudioInteractionError("media suffix differs from declared modality")
    if rights_scope not in ("original", "licensed", "public_domain", "reference_only"):
        raise StudioInteractionError("media rights scope is not reviewed")
    data = _read_pinned(root, file_name, expected_sha256, MAX_MEDIA_BYTES)
    if modality == "image":
        if not (data.startswith(b"\x89PNG\r\n\x1a\n") or
                data.startswith(b"\xff\xd8\xff") or
                data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
            raise StudioInteractionError("image lacks recognized source signature")
    if modality == "audio" and Path(file_name).suffix.lower() == ".wav":
        if not (data.startswith(b"RIFF") and data[8:12] == b"WAVE"):
            raise StudioInteractionError("WAV lacks RIFF/WAVE source signature")
    if modality == "video" and Path(file_name).suffix.lower() == ".mp4":
        if data[4:8] != b"ftyp":
            raise StudioInteractionError("MP4 lacks file-type signature")
    if modality == "3d" and Path(file_name).suffix.lower() == ".glb":
        if not data.startswith(b"glTF"):
            raise StudioInteractionError("GLB lacks glTF binary signature")
    has_sidecar = any(x is not None for x in
                      (sidecar_name, sidecar_sha256, decoder_id, reviewer_id))
    if has_sidecar and not all(isinstance(x, str) and x for x in
                               (sidecar_name, sidecar_sha256, decoder_id, reviewer_id)):
        raise StudioInteractionError("reviewed observation requires all four sidecar fields")
    observation: str | None = None
    if has_sidecar:
        if rights_scope == "reference_only":
            raise StudioInteractionError("reference-only assets cannot become local model context")
        raw = _read_pinned(root, sidecar_name, sidecar_sha256, MAX_OBSERVATION_BYTES)
        try:
            observation = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StudioInteractionError("reviewed decoder output must be UTF-8") from exc
        if not 16 <= len(observation) <= 8192:
            raise StudioInteractionError("reviewed decoder output is outside model context limits")
        identifier(decoder_id, "decoder")
        identifier(reviewer_id, "reviewer")
    previous = controller.journal.read()
    if any(row["kind"] == "modality_registered" and
           row["payload"]["source_id"] == source_id for row in previous):
        raise StudioInteractionError("source id already admitted; avoid ambiguous source identity")
    attached = controller.attach(modality=modality, artifact_digest=expected_sha256,
                                 source_id=source_id, rights_scope=rights_scope)
    outcome = {
        "schema_version": "skeleton.jeeves.multimodal_admission.v1",
        "project_id": controller.journal.project_id,
        "session_id": controller.journal.session_id,
        "source_id": source_id,
        "modality": modality,
        "media_bytes": len(data),
        "source_sha256": expected_sha256,
        "source_receipt_sha256": attached["digest"],
        "reviewed_observation_sha256": sidecar_sha256 if has_sidecar else None,
        "observation_receipt_sha256": None,
        "locally_decoded_by_jeeves": False,
        "weight_training_performed": False,
    }
    if observation is not None:
        reviewed = controller.review_media_observation(
            source_id=source_id, observation=observation,
            observation_sha256=sidecar_sha256,
            source_sha256=expected_sha256,
            decoder_id=decoder_id, reviewer_id=reviewer_id,
        )
        outcome["observation_receipt_sha256"] = reviewed["digest"]
    outcome["receipt_sha256"] = digest(outcome)
    return outcome


__all__ = ["admit_reviewed_media", "MAX_MEDIA_BYTES", "MAX_OBSERVATION_BYTES"]
