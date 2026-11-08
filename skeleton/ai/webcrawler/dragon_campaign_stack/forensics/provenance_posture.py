"""Bounded capture provenance integrity posture for selected Dragon passages.

Validates documented identity fields against the authenticated canonical run.
Unknown extraction fidelity and unavailable raw-body custody remain explicit
human-review concerns. Does not invent content rights or re-fetch sources.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from ...operations import CrawlRun
from ..contracts import CampaignMandate, digest, ensure_snapshot_scope
from .frames import FrameSet


@dataclass(frozen=True)
class ProvenanceFinding:
    source_id: str
    source_hash: str
    canonical_host: str
    captured_mime: str
    provenance_digest: str
    flags: tuple[str, ...]
    selected_passages: int
    source_identity_verified: bool
    raw_body_replay_available: bool
    extraction_completeness_certified: bool = False


@dataclass(frozen=True)
class ProvenancePosture:
    mandate_digest: str
    frame_set_digest: str
    source_snapshot_digest: str
    findings: tuple[ProvenanceFinding, ...]
    held_source_ids: tuple[str, ...]
    identity_violations_rejected: bool
    replayable_raw_body_count: int
    truncated_selected_source_count: int
    posture_digest: str
    content_rights_certified: bool = False
    source_text_exported: bool = False


def audit_capture_provenance(
    mandate: CampaignMandate, snapshot: dict[str, object],
    frames: FrameSet, *, now: float, authorized: bool,
) -> ProvenancePosture:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(frames, FrameSet):
        raise TypeError("current source frames required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if frames.mandate_digest != mandate.fingerprint or (
        frames.snapshot_digest != canonical["snapshot_digest"]
    ):
        raise PermissionError("provenance inspection on stale or foreign snapshot")
    grouped: dict[str, list] = {}
    for frame in frames.frames:
        grouped.setdefault(frame.anchor.source_id, []).append(frame.anchor)
    if len(grouped) > 32:
        raise ValueError("provenance selected source cap exceeded")
    findings = []
    held = set()
    for source_id, anchors in sorted(grouped.items()):
        source = canonical["sources"].get(source_id)
        if not isinstance(source, dict):
            raise PermissionError("selected source missing in captured run")
        host = urlsplit(source["canonical_url"]).hostname
        if host is None or host not in mandate.scope.allowed_hosts:
            raise PermissionError("source host is outside mandate")
        if any(a.source_hash != source["content_hash"] or a.host != host
               for a in anchors):
            raise PermissionError("provenance does not match selected source identity")
        capture = source.get("provenance")
        if not isinstance(capture, dict):
            raise PermissionError("canonical captured provenance missing")
        if (capture.get("canonical_url") != source["canonical_url"]
                or capture.get("content_hash") != source["content_hash"]
                or capture.get("consent_id") != mandate.scope.consent_id
                or capture.get("binding_digest") != digest(canonical["binding"])):
            raise PermissionError("capture provenance is not bound to canonical authority")
        if capture.get("training_permission") is not False or (
            capture.get("source_status") != "unreviewed_external_capture"
        ):
            raise PermissionError("capture provenance claims unrecognized training or source authority")
        flags = set()
        text = source.get("text")
        if not isinstance(text, str) or (
            sha256(text.encode("utf-8")).hexdigest() != source["content_hash"]
        ):
            raise PermissionError("retained text changed after capture")
        if source.get("text_truncated") is True:
            flags.add("partial_retained_text")
        if source.get("preserved_text_hash") != source["content_hash"]:
            flags.add("preserved_text_hash_requires_review")
        raw_hash = source.get("raw_body_hash")
        if not isinstance(raw_hash, str) or len(raw_hash) != 64:
            flags.add("raw_body_identity_unavailable")
        elif capture.get("raw_body_hash") != raw_hash:
            raise PermissionError("captured body identity disagrees with provenance")
        if capture.get("raw_bytes_retained") is not True:
            flags.add("raw_body_not_retained")
        if capture.get("fetched_url") != source.get("fetched_url"):
            raise PermissionError("fetched origin differs from recorded provenance")
        if source["canonical_url"] != source.get("fetched_url"):
            flags.add("source_redirect_path_requires_review")
        if source.get("content_type") not in ("text/html", "text/plain", "application/xhtml+xml"):
            flags.add("unexpected_selected_content_type")
        if source.get("review_state") not in ("unreviewed",):
            flags.add("review_state_requires_current_authority")
        if flags:
            held.add(source_id)
        findings.append(ProvenanceFinding(
            source_id, source["content_hash"], host, str(source.get("content_type", "")),
            digest(capture), tuple(sorted(flags)), len(anchors),
            True, capture.get("raw_bytes_retained") is True,
        ))
    payload = {
        "mandate": mandate.fingerprint, "frames": frames.frame_set_digest,
        "snapshot": canonical["snapshot_digest"],
        "findings": [asdict(x) for x in findings],
    }
    return ProvenancePosture(
        mandate.fingerprint, frames.frame_set_digest,
        canonical["snapshot_digest"], tuple(findings),
        tuple(sorted(held)), True,
        sum(f.raw_body_replay_available for f in findings),
        sum("partial_retained_text" in f.flags for f in findings),
        digest(payload),
    )
