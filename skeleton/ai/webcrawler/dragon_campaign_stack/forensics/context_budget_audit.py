"""Measure the bounded untrusted text footprint selected for forensic analysis.

All quantities are measured from current exact captured spans. A count of
characters or bytes does not grant any model-context safety, right, privacy
permission or authorization to execute instructions from source pages.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import CampaignMandate, digest, integer
from .frames import FrameSet


@dataclass(frozen=True)
class ContextSourceBudget:
    source_id: str
    host: str
    selected_passages: int
    selected_characters: int
    selected_utf8_bytes: int
    objective_count: int
    relative_character_share: float
    model_context_safety_certified: bool = False


@dataclass(frozen=True)
class ContextBudgetAudit:
    mandate_digest: str
    frame_set_digest: str
    total_selected_passages: int
    total_selected_chars: int
    total_selected_utf8_bytes: int
    source_budgets: tuple[ContextSourceBudget, ...]
    hottest_source_id: str | None
    over_campaign_evidence_char_limit: bool
    over_explicit_context_byte_limit: bool
    source_concentration_review: bool
    audit_digest: str
    model_invoked: bool = False
    publication_authorized: bool = False
    untrusted_text_exported: bool = False


def audit_context_budget(
    mandate: CampaignMandate, frames: FrameSet,
    *, max_total_context_bytes: int = 32_000,
) -> ContextBudgetAudit:
    if not isinstance(mandate, CampaignMandate) or not isinstance(frames, FrameSet):
        raise TypeError("campaign mandate and protected source frames required")
    integer(max_total_context_bytes, "context byte audit threshold", 128, 131_072)
    if frames.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign mandate on context budget")
    grouped = defaultdict(list)
    total_bytes = 0
    total_chars = 0
    for frame in frames.frames:
        grouped[frame.anchor.source_id].append(frame)
        total_bytes += len(frame.text.encode("utf-8"))
        total_chars += len(frame.text)
    if len(grouped) > 32 or len(frames.frames) > 64 or total_chars > 48_000:
        raise ValueError("unbounded context audit source universe")
    budgets = []
    for source_id, rows in sorted(grouped.items()):
        anchors = [r.anchor for r in rows]
        chars = sum(len(r.text) for r in rows)
        bytes_used = sum(len(r.text.encode("utf-8")) for r in rows)
        if len({a.host for a in anchors}) != 1:
            raise PermissionError("selected source host changed in context audit")
        budgets.append(ContextSourceBudget(
            source_id, anchors[0].host, len(rows), chars, bytes_used,
            len({oid for a in anchors for oid in a.objective_ids}),
            round(chars / total_chars, 6) if total_chars else 0.,
        ))
    busiest = sorted(budgets, key=lambda x: (-x.selected_characters, x.source_id))
    over_char = total_chars > mandate.limits.max_evidence_chars
    over_bytes = total_bytes > max_total_context_bytes
    concentrated = bool(busiest and busiest[0].relative_character_share >= .8)
    payload = {
        "mandate": mandate.fingerprint, "frames": frames.frame_set_digest,
        "limit": max_total_context_bytes, "char_limit": mandate.limits.max_evidence_chars,
        "sources": [asdict(row) for row in budgets],
        "total_chars": total_chars, "total_bytes": total_bytes,
    }
    return ContextBudgetAudit(
        mandate.fingerprint, frames.frame_set_digest,
        len(frames.frames), total_chars, total_bytes, tuple(budgets),
        busiest[0].source_id if busiest else None,
        over_char, over_bytes, concentrated, digest(payload),
    )
