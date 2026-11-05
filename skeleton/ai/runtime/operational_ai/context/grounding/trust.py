"""Fail-closed source policy: hard-deny scopes/rights, never upgrade by rank."""
from __future__ import annotations
from dataclasses import dataclass
from .documents import Document,GroundingError
from .poison import scan_passage
from .chunking import segment

@dataclass(frozen=True,slots=True)
class TrustDecision:
    accepted:bool
    reasons:tuple[str,...]
    source_sha256:str


def evaluate_document(doc:Document,*,allow_untrusted:bool=False,
                      quarantined_injections:bool=True)->TrustDecision:
    reasons=[]
    if doc.trust=='untrusted-reference' and not allow_untrusted:
        reasons.append('untrusted-source-policy')
    if not doc.rights or doc.rights.casefold() in {'unknown','unlicensed','tbd'}:
        reasons.append('rights-unverified')
    if quarantined_injections:
        count=0
        for passage in segment(doc):
            if scan_passage(passage):count+=1
        if count:reasons.append('prompt-injection-pattern')
    return TrustDecision(not reasons,tuple(reasons),doc.sha256)
