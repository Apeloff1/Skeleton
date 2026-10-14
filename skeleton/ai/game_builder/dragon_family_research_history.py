"""Read-only, source-exact family history for all three Dragon hatchlings.

A timeline is a projection of already-verified journal records, not a new
source of truth, factual approval, growth authority or training receipt.
All source and owner identities are checked by their original custodians.
"""
from __future__ import annotations

from .dragon_almanacs import _auth
from .dragon_article_hatchling import DragonArticleHatchling
from .dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from .dragon_source_delta_ledger import DragonSourceDeltaLedger
from .reviewed_knowledge import _integer


class DragonFamilyResearchHistory:
    def __init__(self, article:DragonArticleHatchling,
                 video:DragonVideoTranscriptLedger,
                 updates:DragonSourceDeltaLedger):
        if (not isinstance(article,DragonArticleHatchling)
            or not isinstance(video,DragonVideoTranscriptLedger)
            or not isinstance(updates,DragonSourceDeltaLedger)
            or article.captures.db is not video.db
            or video.db is not updates.db):
            raise TypeError("canonical three-lane owner research custody required")
        self.article=article
        self.video=video
        self.updates=updates

    def timeline(self,owner:str,*,article_source_id:str,
                 video_source_id:str,update_source_id:str,
                 authorized:bool,limit:int=40)->dict:
        _auth(owner,authorized)
        _integer(limit,"family history page",1,100)
        if video_source_id in (article_source_id,update_source_id):
            raise ValueError("video and web-source identities must differ")
        # Always verify all three canonical source identities BEFORE exposing
        # even digest-only timeline data. No swallowed integrity failures.
        self.article.captures._source(owner,article_source_id)
        self.article.captures._source(owner,update_source_id)
        self.video._source(owner,video_source_id)
        events=[]
        for event in self.article.captures._history(owner,article_source_id):
            kind=event["change"]
            if kind not in {"new","changed","unchanged"}:
                raise ValueError("unknown article change in verified history")
            note=("(Article captured for evidence review)" if kind=="new"
                  else "(Article source content changed; review needed)"
                  if kind=="changed" else
                  "(Article reobserved unchanged; no new evidence gained)")
            events.append({
                "lane":"article",
                "source_id":article_source_id,
                "event_digest":event["digest"],
                "observation_at":event["observed_at"],
                "sequence":event["sequence"],
                "kind":kind,"change_note":note,
                "content_sha256":event["content_sha256"],
                "requires_independent_review":kind!="unchanged",
            })
        for event in self.video._history(owner,video_source_id):
            if event["change"] not in {"new","changed","unchanged"}:
                raise ValueError("unknown video change in verified history")
            events.append({
                "lane":"video",
                "source_id":video_source_id,
                "event_digest":event["digest"],
                "observation_at":event["observed_at"],
                "sequence":event["sequence"],
                "kind":event["change"],
                "change_note":event["improvements"][0],
                "content_sha256":event["track_sha256"],
                "requires_independent_review":event["change"]!="unchanged",
            })
        for event in self.updates._history(owner,update_source_id):
            events.append({
                "lane":"updates",
                "source_id":update_source_id,
                "event_digest":event["digest"],
                "observation_at":event["observed_at"],
                "sequence":event["sequence"],
                "kind":"changed_revision_staged",
                "change_note":event["improvements"][0],
                "content_sha256":None,
                "requires_independent_review":True,
            })
        events.sort(
            key=lambda x:(-x["observation_at"],x["lane"],-x["sequence"],
                          x["event_digest"]))
        visible=events[:limit]
        counts={lane:sum(v["lane"]==lane for v in events)
                for lane in ("article","video","updates")}
        return {
            "schema":"skeleton.dragon.three_hatchling_history.v1",
            "owner":owner,
            "source_ids":{
                "article":article_source_id,
                "video":video_source_id,
                "updates":update_source_id,
            },
            "entries":visible,
            "event_counts":counts,
            "total_events":len(events),
            "truncated":len(events)>len(visible),
            "read_only":True,"network_requests":0,
            "workers_started":0,"xp_awarded":0,
            "source_independence_verified":False,
            "knowledge_approved":False,
            "training_authorized":False,
        }
