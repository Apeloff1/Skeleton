"""Bounded, crash-recoverable multi-year original game E2E history segments.

Each 64-run sealed file holds the canonical entry digests and links to its
predecessor. The writable head remains well below the campaign receipt's
256-KiB JSON reader cap. Publishing a sealed file precedes atomically
updating the journal index: crashes can leave only an unreferenced segment
which is checked for exact byte-equivalent content before safe reuse.
No segment is deleted, overwritten, skipped or silently truncated.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import canonical_digest
from .studio_campaign import _atomic_json, _canonical, _load_json

SEGMENT_SIZE = 64
MAX_SEGMENTS = 512
SEGMENT_SCHEMA = "skeleton.game_builder.studio_qualification_history_segment.v1"


class StudioHistorySegmentError(ValueError):
    """Audited run archive differs from its canonical source-bound chain."""


def _validate_entry(entry: object, number: int, previous: str | None,
                    schema: str, identity: str) -> str:
    if (type(entry) is not dict or entry.get("schema") != schema
            or entry.get("sequence") != number
            or entry.get("previous_entry_digest") != previous
            or entry.get("campaign_identity") != identity
            or type(entry.get("run_digest")) is not str
            or type(entry.get("assurance_report_digest")) is not str
            or entry.get("full_release_qualified") is not False
            or entry.get("model_weights_updated") is not False
            or canonical_digest({k: v for k, v in entry.items()
                                 if k != "entry_digest"}) != entry.get("entry_digest")):
        raise StudioHistorySegmentError("E2E archived receipt sequence or digest was modified")
    return entry["entry_digest"]


def _directory(root: Path, *, create: bool) -> Path:
    folder = root / "qualification_history_segments"
    if folder.is_symlink():
        raise StudioHistorySegmentError("E2E archive folder must not be a symlink")
    if create:
        folder.mkdir(exist_ok=True)
    if folder.exists() and not folder.is_dir():
        raise StudioHistorySegmentError("E2E archive folder must be a real directory")
    return folder


def audit_segments(root: Path, identity: str, segments: object, *,
                   entry_schema: str) -> dict:
    """Revalidate every archived entry and SHA chain; return private totals."""
    if (type(segments) is not list or len(segments) > MAX_SEGMENTS
            or any(type(row) is not dict for row in segments)):
        raise StudioHistorySegmentError("bounded immutable E2E archive manifest required")
    prior = None
    divergence_count = 0
    unblocked_runs = 0
    for number, metadata in enumerate(segments, 1):
        file_name = f"segment-{number:05d}.json"
        if (set(metadata) != {"file", "segment_digest", "last_entry_digest"}
                or metadata["file"] != file_name):
            raise StudioHistorySegmentError("archive segment order or file name altered")
        folder = _directory(root, create=False)
        path = folder / file_name
        if path.is_symlink():
            raise StudioHistorySegmentError("archived run history must not contain symlinks")
        try:
            contents = _load_json(path)
        except (OSError, ValueError) as exc:
            raise StudioHistorySegmentError("sealed E2E history segment inaccessible") from exc
        if (contents.get("schema") != SEGMENT_SCHEMA
                or contents.get("campaign_identity") != identity
                or contents.get("first_sequence") != (number - 1) * SEGMENT_SIZE + 1
                or contents.get("previous_entry_digest") != prior
                or type(contents.get("entries")) is not list
                or len(contents["entries"]) != SEGMENT_SIZE
                or canonical_digest({k: v for k, v in contents.items()
                                     if k != "segment_digest"})
                != contents.get("segment_digest")
                or contents["segment_digest"] != metadata["segment_digest"]):
            raise StudioHistorySegmentError("sealed E2E archive content no longer matches index")
        for offset, entry in enumerate(contents["entries"]):
            prior = _validate_entry(
                entry, (number - 1) * SEGMENT_SIZE + offset + 1,
                prior, entry_schema, identity,
            )
            divergence_count += entry.get("native_cpu_divergence_count", 0)
            unblocked_runs += (
                entry.get("blocked_stage_attempts") == 0
                and entry.get("unsupported_stage_attempts") == 0
            )
        if (prior != metadata["last_entry_digest"]
                or prior != contents.get("last_entry_digest")):
            raise StudioHistorySegmentError("archive terminal chain digest changed")
    return {
        "archive_entry_count": len(segments) * SEGMENT_SIZE,
        "archive_tip": prior,
        "archive_cpu_divergence_count": divergence_count,
        "archive_unblocked_runs": unblocked_runs,
        "segments_used": len(segments),
        "segments_remaining": MAX_SEGMENTS - len(segments),
    }


def seal_full_heads(root: Path, identity: str, segments: list[dict],
                    entries: list[dict], *, entry_schema: str) -> tuple[list[dict], list[dict]]:
    """Append complete immutable 64-run segments before updating the head.

    This function must only be called while the campaign OS process lock is
    held, and after existing segments and current entries have been verified.
    """
    if type(segments) is not list or type(entries) is not list:
        raise StudioHistorySegmentError("typed journal index and entries required")
    output = list(segments)
    remaining = list(entries)
    while len(remaining) >= SEGMENT_SIZE:
        if len(output) >= MAX_SEGMENTS:
            raise StudioHistorySegmentError("multi-year E2E audit archive capacity exhausted")
        chunk = remaining[:SEGMENT_SIZE]
        prior = output[-1]["last_entry_digest"] if output else None
        first = len(output) * SEGMENT_SIZE + 1
        for offset, row in enumerate(chunk):
            prior = _validate_entry(
                row, first + offset,
                output[-1]["last_entry_digest"] if output and offset == 0
                else None if not output and offset == 0
                else chunk[offset - 1]["entry_digest"],
                entry_schema, identity,
            )
        payload = {
            "schema": SEGMENT_SCHEMA, "campaign_identity": identity,
            "first_sequence": first,
            "previous_entry_digest": (
                output[-1]["last_entry_digest"] if output else None
            ),
            "entries": chunk,
            "last_entry_digest": prior,
        }
        payload["segment_digest"] = canonical_digest(payload)
        if len(_canonical(payload)) > 256_000:
            raise StudioHistorySegmentError(
                "sealed archive exceeds the bounded on-disk JSON reader budget"
            )
        name = f"segment-{len(output) + 1:05d}.json"
        file = _directory(root, create=True) / name
        if file.exists() or file.is_symlink():
            if file.is_symlink():
                raise StudioHistorySegmentError("existing archive is a symlink")
            try:
                old = _load_json(file)
            except (OSError, ValueError) as exc:
                raise StudioHistorySegmentError("preexisting sealed archive unreadable") from exc
            if old != payload:
                raise StudioHistorySegmentError("unreferenced archive conflicts with pending seal")
        else:
            _atomic_json(file, payload)
        output.append({
            "file": name, "segment_digest": payload["segment_digest"],
            "last_entry_digest": prior,
        })
        remaining = remaining[SEGMENT_SIZE:]
    return output, remaining


__all__ = [
    "StudioHistorySegmentError", "SEGMENT_SIZE", "MAX_SEGMENTS",
    "audit_segments", "seal_full_heads",
]
