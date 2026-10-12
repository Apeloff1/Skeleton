"""Update hatchling: exact, revision-bound change detection for game research.

Reads ONLY source versions captured by Dragon's rights-governed article worker.
An observation with identical source bytes is not a change; an unreviewed
revision is NOT a verified claim, hatchling XP, or model-promotion evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re

from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission,HatchlingWorkerTicket,
)
from .contracts import canonical_digest,canonical_json
from .dragon_almanacs import _auth
from .dragon_technical_source_captures import DragonSourceCaptures
from .reviewed_knowledge import _integer

_MAX_SEGMENTS=512
_MAX_RECORDS=64
_MAX_CHANGES=12
_MAX_QUOTE=220
_MAX_EPOCH=4_102_444_800
_ISSUES={
    "api_compatibility":frozenset(
        "deprecated removed breaking incompatible migration api version".split()),
    "correctness":frozenset(
        "bug fix regression patch crash overflow invalid error".split()),
    "performance":frozenset(
        "performance latency render optimization frame memory cpu gpu".split()),
    "rights":frozenset(
        "license copyright terms rights permission trademark restricted".split()),
    "security":frozenset(
        "security vulnerability exploit unsafe cve injection validation".split()),
    "gameplay":frozenset(
        "npc quest gameplay game physics controls collision animation".split()),
}
_TOKEN=re.compile(r"[a-z0-9]+")


def _segments(text:str)->list[tuple[int,int,str]]:
    """Bound CPU by cap; never claim completeness when a text is too large."""
    matches=list(re.finditer(r".{1,256}",text,re.DOTALL))
    if len(matches)>_MAX_SEGMENTS:
        raise ValueError("source revision too large for exact bounded diff")
    return [(m.start(),m.end(),m.group()) for m in matches]


def _excerpt(text:str,start:int,end:int)->dict:
    a=max(0,start);b=min(len(text),end)
    quote=text[a:min(b,a+_MAX_QUOTE)]
    if quote!=text[a:a+len(quote)]:
        raise ValueError("non-exact source excerpt")
    tokens=set(_TOKEN.findall(quote.lower()))
    issues={
        issue:sorted(tokens&terms)
        for issue,terms in _ISSUES.items() if tokens&terms
    }
    return {
        "start":a,"end":a+len(quote),"exact_quote":quote,
        "lens_triggers":issues,"independently_verified":False,
    }


class DragonSourceDeltaLedger:
    """Immutable change journal; separate Wiki acceptance required."""

    def __init__(self,captures:DragonSourceCaptures):
        if not isinstance(captures,DragonSourceCaptures):
            raise TypeError("canonical source-capture authority required")
        self.captures=captures
        self.db=captures.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_deltas_v1(
            owner TEXT NOT NULL,source TEXT NOT NULL,sequence INTEGER NOT NULL,
            body TEXT NOT NULL,digest TEXT NOT NULL,
            PRIMARY KEY(owner,source,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_delta_heads_v1(
            owner TEXT NOT NULL,source TEXT NOT NULL,
            sequence INTEGER NOT NULL,digest TEXT NOT NULL,
            PRIMARY KEY(owner,source))""")

    def _history(self,owner,source):
        rows=self.db.execute(
            "SELECT sequence,body,digest FROM dragon_source_deltas_v1 "
            "WHERE owner=? AND source=? ORDER BY sequence LIMIT ?",
            (owner,source,_MAX_RECORDS+1)).fetchall()
        if len(rows)>_MAX_RECORDS:
            raise ValueError("update hatchling journal capacity exhausted")
        prev=None;out=[]
        for idx,(seq,raw,digest) in enumerate(rows,1):
            if not isinstance(raw,str) or len(raw.encode())>19_000:
                raise ValueError("oversize delta history")
            obj=json.loads(raw)
            if (seq!=idx or obj.get("owner")!=owner
                or obj.get("source_id")!=source or obj.get("sequence")!=idx
                or obj.get("parent_digest")!=prev
                or obj.get("training_authorized") is not False
                or obj.get("knowledge_approved") is not False
                or canonical_digest(obj)!=digest):
                raise ValueError("source update journal custody invalid")
            out.append({**obj,"digest":digest})
            prev=digest
        head=self.db.execute(
            "SELECT sequence,digest FROM dragon_source_delta_heads_v1 "
            "WHERE owner=? AND source=?",(owner,source)).fetchone()
        if bool(head)!=bool(out) or (out and head!=(len(out),prev)):
            raise ValueError("source update head integrity invalid")
        return out

    def preview(self,owner:str,source_id:str,*,authorized:bool,
                capture_digest:str|None=None)->dict:
        """Pure comparison, never a claim of published/verified improvement."""
        _auth(owner,authorized)
        self.captures._source(owner,source_id)
        chain=self.captures._history(owner,source_id)
        if len(chain)<2:
            return {
                "owner":owner,"source_id":source_id,
                "status":"needs_two_actual_captures",
                "changed":False,"independent_review_required":True,
                "model_training_authorized":False,
            }
        if capture_digest is None:
            new=chain[-1]
            prior_chain=chain[:-1]
        else:
            index=next((i for i,r in enumerate(chain)
                        if r["digest"]==capture_digest),None)
            if index is None:
                raise ValueError("source revision not in canonical capture history")
            new=chain[index]
            prior_chain=chain[:index]
            if any(r["content_sha256"]!=new["content_sha256"]
                   for r in chain[index+1:]):
                raise ValueError("later changed source revision supersedes delta")
        old=next((r for r in reversed(prior_chain)
                  if r["content_sha256"]!=new["content_sha256"]),None)
        if new["change"]=="unchanged":
            # Re-observation of identical text is not new information, even
            # if an earlier changed revision is available in history.
            return {
                "owner":owner,"source_id":source_id,
                "status":"unchanged_reobservation","changed":False,
                "latest_capture_digest":new["digest"],
                "independent_review_required":False,
                "model_training_authorized":False,
            }
        if old is None or new["change"]!="changed":
            return {
                "owner":owner,"source_id":source_id,
                "status":"no_prior_distinct_text","changed":False,
                "independent_review_required":True,
                "model_training_authorized":False,
            }
        before=old["document"]["text"]
        after=new["document"]["text"]
        original=_segments(before);updated=_segments(after)
        matcher=SequenceMatcher(
            None,[x[2] for x in original],[x[2] for x in updated],
            autojunk=True,
        )
        edits=[]
        operations=matcher.get_opcodes()
        total_changes=sum(tag!="equal" for tag,_,_,_,_ in operations)
        for op,lo,hi,ln,hn in operations:
            if op=="equal" or len(edits)>=_MAX_CHANGES:
                continue
            prior=None
            if hi>lo:
                a=original[lo][0];b=original[hi-1][1]
                prior=_excerpt(before,a,b)
            current=None
            if hn>ln:
                a=updated[ln][0];b=updated[hn-1][1]
                current=_excerpt(after,a,b)
            edits.append({
                "kind":op,"before":prior,"after":current,
                "possible_meaning_changed":True,
                "requires_human_comparison":True,
            })
        payload={
            "schema":"skeleton.dragon.source_delta_preview.v1",
            "owner":owner,"source_id":source_id,
            "source_url":new["source_url"],
            "previous_capture_digest":old["digest"],
            "latest_capture_digest":new["digest"],
            "previous_content_sha256":old["content_sha256"],
            "latest_content_sha256":new["content_sha256"],
            "observed_at":new["observed_at"],
            "change":"changed",
            "total_changed_segments":total_changes,
            "shown_changes":edits,
            "truncated":total_changes>len(edits),
            "review_questions":[
                "Does the new wording invalidate existing game-building techniques?",
                "Are rights, compatibility, security or API assumptions superseded?",
                "Can independent sources reproduce the technical change?",
            ],
            "independent_review_required":True,
            "knowledge_approved":False,"training_authorized":False,
        }
        return {**payload,"delta_digest":canonical_digest(payload)}

    def stage_idle(self,admission:DragonNestWorkerAdmission,
                   ticket:HatchlingWorkerTicket,*,sample,at:str,idle_since:str,
                   now_seconds:float,authorized:bool,trusted_worker:bool,
                   consented:bool,updates_consent:bool)->dict:
        if (not isinstance(admission,DragonNestWorkerAdmission)
            or not isinstance(ticket,HatchlingWorkerTicket)
            or ticket.lane!="updates"
            or admission.feed.almanacs is not self.captures.a):
            raise TypeError("exact update hatchling and canonical source authority required")
        _auth(ticket.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted update worker required")
        try:
            if consented is not True or updates_consent is not True:
                raise PermissionError("separate update specialist consent required")
            if not admission.authorize_chunk(
                ticket,sample=sample,at=at,idle_since=idle_since,
                now_seconds=now_seconds,authorized=True,trusted_worker=True,
                consented=True,article_consent=False,
                video_consent=False,updates_consent=True):
                raise PermissionError("update worker not idle or resource-admitted")
            source,_=self.captures._source(ticket.owner,ticket.source_id)
            if source["url"]!=ticket.source_url:
                raise PermissionError("updates ticket source identity differs")
            report=self.preview(ticket.owner,ticket.source_id,authorized=True)
            if report.get("changed") is False or report.get("change")!="changed":
                return {"status":"no_new_changed_evidence",
                        "source_id":ticket.source_id,"training_authorized":False}
            self.db.execute("BEGIN IMMEDIATE")
            try:
                entries=self._history(ticket.owner,ticket.source_id)
                for item in entries:
                    if item["latest_capture_digest"]==report["latest_capture_digest"]:
                        if item["delta_digest"]!=report["delta_digest"]:
                            raise ValueError("same source revision has conflicting delta")
                        self.db.execute("COMMIT")
                        return {"status":"already_staged",
                                "delta_receipt":item["digest"],
                                "training_authorized":False}
                if len(entries)>=_MAX_RECORDS:
                    raise ValueError("source update journal exhausted")
                latest=self.captures._history(ticket.owner,ticket.source_id)
                if not latest or latest[-1]["digest"]!=report["latest_capture_digest"]:
                    raise ValueError("source changed during update analysis")
                body={
                    "schema":"skeleton.dragon.source_delta_receipt.v1",
                    "owner":ticket.owner,"source_id":ticket.source_id,
                    "sequence":len(entries)+1,
                    "parent_digest":entries[-1]["digest"] if entries else None,
                    "latest_capture_digest":report["latest_capture_digest"],
                    "delta_digest":report["delta_digest"],
                    "observed_at":report["observed_at"],
                    "candidate_changes":report["shown_changes"],
                    "improvements":["(exact changed source spans prepared for Wiki scrutiny)"],
                    "knowledge_approved":False,"training_authorized":False,
                }
                digest=canonical_digest(body)
                self.db.execute(
                    "INSERT INTO dragon_source_deltas_v1 VALUES(?,?,?,?,?)",
                    (ticket.owner,ticket.source_id,len(entries)+1,
                     canonical_json(body),digest))
                self.db.execute(
                    "INSERT INTO dragon_source_delta_heads_v1 VALUES(?,?,?,?) "
                    "ON CONFLICT(owner,source) DO UPDATE SET "
                    "sequence=excluded.sequence,digest=excluded.digest",
                    (ticket.owner,ticket.source_id,len(entries)+1,digest))
                self.db.execute("COMMIT")
                return {
                    "status":"awaiting_independent_update_review",
                    "delta_receipt":digest,
                    "changes":len(body["candidate_changes"]),
                    "model_training_authorized":False,
                }
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        finally:
            admission.stopped(
                ticket,authorized=True,trusted_worker=True,worker_stopped=True)

    def review_packet(self,owner:str,source_id:str,*,authorized:bool)->dict|None:
        _auth(owner,authorized)
        self.captures._source(owner,source_id)
        chain=self._history(owner,source_id)
        if not chain:
            return None
        last=chain[-1]
        report=self.preview(
            owner,source_id,authorized=True,
            capture_digest=last["latest_capture_digest"])
        if (report.get("latest_capture_digest")!=last["latest_capture_digest"]
            or report.get("delta_digest")!=last["delta_digest"]
            or report.get("shown_changes")!=last["candidate_changes"]):
            raise ValueError("staged update superseded; reanalyze")
        return {
            "schema":"skeleton.dragon.source_delta_review.v1",
            "owner":owner,"source_id":source_id,
            "delta_receipt":last["digest"],
            "latest_capture_digest":last["latest_capture_digest"],
            "observed_at":last["observed_at"],
            "change_count":len(last["candidate_changes"]),
            "candidate_changes":last["candidate_changes"],
            "independent_claim_review_required":True,
            "knowledge_approved":False,"model_training_authorized":False,
        }
