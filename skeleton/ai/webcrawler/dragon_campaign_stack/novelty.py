"""Bounded lexical novelty, exact copies, and near-duplicate research families.

Duplicate grouping is a cost and diversity hint. It is never a substitute
for content provenance, independent corroboration or source rights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
import re

from .contracts import digest, exact_digest, finite


_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class NoveltyDocument:
    source_id: str
    preserved_text_hash: str
    text: str

    def __post_init__(self):
        exact_digest(self.source_id, "source identity")
        exact_digest(self.preserved_text_hash, "retained hash")
        if not isinstance(self.text, str) or not 0 < len(self.text.encode("utf-8")) <= 24_000:
            raise ValueError("novelty text capacity exceeded")
        if sha256(self.text.encode("utf-8")).hexdigest() != self.preserved_text_hash:
            raise ValueError("novelty source hash mismatch")


@dataclass(frozen=True)
class NoveltyPair:
    first_source_id: str
    second_source_id: str
    similarity: float
    same_preserved_text: bool
    near_duplicate: bool


@dataclass(frozen=True)
class NoveltyFamily:
    source_ids: tuple[str, ...]
    union_reason: str


@dataclass(frozen=True)
class NoveltyReport:
    compared_documents: int
    compared_pairs: int
    flagged_pairs: tuple[NoveltyPair, ...]
    duplicate_families: tuple[NoveltyFamily, ...]
    unique_families: int
    novelty_digest: str
    independent_corroboration_established: bool = False


def _shingles(text: str, *, maximum: int = 2048) -> frozenset[tuple[str, ...]]:
    words = [x.casefold() for x in _TOKENS.findall(text)]
    if len(words) > maximum:
        # No silent truncation: a partial shingle universe can hide a copy.
        raise ValueError("source exceeds bounded novelty tokenizer capacity")
    if len(words) < 3:
        return frozenset((x,) for x in words)
    return frozenset(tuple(words[i:i+3]) for i in range(len(words)-2))


def group_near_duplicates(
    documents: Iterable[NoveltyDocument], *,
    threshold: float = 0.82,
    maximum_documents: int = 64,
) -> NoveltyReport:
    finite(threshold, "novelty duplicate threshold", 0.5, 1.0)
    if type(maximum_documents) is not int or not 1 <= maximum_documents <= 128:
        raise ValueError("invalid novelty capacity")
    rows = tuple(documents)
    if len(rows) > maximum_documents:
        raise ValueError("novelty document budget exceeded")
    if len({x.source_id for x in rows}) != len(rows):
        raise ValueError("duplicate novelty source identity")
    rows = tuple(sorted(rows, key=lambda x: x.source_id))
    shingles = [_shingles(x.text) for x in rows]
    parent = list(range(len(rows)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        left, right = root(i), root(j)
        if left != right:
            parent[max(left, right)] = min(left, right)

    flagged = []
    pairs = 0
    for i in range(len(rows)):
        for j in range(i+1, len(rows)):
            pairs += 1
            same = rows[i].preserved_text_hash == rows[j].preserved_text_hash
            intersection = len(shingles[i] & shingles[j])
            cardinality = len(shingles[i] | shingles[j])
            score = 1.0 if same else intersection / cardinality if cardinality else 0
            near = score >= threshold
            if near:
                union(i, j)
                flagged.append(NoveltyPair(
                    rows[i].source_id, rows[j].source_id,
                    round(score, 8), same, True,
                ))
    families: dict[int, list[str]] = {}
    for i, row in enumerate(rows):
        families.setdefault(root(i), []).append(row.source_id)
    dedup = tuple(
        NoveltyFamily(tuple(sorted(group)), "lexical_similarity_only")
        for group in families.values() if len(group) > 1
    )
    dedup = tuple(sorted(dedup, key=lambda x: x.source_ids))
    payload = {
        "sources": [(x.source_id, x.preserved_text_hash) for x in rows],
        "threshold": threshold,
        "pairs": [asdict(x) for x in flagged],
        "families": [asdict(x) for x in dedup],
    }
    return NoveltyReport(
        compared_documents=len(rows),
        compared_pairs=pairs,
        flagged_pairs=tuple(flagged),
        duplicate_families=dedup,
        unique_families=len(families),
        novelty_digest=digest(payload),
    )
