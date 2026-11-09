"""Deterministic adversarial lenses for Dragon three-source evidence.

A lexical signal of disagreement is a REVIEW QUESTION, not a resolved truth.
Do not use text markers to claim source agreement, independent provenance,
model improvement, legal permissions or autonomous neural-weight promotion.
"""
from __future__ import annotations

from collections import Counter
import re
from .contracts import canonical_digest

_TOKEN = re.compile(r"[a-z0-9]+")
_VERSION = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d{1,4}(?:\.\d{1,3}){1,3})\b",re.I)
_NEGATIVE = frozenset("not no never without cannot unsupported prohibited fails broken removed unsafe deprecated".split())
_POSITIVE = frozenset("supports supported available enabled permitted works fixed stable valid compatible".split())
_UNCERTAIN = frozenset("may might could appears perhaps reportedly allegedly preliminary estimate experimental".split())
_NARROW = frozenset("only except unless when until before after requires depends limited".split())
_MAX_TEXT = 2048
_MAX_TERMS = 16

def _shape(text: str, shared: tuple[str, ...]) -> dict:
    if not isinstance(text,str) or not 1<=len(text)<=_MAX_TEXT:
        raise ValueError("bounded source-exact passage required")
    words=_TOKEN.findall(text.lower())
    negatives=[w for w in words if w in _NEGATIVE]
    positives=[w for w in words if w in _POSITIVE]
    uncertain=[w for w in words if w in _UNCERTAIN]
    conditions=[w for w in words if w in _NARROW]
    versions=sorted(set(_VERSION.findall(text)))[:8]
    # A marker anywhere in a quote does NOT establish scoped negation.
    # Require one of the shared terms to occur within a small token window.
    spans=[]
    for i,w in enumerate(words):
        if w in shared:
            lo=max(0,i-5);hi=min(len(words),i+6)
            near=words[lo:hi]
            spans.append({
                "term":w,
                "negative_near":any(z in _NEGATIVE for z in near),
                "positive_near":any(z in _POSITIVE for z in near),
            })
    return {
        "negation_markers":negatives[:8],
        "affirmative_markers":positives[:8],
        "uncertainty_markers":uncertain[:8],
        "scope_markers":conditions[:8],
        "mentioned_versions":versions,
        "scoped_term_signals":spans[:_MAX_TERMS],
    }


def three_way_evidence_risks(article: str, video: str, update: str,
                             shared_terms: tuple[str,...]) -> dict:
    if not isinstance(shared_terms,tuple) or len(shared_terms)>_MAX_TERMS:
        raise ValueError("bounded shared term vocabulary required")
    words=tuple(sorted(set(shared_terms)))
    if any(not isinstance(t,str) or not re.fullmatch(r"[a-z0-9]{3,40}",t)
           for t in words):
        raise ValueError("canonical source term required")
    sources={"article":_shape(article,words),
             "video":_shape(video,words),
             "updates":_shape(update,words)}
    scope={}
    for role,entry in sources.items():
        for term in words:
            sigs=[s for s in entry["scoped_term_signals"] if s["term"]==term]
            if not sigs:continue
            scope[(role,term)]=(
                any(x["negative_near"] for x in sigs),
                any(x["positive_near"] for x in sigs),
            )
    contested=[]
    for term in words:
        near=[(role,*scope[(role,term)]) for role in sources if (role,term) in scope]
        if any(neg and not pos for _,neg,pos in near) and any(
            pos and not neg for _,neg,pos in near
        ):
            contested.append(term)
    versions=set(tuple(v) for v in (
        sources[role]["mentioned_versions"] for role in sources
    ) if v)
    cues=[]
    if contested:
        cues.append("possible_opposing_term_polarity")
    if len(versions)>1:
        cues.append("version_scope_disagreement_possible")
    if any(x["uncertainty_markers"] for x in sources.values()):
        cues.append("uncertainty_not_shared_by_all_sources")
    if any(x["scope_markers"] for x in sources.values()):
        cues.append("conditional_scope_needs_review")
    if len(set([article.strip(),video.strip(),update.strip()]))<3:
        cues.append("duplicate_or_paraphrased_evidence_possible")
    if not cues:
        cues.append("no_rule_based_conflict_found_not_proof_of_agreement")
    body={
        "schema":"skeleton.dragon.evidence_risk_lenses.v1",
        "sources":sources,
        "possible_conflicts":cues,
        "contested_terms":contested,
        "independent_source_review_required":True,
        "agreement_verified":False,"training_authorized":False,
        "model_improvement_proven":False,
    }
    return {**body,"lens_digest":canonical_digest(body)}
