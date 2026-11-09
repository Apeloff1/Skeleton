"""Mother Dragon: cross-media evidence discovery, NOT independent corroboration.

Combines only registered, owner-bound, content-provenance-checked video cue
history and source-revision diff receipts. Shared vocabulary suggests questions
for Wiki/HOAG to investigate. It cannot assert factual agreement or award XP.
"""
from __future__ import annotations

from collections import Counter
import re

from .dragon_source_delta_ledger import DragonSourceDeltaLedger
from .dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from .dragon_almanacs import _auth

_WORDS=re.compile(r"[a-z0-9]+")
_STOP=frozenset((
    "a an and are as at be by can for from has have in into is it of on or"
    " that the their this to was were when with would you your game games"
).split())
_MAX_MATCHES=12
_MAX_TERMS=16


def _terms(value:str)->set[str]:
    return {t for t in _WORDS.findall(value.lower())
            if len(t)>=3 and t not in _STOP}


class DragonMotherEvidenceSynergy:
    """Read-only cross-lane, review-required game-building research bridges."""

    def __init__(self,video:DragonVideoTranscriptLedger,
                 deltas:DragonSourceDeltaLedger):
        if (not isinstance(video,DragonVideoTranscriptLedger)
            or not isinstance(deltas,DragonSourceDeltaLedger)
            or video.db is not deltas.db):
            raise TypeError("same canonical owner source custody required")
        self.video=video
        self.deltas=deltas

    def preview(self,owner:str,video_source_id:str,article_source_id:str,
                *,authorized:bool)->dict:
        _auth(owner,authorized)
        if video_source_id==article_source_id:
            raise ValueError("independent media/source identities required")
        video=self.video.review_packet(
            owner,video_source_id,authorized=True,include_quotes=True)
        delta=self.deltas.review_packet(
            owner,article_source_id,authorized=True)
        if video is None or delta is None:
            return {
                "schema":"skeleton.dragon.mother_cross_media.v1",
                "owner":owner,"video_source_id":video_source_id,
                "article_source_id":article_source_id,
                "status":"missing_independent_review_candidates",
                "bridges":[],"knowledge_approved":False,
                "training_authorized":False,
            }
        hits=[];cooccurrence=Counter()
        for cue in video["timecoded_cues"][:64]:
            video_terms=_terms(cue["text"])
            for change in delta["candidate_changes"][:12]:
                latest=change["after"]
                if not latest:
                    continue
                shared=sorted(video_terms&_terms(latest["exact_quote"]))
                if not shared:
                    continue
                shared=shared[:_MAX_TERMS]
                cooccurrence.update(shared)
                hits.append({
                    "video_start_ms":cue["start_ms"],
                    "video_end_ms":cue["end_ms"],
                    "video_exact_quote":cue["text"],
                    "article_start":latest["start"],
                    "article_end":latest["end"],
                    "article_exact_quote":latest["exact_quote"],
                    "shared_vocabulary":shared,
                    "source_independence_verified":False,
                    "content_agreement_verified":False,
                    "verification_prompt":
                        "Do the independently rights-reviewed sources really describe "
                        "the same mechanism, version and constraints?",
                })
                if len(hits)>=_MAX_MATCHES:
                    break
            if len(hits)>=_MAX_MATCHES:
                break
        return {
            "schema":"skeleton.dragon.mother_cross_media.v1",
            "owner":owner,
            "video_source_id":video_source_id,
            "article_source_id":article_source_id,
            "video_capture_digest":video["capture_digest"],
            "article_delta_receipt":delta["delta_receipt"],
            "status":"possible_cross_media_relevance" if hits else
                     "no_lexical_cross_media_match",
            "bridges":hits,
            "task_terms":dict(sorted(cooccurrence.items())),
            "independent_review_required":True,
            "source_independence_verified":False,
            "knowledge_approved":False,
            "training_authorized":False,
            "improvements":["(cross-media exact source clues routed to Wiki scrutiny)"],
        }
