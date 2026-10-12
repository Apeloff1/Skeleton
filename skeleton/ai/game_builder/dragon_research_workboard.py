"""Three-hatchling research workboard, deliberately non-executing.

Presents bounded, provenance-backed next-review actions across article,
video and updated-source lanes. It cannot schedule a worker, grant a source
license, award XP or promote a model weight. No quote text is returned.
"""
from __future__ import annotations

from .dragon_almanacs import _auth
from .dragon_article_hatchling import DragonArticleHatchling
from .dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from .dragon_source_delta_ledger import DragonSourceDeltaLedger
from .dragon_research_source_picker import DragonResearchSourcePicker
from .reviewed_knowledge import _integer

_LANES=("article","video","updates")
_LABELS={
    "article_candidate":"Independent article evidence review",
    "article_needs_capture":"Article source requires separately permitted acquisition",
    "video_candidate":"Independent timecoded transcript review",
    "video_needs_transcript":"Licensed transcript and reviewer attestation required",
    "update_candidate":"Independent changed-source review",
    "update_needs_idle_analysis":"Idle update worker may stage a real changed revision",
    "update_superseded":"Staged change superseded; re-evaluate changed source",
    "update_unchanged":"No new source-content change to analyze",
    "update_needs_revisions":"At least two governed captures are required",
}


class DragonResearchWorkboard:
    """Read-only owner-verified workload hints; never worker tickets."""

    def __init__(self,article:DragonArticleHatchling,
                 video:DragonVideoTranscriptLedger,
                 updates:DragonSourceDeltaLedger):
        if (not isinstance(article,DragonArticleHatchling)
            or not isinstance(video,DragonVideoTranscriptLedger)
            or not isinstance(updates,DragonSourceDeltaLedger)
            or article.captures.db is not video.db
            or video.db is not updates.db):
            raise TypeError("canonical same-owner hatchling authorities required")
        self.article=article
        self.video=video
        self.updates=updates
        self.picker=DragonResearchSourcePicker(article,video,updates)

    @staticmethod
    def _mission(lane:str,source:dict,action:str,
                 *,receipt:str|None,observed_at:int|None)->dict:
        if lane not in _LANES or action not in _LABELS:
            raise ValueError("unrecognized Dragon research action")
        return {
            "lane":lane,
            "source_id":source["source_id"],
            "source_kind":source["kind"],
            "host":source["host"],
            "label":source["label"],
            "action":action,
            "next_step":_LABELS[action],
            "evidence_digest":receipt,
            "observed_at":observed_at,
            "requires_idle":action=="update_needs_idle_analysis",
            "requires_operator_authorization":action in {
                "article_needs_capture","video_needs_transcript",
                "update_needs_idle_analysis",
            },
            "requires_independent_wiki_review":action.endswith("_candidate"),
            "automatically_executable":False,
            "source_independence_verified":False,
            "xp_awarded":0,
            "model_training_authorized":False,
        }

    def page(self,owner:str,*,authorized:bool,
             limit:int=30,after_source:str|None=None)->dict:
        _auth(owner,authorized)
        _integer(limit,"workboard page size",1,60)
        listing=self.picker.page(
            owner,authorized=True,limit=limit,after_source=after_source)
        tasks=[]
        for source in listing["entries"]:
            sid=source["source_id"]
            if source["kind"]=="video":
                track=self.video.review_packet(
                    owner,sid,authorized=True,include_quotes=False)
                tasks.append(self._mission(
                    "video",source,
                    "video_candidate" if track else "video_needs_transcript",
                    receipt=track["capture_digest"] if track else None,
                    observed_at=track["observed_at"] if track else None))
                continue
            packet=self.article.review_packet(
                owner,sid,authorized=True,include_quotes=False)
            article_receipt=packet["candidate_capture_digest"]
            tasks.append(self._mission(
                "article",source,
                "article_candidate" if article_receipt else "article_needs_capture",
                receipt=article_receipt,
                observed_at=packet["candidate_observed_at"]))
            staged=None
            try:
                staged=self.updates.review_packet(owner,sid,authorized=True)
            except ValueError as exc:
                # A genuine later capture changes the meaning of a staged
                # report. Do not hide unrelated journal/custody corruption.
                if "supersedes" not in str(exc) and "superseded" not in str(exc):
                    raise
                action="update_superseded"
                tasks.append(self._mission(
                    "updates",source,action,receipt=None,
                    observed_at=packet["latest_observation_at"]))
                continue
            if staged:
                action="update_candidate"
                receipt=staged["delta_receipt"]
                observed=staged["observed_at"]
            else:
                state=self.updates.preview(owner,sid,authorized=True)
                action=("update_needs_idle_analysis" if state.get("change")=="changed"
                        else "update_unchanged" if
                        state.get("status")=="unchanged_reobservation"
                        else "update_needs_revisions")
                receipt=state.get("latest_capture_digest")
                observed=state.get("observed_at")
            tasks.append(self._mission(
                "updates",source,action,receipt=receipt,
                observed_at=observed))
        counts={lane:sum(x["lane"]==lane for x in tasks) for lane in _LANES}
        return {
            "schema":"skeleton.dragon.research_workboard.v1",
            "owner":owner,"missions":tasks,
            "lane_counts":counts,
            "sources_on_page":listing["page_size"],
            "mission_count":len(tasks),
            "has_more":listing["has_more"],
            "next_after_source":listing["next_after_source"],
            "read_only":True,
            "network_requests":0,
            "workers_started":0,
            "permissions_granted":0,
            "xp_awarded":0,
            "knowledge_approved":False,
            "training_authorized":False,
        }
