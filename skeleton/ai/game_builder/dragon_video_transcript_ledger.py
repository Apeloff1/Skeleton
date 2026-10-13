"""Video hatchling: licensed, timecoded transcript staging under a live idle grant.

No media extraction, no Youtube/Vimeo download, no model training, no implied
copyright permission. A separately controlled Ed25519 signer attests to the
exact transcript track and permission evidence; a resource-admitted video
hatchling may stage only short textual cues for independent Wiki review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.webcrawler.dragon_nest_worker_admission import (
    DragonNestWorkerAdmission, HatchlingWorkerTicket,
)
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.webcrawler.dragon_nest_research_scheduler import ResearchLead
from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_source_catalog import canonical_source_url
from .reviewed_knowledge import _id, _integer

_REVIEW_ID=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
_HEX=re.compile(r"[0-9a-f]{64}\Z")
_MAX_HISTORY=48
_MAX_CUES=64
_MAX_CUE_CHARS=200
_MAX_TRACK_BYTES=16_000
_MAX_EPOCH=4_102_444_800


@dataclass(frozen=True,slots=True)
class TimedTranscriptCue:
    start_ms:int
    end_ms:int
    text:str

    def __post_init__(self):
        _integer(self.start_ms,"cue start",0,43_200_000)
        _integer(self.end_ms,"cue end",self.start_ms+1,43_200_000)
        if (not isinstance(self.text,str)
            or not 1<=len(self.text)<=_MAX_CUE_CHARS
            or any(ord(c)<32 and c not in "\t" for c in self.text)):
            raise ValueError("bounded verbatim transcript cue required")

    def body(self)->dict:
        return {"start_ms":self.start_ms,"end_ms":self.end_ms,"text":self.text}


@dataclass(frozen=True,slots=True)
class TranscriptRightsReceipt:
    owner:str
    source_id:str
    source_url:str
    track_sha256:str
    evidence_digest:str
    reviewer:str
    issuer:str
    key_id:str
    issued_at:int
    expires_at:int
    signature_hex:str

    def body(self)->dict:
        return {
            "schema":"skeleton.dragon.external_transcript_rights.v1",
            "owner":self.owner,"source_id":self.source_id,
            "source_url":self.source_url,"track_sha256":self.track_sha256,
            "evidence_digest":self.evidence_digest,"reviewer":self.reviewer,
            "issuer":self.issuer,"key_id":self.key_id,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
            "scope":"timecoded_transcript_reference_only",
            "media_download_authorized":False,
            "training_authorized":False,
        }


class DragonVideoTranscriptLedger:
    """Staging only. Wiki/HOAG remain the only knowledge promotion authorities."""

    def __init__(self,feed:DragonNestSourceFeed, *,
                 review_public_key:bytes,issuer:str,key_id:str):
        if not isinstance(feed,DragonNestSourceFeed):
            raise TypeError("canonical signed Dragon video feed required")
        if type(review_public_key) is not bytes or len(review_public_key)!=32:
            raise ValueError("external transcript review public key required")
        _id(issuer,"transcript rights issuer");_id(key_id,"rights key identity")
        self.feed=feed
        self.db=feed.db
        self.verifier=Ed25519PublicKey.from_public_bytes(review_public_key)
        self.issuer=issuer
        self.key_id=key_id
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_video_cues_v1(
            owner TEXT NOT NULL,source TEXT NOT NULL,sequence INTEGER NOT NULL,
            body TEXT NOT NULL,digest TEXT NOT NULL,
            PRIMARY KEY(owner,source,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_video_cue_heads_v1(
            owner TEXT NOT NULL,source TEXT NOT NULL,
            sequence INTEGER NOT NULL,digest TEXT NOT NULL,
            PRIMARY KEY(owner,source))""")

    @staticmethod
    def _track(cues:tuple[TimedTranscriptCue,...])->tuple[list[dict],str]:
        if (type(cues) is not tuple or not 1<=len(cues)<=_MAX_CUES
            or any(not isinstance(c,TimedTranscriptCue) for c in cues)):
            raise ValueError("bounded typed video transcript cues required")
        last=-1
        for cue in cues:
            if cue.start_ms<last:
                raise ValueError("overlapping or unordered timecoded cues")
            last=cue.end_ms
        rows=[cue.body() for cue in cues]
        raw=canonical_json(rows)
        if len(raw.encode("utf-8"))>_MAX_TRACK_BYTES:
            raise ValueError("transcript reference text exceeds bounded retention")
        return rows,sha256(raw.encode("utf-8")).hexdigest()

    def _source(self,owner,source_id):
        row=self.db.execute(
            "SELECT body,digest FROM dragon_almanac_sources "
            "WHERE owner=? AND source=?",(owner,source_id)).fetchone()
        if row is None:
            raise ValueError("unregistered specialist video source")
        body=json.loads(row[0])
        url=body.get("url")
        if (canonical_digest(body)!=row[1]
            or body.get("source_id")!=source_id
            or body.get("kind")!="video_candidate"
            or body.get("training_authorized") is not False
            or not isinstance(url,str) or canonical_source_url(url)!=url
            or source_id!="source-"+sha256(url.encode()).hexdigest()
            or (urlsplit(url).hostname or "").lower()
                not in {"youtube.com","www.youtube.com","youtu.be",
                        "vimeo.com","www.vimeo.com"}):
            raise ValueError("registered canonical video identity required")
        job=self.db.execute(
            "SELECT state FROM dragon_almanac_jobs WHERE owner=? AND source=?",
            (owner,source_id)).fetchone()
        if not job or job[0]=="blocked":
            raise PermissionError("blocked or absent video policy job")
        return url

    def _history(self,owner:str,source_id:str)->list[dict]:
        rows=self.db.execute(
            "SELECT sequence,body,digest FROM dragon_video_cues_v1 "
            "WHERE owner=? AND source=? ORDER BY sequence LIMIT ?",
            (owner,source_id,_MAX_HISTORY+1)).fetchall()
        if len(rows)>_MAX_HISTORY:
            raise ValueError("video timeline retention capacity exceeded")
        prev=None;result=[]
        for i,(seq,raw,digest) in enumerate(rows,1):
            if type(raw) is not str or len(raw.encode())>24_000:
                raise ValueError("oversize stored transcript")
            data=json.loads(raw)
            track=tuple(TimedTranscriptCue(**c) for c in data["cues"])
            _,expected_sha=self._track(track)
            if (seq!=i or data.get("sequence")!=i
                or data.get("owner")!=owner or data.get("source_id")!=source_id
                or data.get("parent_digest")!=prev
                or data.get("track_sha256")!=expected_sha
                or data.get("knowledge_approved") is not False
                or data.get("training_authorized") is not False
                or (result and data["observed_at"]<=result[-1]["observed_at"])
                or canonical_digest(data)!=digest):
                raise ValueError("transcript custody history invalid")
            result.append({**data,"digest":digest})
            prev=digest
        head=self.db.execute(
            "SELECT sequence,digest FROM dragon_video_cue_heads_v1 "
            "WHERE owner=? AND source=?",(owner,source_id)).fetchone()
        if bool(head)!=bool(result) or (result and head!=(len(result),prev)):
            raise ValueError("transcript custody head invalid")
        return result

    def _verify_rights(self,receipt:TranscriptRightsReceipt,
                       owner:str,source_id:str,url:str,track_sha:str,now:int):
        if (not isinstance(receipt,TranscriptRightsReceipt)
            or receipt.owner!=owner or receipt.source_id!=source_id
            or receipt.source_url!=url or receipt.track_sha256!=track_sha
            or receipt.issuer!=self.issuer or receipt.key_id!=self.key_id
            or type(receipt.evidence_digest) is not str
            or not _HEX.fullmatch(receipt.evidence_digest)
            or receipt.reviewer==self.issuer
            or type(receipt.signature_hex) is not str
            or len(receipt.signature_hex)!=128
            or not receipt.issued_at<=now<receipt.expires_at
            or receipt.expires_at>receipt.issued_at+3600):
            raise PermissionError("external transcript reference permission missing or stale")
        try:
            self.verifier.verify(
                bytes.fromhex(receipt.signature_hex),
                canonical_json(receipt.body()).encode("utf-8")
            )
        except (ValueError,InvalidSignature):
            raise PermissionError("external transcript reviewer signature invalid") from None
        return canonical_digest({**receipt.body(),"signature_hex":receipt.signature_hex})

    def stage(self,admission:DragonNestWorkerAdmission,ticket:HatchlingWorkerTicket,
              *,cues:tuple[TimedTranscriptCue,...],rights:TranscriptRightsReceipt,
              attempt_id:str,at:str,idle_since:str,now_seconds:float,sample,
              authorized:bool,trusted_worker:bool,
              video_consent:bool,consented:bool)->dict:
        """One granted video worker, no HTTP; always acknowledge synchronous exit."""
        if (not isinstance(admission,DragonNestWorkerAdmission)
            or admission.feed is not self.feed
            or not isinstance(ticket,HatchlingWorkerTicket)
            or ticket.lane!="video"):
            raise TypeError("exact video hatchling and canonical admission required")
        _auth(ticket.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted specialist worker required")
        if not isinstance(attempt_id,str) or not _REVIEW_ID.fullmatch(attempt_id):
            raise ValueError("bounded idempotent video receipt ID required")
        try:
            if consented is not True or video_consent is not True:
                raise PermissionError("explicit independent video consent required")
            if not admission.authorize_chunk(
                ticket,sample=sample,at=at,idle_since=idle_since,
                now_seconds=now_seconds,authorized=True,trusted_worker=True,
                consented=True,article_consent=False,
                video_consent=True,updates_consent=False):
                raise PermissionError("video idle/resource permission not current")
            instant=datetime.fromisoformat(at.replace("Z","+00:00"))
            if instant.tzinfo is None or instant.utcoffset().total_seconds()!=0:
                raise ValueError("canonical UTC video observation required")
            now=int(instant.timestamp())
            _integer(now,"video observation time",0,_MAX_EPOCH)
            url=self._source(ticket.owner,ticket.source_id)
            if url!=ticket.source_url:
                raise ValueError("video ticket and registry URL differ")
            rows,track_sha=self._track(cues)
            rights_digest=self._verify_rights(
                rights,ticket.owner,ticket.source_id,url,track_sha,now)
            self.db.execute("BEGIN IMMEDIATE")
            try:
                chain=self._history(ticket.owner,ticket.source_id)
                for existing in chain:
                    if existing["attempt_id"]==attempt_id:
                        if (existing["track_sha256"]!=track_sha
                            or existing["rights_digest"]!=rights_digest):
                            raise ValueError("conflicting video receipt replay")
                        self.db.execute("COMMIT")
                        return self._summary(existing,replayed=True)
                if len(chain)>=_MAX_HISTORY:
                    raise ValueError("video event history full")
                if chain and now<=chain[-1]["observed_at"]:
                    raise ValueError("video timeline observation must advance")
                previous=chain[-1]["track_sha256"] if chain else None
                change=("new" if previous is None else
                        "unchanged" if previous==track_sha else "changed")
                event={
                    "schema":"skeleton.dragon.video_transcript.v1",
                    "owner":ticket.owner,"source_id":ticket.source_id,
                    "source_url":url,"sequence":len(chain)+1,
                    "attempt_id":attempt_id,"parent_digest":
                        chain[-1]["digest"] if chain else None,
                    "observed_at":now,"track_sha256":track_sha,
                    "rights_digest":rights_digest,"cues":rows,"change":change,
                    "improvements":["(timecoded transcript evidence staged for independent review)"
                                    if change!="unchanged" else
                                    "(unchanged transcript; duplicate learning suppressed)"],
                    "knowledge_approved":False,"training_authorized":False,
                }
                digest=canonical_digest(event)
                self.db.execute(
                    "INSERT INTO dragon_video_cues_v1 VALUES(?,?,?,?,?)",
                    (ticket.owner,ticket.source_id,len(chain)+1,
                     canonical_json(event),digest))
                self.db.execute(
                    "INSERT INTO dragon_video_cue_heads_v1 VALUES(?,?,?,?) "
                    "ON CONFLICT(owner,source) DO UPDATE SET "
                    "sequence=excluded.sequence,digest=excluded.digest",
                    (ticket.owner,ticket.source_id,len(chain)+1,digest))
                self.db.execute("COMMIT")
                return self._summary({**event,"digest":digest},replayed=False)
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        finally:
            # A synchronous transcript stage is finished, not an open video
            # stream: free the real CPU/RAM grant on every successful/denied path.
            admission.stopped(
                ticket,authorized=True,trusted_worker=True,worker_stopped=True)

    @staticmethod
    def _summary(data,*,replayed):
        return {
            "owner":data["owner"],"source_id":data["source_id"],
            "capture_digest":data["digest"],"track_sha256":data["track_sha256"],
            "change":data["change"],"observed_at":data["observed_at"],
            "cues":len(data["cues"]),"replayed":replayed,
            "improvements":data["improvements"],
            "independent_review_required":True,"knowledge_approved":False,
            "training_authorized":False,
        }

    def review_packet(self,owner:str,source_id:str,*,authorized:bool,
                      include_quotes:bool=False)->dict|None:
        _auth(owner,authorized)
        self._source(owner,source_id)
        chain=self._history(owner,source_id)
        if not chain:
            return None
        event=chain[-1]
        return {
            "schema":"skeleton.dragon.video_review.v1",
            "owner":owner,"source_id":source_id,
            "source_url":event["source_url"],
            "capture_digest":event["digest"],
            "track_sha256":event["track_sha256"],
            "observed_at":event["observed_at"],
            "change":event["change"],
            "rights_receipt_digest":event["rights_digest"],
            "timecoded_cues":event["cues"] if include_quotes else [
                {"start_ms":c["start_ms"],"end_ms":c["end_ms"]}
                for c in event["cues"]],
            "independent_review_required":True,
            "training_authorized":False,"xp_awarded":0,
        }
