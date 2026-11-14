"""Deterministic result merging; partial segments never become phantom full passes."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .challenge_catalog import TOTAL
from .errors import reject


def stitch(parts:tuple[ChallengeRun,...])->ChallengeRun:
    if type(parts) is not tuple or not parts or len(parts)>TOTAL:
        reject("stitch-segments")
    ordered=sorted(parts,key=lambda p:p.start)
    first=ordered[0]
    pointer=0
    results=[]
    for part in ordered:
        if type(part) is not ChallengeRun:
            reject("stitch-part-type")
        if part.start!=pointer:
            reject("stitch-gap-or-overlap")
        if part.model_sha256!=first.model_sha256 or part.source_sha256!=first.source_sha256:
            reject("stitch-model-or-source-drift")
        if part.requested!=len(part.results):
            reject("stitch-short-segment")
        results.extend(part.results)
        pointer+=len(part.results)
    if pointer>TOTAL:
        reject("stitch-overflow")
    return ChallengeRun(first.model_sha256,first.source_sha256,0,pointer,tuple(results))
