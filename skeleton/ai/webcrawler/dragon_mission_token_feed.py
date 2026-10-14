"""Permissioned, token-verifiable native-model data preparation (native-model preparation family).

Tokenizer is injected: this module does not substitute byte counting or
whitespace splitting for a real native LLM tokenizer. Corpus ingestion,
licensed training, experiment split, evaluation and memory promotion are
different authorities with explicit handoff receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
from typing import Callable, Iterable
from math import isfinite
import json

from .core import CrawlDocument
from .dragon_mission_quality import (
    RightsGrant, TextSpan, require_training_grant,
    scan_untrusted_instructions, mask_personal_data, rank_query_passages,
)
from .dragon_source_independence import SourceProvenance, derive_dependency_clusters


@dataclass(frozen=True)
class CuratedFragment:
    source_id: str
    content_hash: str
    canonical_url: str
    start: int
    end: int
    text: str
    masked: bool
    rights_fingerprint: str
    preparation_digest: str


@dataclass(frozen=True)
class EncodedFragment:
    fragment: CuratedFragment
    tokens: tuple[int, ...]
    token_digest: str
    tokenizer_id: str


@dataclass(frozen=True)
class TokenWindow:
    window_id: str
    source_id: str
    revision: str
    tokenizer_id: str
    token_start: int
    token_end: int
    tokens: tuple[int, ...]
    rights_fingerprint: str


@dataclass(frozen=True)
class DatasetAssignment:
    source_id: str
    dependency_cluster: str
    split: str


@dataclass(frozen=True)
class YearTaggedWindow:
    window: TokenWindow
    publication_year: int | None


@dataclass(frozen=True)
class TrainingManifest:
    model_task: str
    windows: tuple[TokenWindow, ...]
    assignments: tuple[DatasetAssignment, ...]
    training_tokens: int
    validation_tokens: int
    test_tokens: int
    fingerprint: str
    approval_required: bool = True


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


# 11. Rights-bound, query-centered fragments; suspicious instructions quarantine.
def curate_training_fragment(
    source_id: str, document: CrawlDocument, grant: RightsGrant | None,
    *, purpose: str, now: float, query: str,
    max_chars: int = 600, minimum_coverage: float = .2,
) -> CuratedFragment:
    if not isinstance(source_id,str) or not 1 <= len(source_id) <= 256:
        raise ValueError("invalid source ID")
    if not isinstance(minimum_coverage,(float,int)) or not isfinite(minimum_coverage) or not 0 < minimum_coverage <= 1:
        raise ValueError("invalid minimum coverage")
    license_fp = require_training_grant(document, grant, purpose=purpose, now=now)
    if scan_untrusted_instructions(document.text):
        raise PermissionError("untrusted instructions require quarantine before training")
    ranked = rank_query_passages(document.text, query, limit=1, max_chars=max_chars)
    if not ranked or ranked[0].query_coverage < minimum_coverage:
        raise ValueError("no relevant grounded passage")
    span = ranked[0].span
    safe, masked = mask_personal_data(span.text)
    if not safe.strip():
        raise ValueError("empty redacted training example")
    fp = _digest([
        "skeleton.crawler.curated_fragment.v1", source_id,
        document.content_hash, document.canonical_url,
        span.start, span.end, safe, license_fp,
    ])
    return CuratedFragment(
        source_id, document.content_hash, document.canonical_url,
        span.start, span.end, safe, bool(masked), license_fp, fp,
    )


# 12. Real tokenizer adapter with lossless roundtrip and finite ID budget.
def encode_verified_tokens(
    fragment: CuratedFragment,
    encode: Callable[[str], Iterable[int]],
    decode: Callable[[tuple[int, ...]], str],
    *, tokenizer_id: str, max_tokens: int = 32768,
) -> EncodedFragment:
    if not isinstance(fragment,CuratedFragment) or not fragment.rights_fingerprint:
        raise ValueError("rights-bound fragment required")
    if not isinstance(tokenizer_id,str) or not 1 <= len(tokenizer_id) <= 128:
        raise ValueError("invalid tokenizer ID")
    if not 1 <= max_tokens <= 1000000:
        raise ValueError("invalid tokenizer budget")
    # Never exhaust an untrusted/tokenizer-provided generator without a hard
    # output ceiling: an eager tuple() could run forever before budget checks.
    tokens = tuple(islice(encode(fragment.text), max_tokens + 1))
    if len(tokens) > max_tokens or not tokens:
        raise ValueError("token budget exceeded or empty encoding")
    if any(not isinstance(token,int) or isinstance(token,bool)
           or not 0 <= token < 2**32 for token in tokens):
        raise ValueError("invalid tokenizer IDs")
    if decode(tokens) != fragment.text:
        raise ValueError("tokenizer roundtrip mismatch")
    return EncodedFragment(
        fragment, tokens, _digest([tokenizer_id, tokens]), tokenizer_id,
    )


# 13. Exact token windows (not approximate byte or word splits).
def pack_token_windows(
    encoded: EncodedFragment, *,
    max_window_tokens: int = 2048,
    overlap_tokens: int = 128,
    max_windows: int = 10000,
) -> tuple[TokenWindow, ...]:
    if not isinstance(encoded, EncodedFragment):
        raise ValueError("verified token fragment required")
    if not 1 <= max_window_tokens <= 131072 or not 0 <= overlap_tokens < max_window_tokens:
        raise ValueError("invalid token window geometry")
    if not 1 <= max_windows <= 100000:
        raise ValueError("invalid window count")
    if any(not isinstance(t,int) or isinstance(t,bool) or t<0 or t>=2**32
           for t in encoded.tokens):
        raise ValueError("invalid encoded token content")
    if _digest([encoded.tokenizer_id, encoded.tokens]) != encoded.token_digest:
        raise ValueError("corrupt token digest")
    windows = []
    start = 0
    while start < len(encoded.tokens):
        end = min(len(encoded.tokens), start + max_window_tokens)
        subset=encoded.tokens[start:end]
        fp=_digest([
            "skeleton.crawler.token_window.v1", encoded.fragment.preparation_digest,
            encoded.tokenizer_id, start, end, subset,
        ])
        if len(windows) >= max_windows:
            raise ValueError("window capacity exceeded")
        windows.append(TokenWindow(
            fp, encoded.fragment.source_id, encoded.fragment.content_hash,
            encoded.tokenizer_id, start, end, subset,
            encoded.fragment.rights_fingerprint,
        ))
        if end == len(encoded.tokens):
            break
        start = end-overlap_tokens
    return tuple(windows)


# 14. Prevent provenance-dependent documents leaking across train/eval.
def assign_dependency_splits(
    manifest: Iterable[SourceProvenance], *,
    seed: str, train_share: float = .8, validation_share: float = .1,
    max_sources: int = 10000,
) -> tuple[DatasetAssignment, ...]:
    if not isinstance(seed,str) or not 1 <= len(seed) <= 128:
        raise ValueError("invalid split seed")
    if any(not isinstance(n,(int,float)) or isinstance(n,bool) or not isfinite(n)
           for n in (train_share, validation_share)):
        raise ValueError("invalid split fractions")
    if not (0 < train_share < 1 and 0 < validation_share < 1
            and train_share + validation_share < 1):
        raise ValueError("invalid split fractions")
    if not 1 <= max_sources <= 100000:
        raise ValueError("split source budget exceeded")
    sources=tuple(islice(manifest,max_sources+1))
    if len(sources)>max_sources:
        raise ValueError("split source budget exceeded")
    clusters=derive_dependency_clusters(sources,authorized=True,max_sources=max_sources)
    mapping=[]
    for cluster in clusters:
        token=int(_digest([seed,cluster.cluster_id])[:16],16)/(16**16)
        split=("train" if token<train_share else
               "validation" if token<train_share+validation_share else "test")
        for sid in cluster.source_ids:
            mapping.append(DatasetAssignment(sid,cluster.cluster_id,split))
    return tuple(sorted(mapping,key=lambda a:a.source_id))


# 15. Era-aware deterministic down-selection for historical domain coverage.
def balance_decade_windows(
    tagged: Iterable[YearTaggedWindow], *,
    per_decade: int = 100,
    unknown_limit: int = 10,
    max_inputs: int = 100000,
) -> tuple[YearTaggedWindow, ...]:
    if not 1 <= max_inputs <= 1000000:
        raise ValueError("historical sampling input budget exceeded")
    values=tuple(islice(tagged,max_inputs+1))
    if len(values)>max_inputs:
        raise ValueError("historical sampling input budget exceeded")
    if not 1 <= per_decade <= 100000 or not 0 <= unknown_limit <= 100000:
        raise ValueError("invalid historical quota")
    buckets:dict[int|None,list[YearTaggedWindow]]={}
    seen=set()
    for entry in values:
        if not isinstance(entry,YearTaggedWindow) or not isinstance(entry.window,TokenWindow):
            raise ValueError("invalid historical window")
        year=entry.publication_year
        if year is not None and (not isinstance(year,int) or isinstance(year,bool)
                                 or not 1400 <= year <= 2200):
            raise ValueError("invalid publication year")
        if entry.window.window_id in seen:
            raise ValueError("duplicate historical window")
        seen.add(entry.window.window_id)
        decade=(year//10*10) if year is not None else None
        buckets.setdefault(decade,[]).append(entry)
    result=[]
    for decade in sorted(buckets,key=lambda k:(k is None,k if k is not None else 0)):
        cohort=sorted(buckets[decade],key=lambda x:x.window.window_id)
        result.extend(cohort[:unknown_limit if decade is None else per_decade])
    return tuple(sorted(result,key=lambda x:x.window.window_id))


# 16. Deterministic, rights-preserving native-model data manifest.
def compile_training_manifest(
    task_id: str, windows: Iterable[TokenWindow],
    assignments: Iterable[DatasetAssignment], *,
    authorized: bool, max_windows: int = 100000,
) -> TrainingManifest:
    if not authorized:
        raise PermissionError("training manifest requires authorization")
    if not isinstance(task_id,str) or not 1 <= len(task_id) <= 128:
        raise ValueError("invalid training task")
    if not 1 <= max_windows <= 1000000:
        raise ValueError("training manifest window budget exceeded")
    chunks=tuple(islice(windows,max_windows+1))
    if len(chunks)>max_windows:
        raise ValueError("training manifest window budget exceeded")
    splits=tuple(islice(assignments,100001))
    if len(splits)>100000:
        raise ValueError("training manifest assignment budget exceeded")
    by_id={}
    by_group={}
    for assignment in splits:
        if not isinstance(assignment,DatasetAssignment):
            raise ValueError("invalid dataset assignment")
        if assignment.source_id in by_id:
            raise ValueError("duplicate dataset assignment")
        if assignment.split not in ("train","validation","test"):
            raise ValueError("invalid experiment split")
        if assignment.dependency_cluster in by_group and (
            by_group[assignment.dependency_cluster] != assignment.split
        ):
            raise ValueError("dependency leakage across splits")
        by_id[assignment.source_id]=assignment.split
        by_group[assignment.dependency_cluster]=assignment.split
    ids=set()
    totals={"train":0,"validation":0,"test":0}
    for window in chunks:
        if not isinstance(window,TokenWindow):
            raise ValueError("invalid token window")
        if window.window_id in ids:
            raise ValueError("duplicate token window")
        ids.add(window.window_id)
        if not window.rights_fingerprint or window.source_id not in by_id:
            raise ValueError("unlicensed or unassigned training token window")
        if window.token_start<0 or window.token_end-window.token_start!=len(window.tokens):
            raise ValueError("invalid token offset range")
        if not window.tokens or any(not isinstance(t,int) or isinstance(t,bool)
                                    or not 0<=t<2**32 for t in window.tokens):
            raise ValueError("invalid training tokens")
        totals[by_id[window.source_id]] += len(window.tokens)
    order=tuple(sorted(chunks,key=lambda c:c.window_id))
    assigned=tuple(sorted(splits,key=lambda s:s.source_id))
    fingerprint=_digest({
        "schema":"skeleton.crawler.native_training_manifest.v1",
        "task":task_id,
        "windows":[(w.window_id,w.source_id,w.revision,w.tokenizer_id,
                    w.token_start,w.token_end,w.tokens,w.rights_fingerprint)
                   for w in order],
        "splits":[(s.source_id,s.dependency_cluster,s.split) for s in assigned],
    })
    return TrainingManifest(
        task_id,order,assigned,totals["train"],
        totals["validation"],totals["test"],fingerprint,True,
    )
