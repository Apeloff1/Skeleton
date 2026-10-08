"""Fail-closed pull-request workload court for Apeloff1/Skeleton.

This module does not merge, does not call GitHub, and does not store prose
in the mesh. It classifies an already-fetched open set into lanes and
refuses volume-scatter heads that would otherwise look like capability growth.

Parent cite: issue #80. stored_prose=0.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping, Sequence

PACKET = "PR-COURT-20261008"
PARENT = "#80"
STORED_PROSE = 0
SCHEMA = "skeleton.review.pr-workload-court.v1"

# Observed open window, 2026-10-08 23:01 Europe/Oslo. Heads are pins, not authority.
OBSERVED_WINDOW: tuple[dict[str, object], ...] = (
    {"number": 3537, "title": "fix(ai): bounded serving preflight and deterministic feedback replay fence", "draft": False, "lane_hint": "serve", "additions": 626, "deletions": 21, "changed_files": 6, "head": "40b05d143605b2790bd42253e3d599b4e581ee84", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3535, "title": "fix(ai): validate tokenizer checkpoints and release streaming buffers", "draft": False, "lane_hint": "token", "additions": 170, "deletions": 14, "changed_files": 2, "head": "40fa7800b2440616df3156e4628cb39edc121397", "base": "962bce33d61da43667f6590a9d3c903004446161"},
    {"number": 3548, "title": "feat(app): 50 connected milestones — creation journeys, World Workbench and Design Review", "draft": False, "lane_hint": "app", "additions": 0, "deletions": 0, "changed_files": 0, "head": "0b0b9cccdd2aad0b9cf08ded4a2232fe8da29bc2", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3558, "title": "feat(dragon): 19-era native game forge, 10 PC kernels, ROM/evidence pipeline and real executable release", "draft": False, "lane_hint": "dragon", "additions": 0, "deletions": 0, "changed_files": 0, "head": "223e4ca761f917fcd08ede8fbb13792886416c27", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3560, "title": "feat: scatter 10240 organs across 16 masterplan facets (FACET-10240)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "2f8796ae9946e122f54d729dc62f66046a9b5c5d", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3559, "title": "feat: scatter 10240 organs across 16 thin volumes (SCAT-10240)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "150964344a0996f7ba8e9906bb0fda655a9886fb", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3556, "title": "feat(audio): 5120 era organs for game-audio completion (ERA-5120)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "5e94bc0f23fe2be68d0f84cdbea336af542510bf", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3555, "title": "feat(cue): GB-46 batch of 2560 fail-closed organs (CUE-2560)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "8ca7653584edaf68ebb57ac6190b22c0f7aec991", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3554, "title": "feat(audio): VOL-156 batch of 1280 fail-closed organs (AUD-1280)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "dd880e1dc5e69f7593fb6e0f28583d3aa8f1bc5c", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3553, "title": "feat(document_vision): VOL-155 batch of 640 fail-closed organs (DV-640)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "2fdc24b55c6d001575c6997fd68378a061c9ad67", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3552, "title": "feat(video): VOL-158 batch of 320 fail-closed organs (VID-320)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "2600aa8947508232cef5961db593bfac1e82b1d0", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
    {"number": 3551, "title": "feat(supply_chain): VOL-178 batch of 160 fail-closed organs (SC-160)", "draft": True, "lane_hint": "scatter", "additions": 0, "deletions": 0, "changed_files": 0, "head": "ca6b7c6f923ec51881722c558ca3a129b976c57e", "base": "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"},
)

VOLUME_RE = re.compile(
    r"(scatter|facet-\d+|scat-\d+|era-\d+|batch of \d+|organs across|\b\d{3,5}\b organs)",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
READY_LANES = frozenset({"serve", "token"})
HOLD_LANES = frozenset({"scatter", "volume"})
REVIEW_LANES = frozenset({"app", "dragon", "draft", "unknown"})
MAIN_PIN = "d8bbad98c04b96f4056b3d09a2a47ca859f2cb27"


class CourtError(ValueError):
    """Fail-closed court rejection. Never coerced into a pass card."""


@dataclass(frozen=True, slots=True)
class Workload:
    number: int
    title: str
    draft: bool
    additions: int
    deletions: int
    changed_files: int
    head: str
    base: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "Workload":
        required = {"number", "title", "draft", "additions", "deletions", "changed_files", "head", "base"}
        if set(raw) < required:
            raise CourtError("workload missing required fields")
        number = raw["number"]
        title = raw["title"]
        draft = raw["draft"]
        if type(number) is not int or number <= 0:
            raise CourtError("pull number must be a positive int")
        if type(title) is not str or not title.strip() or len(title) > 240:
            raise CourtError("title must be a bounded nonempty string")
        if type(draft) is not bool:
            raise CourtError("draft must be bool")
        counts = {}
        for key in ("additions", "deletions", "changed_files"):
            value = raw[key]
            if type(value) is not int or value < 0:
                raise CourtError(f"{key} must be a non-negative int")
            counts[key] = value
        head = raw["head"]
        base = raw["base"]
        if type(head) is not str or SHA_RE.fullmatch(head) is None:
            raise CourtError("head must be a 40-char sha")
        if type(base) is not str or SHA_RE.fullmatch(base) is None:
            raise CourtError("base must be a 40-char sha")
        return cls(number, title.strip(), draft, counts["additions"], counts["deletions"], counts["changed_files"], head, base)


def lane_of(title: str) -> str:
    folded = title.lower()
    if VOLUME_RE.search(title):
        return "scatter"
    if folded.startswith("fix(ai): bounded serving") or "serving preflight" in folded:
        return "serve"
    if "tokenizer" in folded:
        return "token"
    if folded.startswith("feat(app):"):
        return "app"
    if folded.startswith("feat(dragon):"):
        return "dragon"
    if folded.startswith("feat(") or folded.startswith("fix(") or folded.startswith("plan("):
        return "draft"
    return "unknown"


def verdict_of(workload: Workload) -> str:
    lane = lane_of(workload.title)
    if lane == "scatter":
        return "hold-volume"
    if workload.draft:
        return "hold-draft"
    if workload.base != MAIN_PIN:
        return "hold-stale-base"
    if lane in READY_LANES and workload.changed_files <= 12 and workload.additions <= 2000:
        return "eligible-after-ci"
    if lane in REVIEW_LANES or lane in READY_LANES:
        return "hold-review"
    return "hold-unknown"


def digest_of(rows: Sequence[Mapping[str, object]]) -> str:
    payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def court(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Classify a window. Empty input is a hard failure, not an empty pass."""
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise CourtError("records must be a sequence of mappings")
    if not records:
        raise CourtError("empty workload window")
    if len(records) > 64:
        raise CourtError("workload window exceeds 64")
    seen: set[int] = set()
    cards: list[dict[str, object]] = []
    counts = {"eligible-after-ci": 0, "hold-volume": 0, "hold-draft": 0, "hold-stale-base": 0, "hold-review": 0, "hold-unknown": 0}
    for raw in records:
        if not isinstance(raw, Mapping):
            raise CourtError("record must be a mapping")
        workload = Workload.from_mapping(raw)
        if workload.number in seen:
            raise CourtError("duplicate pull number")
        seen.add(workload.number)
        lane = lane_of(workload.title)
        verdict = verdict_of(workload)
        counts[verdict] = counts.get(verdict, 0) + 1
        cards.append({
            "number": workload.number,
            "lane": lane,
            "verdict": verdict,
            "draft": workload.draft,
            "head": workload.head,
            "base_matches_pin": workload.base == MAIN_PIN,
            "stored_prose": 0,
        })
    cards.sort(key=lambda row: int(row["number"]))
    body = {
        "schema": SCHEMA,
        "packet": PACKET,
        "parent": PARENT,
        "stored_prose": 0,
        "main_pin": MAIN_PIN,
        "counts": counts,
        "cards": cards,
        "merge_authority": 0,
    }
    return {**body, "digest": digest_of(cards)}


def observed() -> dict[str, object]:
    return court(OBSERVED_WINDOW)


__all__ = ["CourtError", "OBSERVED_WINDOW", "Workload", "court", "lane_of", "observed", "verdict_of"]
