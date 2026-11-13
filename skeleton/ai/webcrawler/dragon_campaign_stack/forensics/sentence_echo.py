"""Bounded exact normalized sentence echoes across distinct selected sources.

Similar wording is a human provenance lead, never a proof of copying, common
authorship, plagiarism, rights, corroboration or factual validity. Only
hashes and source identities leave this scanner; sentence text stays private.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import re
import unicodedata

from ..contracts import digest, integer
from .frames import FrameSet


_SPLIT = re.compile(r"[.!?\n]+")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SentenceEcho:
    normalized_sentence_hash: str
    source_ids: tuple[str, ...]
    hosts: tuple[str, ...]
    seen_in_passage_count: int
    cross_host: bool
    repeated_sentence_provenance_unverified: bool = True


@dataclass(frozen=True)
class SentenceEchoReport:
    frame_set_digest: str
    echoes: tuple[SentenceEcho, ...]
    compared_sentences: int
    source_pair_hypotheses: int
    cross_host_echo_count: int
    report_digest: str
    literal_sentences_exported: bool = False
    copying_confirmed: bool = False
    sources_independent: bool = False


def inspect_sentence_echoes(
    frames: FrameSet, *,
    min_sentence_chars: int = 28,
    max_sentences: int = 1024,
    max_echoes: int = 256,
) -> SentenceEchoReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("exact selected source frames required")
    integer(min_sentence_chars, "minimum sentence characters", 16, 512)
    integer(max_sentences, "sentence comparison capacity", 1, 1024)
    integer(max_echoes, "echo findings capacity", 1, 256)
    observations = defaultdict(set)
    hosts: dict[str, str] = {}
    total = 0
    for frame in frames.frames:
        anchor = frame.anchor
        hosts[anchor.source_id] = anchor.host
        for sentence in _SPLIT.split(frame.text):
            normalized = _SPACE.sub(" ", unicodedata.normalize("NFKC", sentence).casefold()).strip()
            if len(normalized) < min_sentence_chars:
                continue
            total += 1
            if total > max_sentences:
                raise ValueError("sentence comparison capacity exceeded")
            identity = sha256(normalized.encode("utf-8")).hexdigest()
            observations[identity].add((anchor.source_id, anchor.anchor_digest))
    echoes = []
    pairs = set()
    for key, locations in sorted(observations.items()):
        ids = tuple(sorted({source_id for source_id, _ in locations}))
        if len(ids) < 2:
            continue
        observed_hosts = tuple(sorted({hosts[x] for x in ids}))
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                pairs.add((left, right))
        echoes.append(SentenceEcho(
            key, ids, observed_hosts, len(locations), len(observed_hosts) > 1,
        ))
        if len(echoes) > max_echoes:
            raise ValueError("sentence echo capacity exceeded")
    data = {
        "frames": frames.frame_set_digest,
        "items": [asdict(x) for x in echoes], "compared": total,
        "pair_count": len(pairs),
        "limits": (min_sentence_chars, max_sentences, max_echoes),
    }
    return SentenceEchoReport(
        frames.frame_set_digest, tuple(echoes), total, len(pairs),
        sum(row.cross_host for row in echoes), digest(data),
    )
