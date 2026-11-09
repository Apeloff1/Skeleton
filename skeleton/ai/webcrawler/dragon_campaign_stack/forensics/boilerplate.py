"""Bounded lexical repetition, boilerplate and padding review signals.

High repetition or unusually low lexical diversity can make a source appear to
match many queries without offering useful distinct evidence. Heuristics only:
do not use scores as a factual assessment or ban a source without review.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
import unicodedata

from ..contracts import digest, integer
from .frames import FrameSet


_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class BoilerplateFinding:
    source_id: str
    passage_hash: str
    total_tokens: int
    unique_token_count: int
    lexical_diversity: float
    fourgram_count: int
    repeated_fourgram_occurrences: int
    repeated_fourgram_share: float
    high_repetition_review: bool
    low_diversity_review: bool
    informational_value_verified: bool = False


@dataclass(frozen=True)
class BoilerplateReport:
    frame_set_digest: str
    findings: tuple[BoilerplateFinding, ...]
    possible_padding_passage_count: int
    held_source_ids: tuple[str, ...]
    report_digest: str
    semantic_quality_certified: bool = False
    source_text_exported: bool = False


def inspect_boilerplate(
    frames: FrameSet,
    *,
    max_tokens_per_frame: int = 8_000,
    min_signal_tokens: int = 20,
    repetition_threshold: float = .45,
    diversity_threshold: float = .22,
) -> BoilerplateReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("bound selected passages required")
    integer(max_tokens_per_frame, "lexical token cap", 16, 8_000)
    integer(min_signal_tokens, "minimum token window", 4, 200)
    for value, label in ((repetition_threshold, "repetition"),
                         (diversity_threshold, "diversity")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not .05 <= value <= 1:
            raise ValueError("invalid " + label + " threshold")
    results = []
    holds = set()
    for frame in frames.frames:
        terms = _WORD.findall(unicodedata.normalize("NFKC", frame.text).casefold())
        if len(terms) > max_tokens_per_frame:
            raise ValueError("selected passage exceeds lexical token cap")
        diversity = len(set(terms)) / len(terms) if terms else 0.
        shingles = tuple(tuple(terms[i:i + 4]) for i in range(max(0, len(terms) - 3)))
        counts = Counter(shingles)
        repeated = sum(n for n in counts.values() if n > 1)
        share = repeated / len(shingles) if shingles else 0.
        high_repeat = len(terms) >= min_signal_tokens and share >= repetition_threshold
        low_diversity = len(terms) >= min_signal_tokens and diversity <= diversity_threshold
        if high_repeat or low_diversity:
            holds.add(frame.anchor.source_id)
        results.append(BoilerplateFinding(
            frame.anchor.source_id, frame.anchor.passage_hash,
            len(terms), len(set(terms)), round(diversity, 6),
            len(shingles), repeated, round(share, 6),
            high_repeat, low_diversity,
        ))
    payload = {
        "frames": frames.frame_set_digest, "items": [asdict(x) for x in results],
        "limits": (max_tokens_per_frame, min_signal_tokens,
                   repetition_threshold, diversity_threshold),
    }
    return BoilerplateReport(
        frames.frame_set_digest, tuple(results),
        sum(x.high_repetition_review or x.low_diversity_review for x in results),
        tuple(sorted(holds)), digest(payload),
    )
