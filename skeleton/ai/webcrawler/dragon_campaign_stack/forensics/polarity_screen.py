"""Simple polarity-collision leads for shared lexical statements.

A matching keyword bundle with opposite local negation is *not* a verified
contradiction; this is only a bounded question for a human to investigate.
It must not create unreviewed factual assertions or model instructions.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
import re
import unicodedata

from ..contracts import digest, integer
from .frames import FrameSet


_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_NEGATORS = frozenset(("not", "no", "never", "without", "neither", "none",
                       "doesnt", "didnt", "cannot", "false", "incorrect"))
_STOP = frozenset(("and", "the", "are", "was", "were", "this", "that", "for",
                   "from", "with", "has", "have", "about", "through", "into"))


@dataclass(frozen=True)
class PolarityReviewLead:
    left_source_id: str
    right_source_id: str
    shared_term_set_digest: str
    left_negative: bool
    right_negative: bool
    overlap_term_count: int
    review_only: bool = True
    factual_contradiction_proven: bool = False


@dataclass(frozen=True)
class PolarityScreen:
    frame_set_digest: str
    compared_source_pairs: int
    leads: tuple[PolarityReviewLead, ...]
    report_digest: str
    truth_assessed: bool = False
    source_text_exported: bool = False


def inspect_polarity_candidates(
    frames: FrameSet, *,
    min_shared_terms: int = 4,
    max_pairs: int = 496,
    max_leads: int = 256,
) -> PolarityScreen:
    if not isinstance(frames, FrameSet):
        raise TypeError("bound selected source evidence required")
    integer(min_shared_terms, "polarity term overlap", 2, 16)
    integer(max_pairs, "polarity pair cap", 1, 496)
    integer(max_leads, "polarity finding cap", 1, 256)
    by_source = defaultdict(list)
    for frame in frames.frames:
        words = _WORD.findall(unicodedata.normalize("NFKC", frame.text).casefold())
        core = frozenset(x for x in words if x not in _NEGATORS and x not in _STOP
                         and len(x) >= 4)
        by_source[frame.anchor.source_id].append((core, bool(set(words) & _NEGATORS)))
    ids = sorted(by_source)
    pairs = len(ids) * (len(ids) - 1) // 2
    if pairs > max_pairs:
        raise ValueError("polarity comparison capacity exceeded")
    leads = []
    for a, b in combinations(ids, 2):
        best = None
        for left_core, left_neg in by_source[a]:
            for right_core, right_neg in by_source[b]:
                if left_neg == right_neg:
                    continue
                shared = left_core & right_core
                if len(shared) < min_shared_terms:
                    continue
                # Stable best-overlap lead only; no arbitrary factual judgment.
                term_seal = digest(tuple(sorted(shared)))
                candidate = (len(shared), term_seal, left_neg, right_neg)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best:
            leads.append(PolarityReviewLead(
                a, b, best[1], best[2], best[3], best[0],
            ))
        if len(leads) > max_leads:
            raise ValueError("polarity review lead capacity exceeded")
    payload = {
        "frames": frames.frame_set_digest,
        "pairs": pairs, "leads": [asdict(x) for x in leads],
        "limits": (min_shared_terms, max_pairs, max_leads),
    }
    return PolarityScreen(
        frames.frame_set_digest, pairs, tuple(leads), digest(payload),
    )
