"""Custodied acquisition history for Dragon technical sources.

Only a trusted, separately authorized crawler may submit a CrawlDocument.
A source must have completed the canonical policy stage with a *current*
permission receipt. This ledger records observed text versions and short
verbatim evidence candidates, never verified knowledge or model weights.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from skeleton.ai.webcrawler.core import CrawlDocument, CrawlPolicy
from skeleton.ai.webcrawler.dragon_crawl_custody import (
    CapturedSource, CustodyPolicy, bind_crawl_evidence,
)
from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_almanac_sequence import AlmanacClaim, SequentialAlmanacWorker
from .dragon_source_catalog import canonical_source_url
from .dragon_technical_source_atlas import CATALOG
from .reviewed_knowledge import _integer

_MAX_TEXT_BYTES = 240_000
_MAX_EVENTS = 64
_MAX_QUOTES = 6
_MAX_QUOTE_CHARS = 240
_WORD = re.compile(r"[a-z0-9]+")
_CAPTURE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,159}\Z")
_SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")


def _passages(text: str, terms: set[str]) -> list[dict]:
    """Extract source-exact spans, with deterministic relevance ordering.

    This is *not* a summarizer. It cannot fabricate a statement or confer
    confidence, and every candidate retains its original character offsets.
    """
    candidates = []
    seen = set()
    for m in re.finditer(r"[^\n.!?]+(?:[.!?]|$)", text):
        start, end = m.span()
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end - 1].isspace(): end -= 1
        if end - start < 24:
            continue
        if end - start > _MAX_QUOTE_CHARS:
            end = start + _MAX_QUOTE_CHARS
        fragment = text[start:end]
        if fragment in seen:
            continue
        seen.add(fragment)
        words = set(_WORD.findall(fragment.lower()))
        overlap = sorted(words & terms)
        score = len(overlap)
        candidates.append((-score, start, {
            "start": start, "end": end, "exact_quote": fragment,
            "matched_topics": overlap, "relevance_hits": score,
            "review_required": True,
        }))
        if len(candidates) >= 3000:
            break
    candidates.sort(key=lambda x: (x[0], x[1]))
    return [p for _, _, p in candidates[:_MAX_QUOTES]]


class DragonSourceCaptures:
    """Bounded, owner-scoped append-only observation and review-candidate log."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical almanac store required")
        self.a = almanacs
        self.db = almanacs.db
        self.worker = SequentialAlmanacWorker(almanacs)
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_technical_captures_v1(
          owner TEXT NOT NULL, source TEXT NOT NULL, sequence INTEGER NOT NULL,
          body TEXT NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(owner,source,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_technical_capture_heads_v1(
          owner TEXT NOT NULL, source TEXT NOT NULL,
          sequence INTEGER NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(owner,source))""")
        self.db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS
          dragon_technical_capture_ids_v1
          ON dragon_technical_captures_v1(owner,source,
              json_extract(body,'$.capture_id'))""")

    def _source(self, owner: str, source_id: str) -> tuple[dict, dict]:
        if not isinstance(source_id, str) or not _SOURCE.fullmatch(source_id):
            raise ValueError("canonical source identity required")
        row = self.db.execute(
            "SELECT body,digest FROM dragon_almanac_sources "
            "WHERE owner=? AND source=?", (owner, source_id)).fetchone()
        if row is None:
            raise ValueError("unregistered source")
        raw, digest = row
        body = json.loads(raw)
        if (canonical_digest(body) != digest
            or body.get("source_id") != source_id
            or body.get("training_authorized") is not False):
            raise ValueError("source registry integrity invalid")
        url = body.get("url")
        if (not isinstance(url,str) or canonical_source_url(url) != url
            or "source-" + sha256(url.encode()).hexdigest() != source_id):
            raise ValueError("noncanonical source identity")
        editorial = [
            item for item in CATALOG if item["url"] == url
        ]
        if len(editorial) != 1:
            raise ValueError("source not in curated technical atlas")
        return body, editorial[0]

    def _policy(self, owner: str, source_id: str, source_url: str,
                *, observed_at: int) -> str:
        row = self.db.execute(
            "SELECT j.stage,j.state,j.input_digest,s.digest FROM dragon_almanac_jobs j "
            "JOIN dragon_almanac_sources s ON s.owner=j.owner AND s.source=j.source "
            "WHERE j.owner=? AND j.source=?", (owner,source_id)).fetchone()
        if row is None:
            raise PermissionError("source has no policy stage")
        stage,state,input_digest,source_digest = row
        if (type(stage) is not int or stage < 1 or stage > 5
            or state not in {"pending","leased","reviewed"}
            or (state=="reviewed")!=(stage==5)):
            raise PermissionError("completed nonblocked policy stage required")
        # Verify every predecessor receipt and the current stage input.
        self.worker._verify_prefix(
            owner,source_id,stage,input_digest,source_url,source_digest,observed_at
        )
        first = self.db.execute(
            "SELECT body,digest FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=0",
            (owner,source_id)).fetchone()
        if first is None:
            raise PermissionError("no source rights receipt")
        policy,digest = first
        payload=json.loads(policy)
        if (canonical_digest(payload) != digest
            or payload.get("stage") != "policy"
            or payload.get("training_authorized") is not False
            or payload.get("evidence",{}).get("expires_at",0) <= observed_at):
            raise PermissionError("policy/rights receipt expired or corrupt")
        return digest

    def _history(self, owner: str, source_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT sequence,body,digest FROM dragon_technical_captures_v1 "
            "WHERE owner=? AND source=? ORDER BY sequence LIMIT ?",
            (owner,source_id,_MAX_EVENTS+1)).fetchall()
        if len(rows)>_MAX_EVENTS:
            raise ValueError("capture history capacity exceeded")
        prev = None
        previous_hash = None
        previous_at = -1
        result=[]
        for i,(seq,raw,digest) in enumerate(rows,1):
            if not isinstance(raw,str) or len(raw.encode("utf-8"))>300_000:
                raise ValueError("capture record exceeds retention budget")
            event=json.loads(raw)
            data=event.get("document",{})
            text=data.get("text")
            if (seq!=i or not isinstance(event,dict)
                or canonical_digest(event)!=digest
                or event.get("owner")!=owner or event.get("source_id")!=source_id
                or event.get("sequence")!=i or event.get("parent_digest")!=prev
                or event.get("observed_at", -1)<=previous_at
                or event.get("training_authorized") is not False
                or event.get("knowledge_approved") is not False
                or not isinstance(text,str)
                or (event.get("response_body_bytes") is not None
                    and (type(event["response_body_bytes"]) is not int
                         or not 1<=event["response_body_bytes"]<=240_000))
                or len(text.encode("utf-8"))>_MAX_TEXT_BYTES
                or sha256(text.encode()).hexdigest()!=event.get("content_sha256")
                or data.get("canonical_url")!=event.get("source_url")):
                raise ValueError("capture chain integrity invalid")
            previous_at=event["observed_at"]
            expected_change=("new" if previous_hash is None else
                             "unchanged" if previous_hash==event["content_sha256"]
                             else "changed")
            if event.get("change")!=expected_change:
                raise ValueError("capture revision classification invalid")
            # Stored exact quotes are reverified against the original text.
            for p in event.get("evidence_candidates",()):
                if (type(p.get("start")) is not int or type(p.get("end")) is not int
                    or not 0<=p["start"]<p["end"]<=len(text)
                    or text[p["start"]:p["end"]]!=p.get("exact_quote")
                    or p.get("review_required") is not True):
                    raise ValueError("non-verbatim evidence candidate")
            result.append({**event,"digest":digest})
            prev=digest;previous_hash=event["content_sha256"]
        head = self.db.execute(
            "SELECT sequence,digest FROM dragon_technical_capture_heads_v1 "
            "WHERE owner=? AND source=?", (owner,source_id)).fetchone()
        if (head is None)!=(not rows):
            raise ValueError("missing capture chain head")
        if rows and head!=(len(rows),prev):
            raise ValueError("capture chain head mismatch")
        return result

    def record(self, owner: str, source_id: str, document: CrawlDocument, *,
               capture_id: str, observed_at: int, authorized: bool,
               trusted_worker: bool, reference_storage_permitted: bool,
               response_body_bytes: int | None = None) -> dict:
        _auth(owner,authorized)
        if trusted_worker is not True or reference_storage_permitted is not True:
            raise PermissionError("trusted worker and explicit reference retention required")
        if not isinstance(capture_id,str) or not _CAPTURE_ID.fullmatch(capture_id):
            raise ValueError("bounded idempotent capture identity required")
        _integer(observed_at,"observation epoch",0,4_102_444_800)
        if response_body_bytes is not None:
            _integer(response_body_bytes,"actual page response bytes",1,240_000)
        if not isinstance(document,CrawlDocument):
            raise TypeError("typed real crawler extraction required")
        if (type(document.fetched_at) not in (int,float)
            or abs(document.fetched_at-observed_at)>300):
            raise ValueError("observation differs from actual fetched timestamp")
        if (not isinstance(document.text,str)
            or not 24<=len(document.text.encode("utf-8"))<=_MAX_TEXT_BYTES):
            raise ValueError("bounded nonempty text required")
        if document.canonical_url!=document.fetched_url:
            raise ValueError("only exact non-redirected source URL is accepted")
        source,seed=self._source(owner,source_id)
        if document.canonical_url!=source["url"]:
            raise ValueError("captured URL differs from canonical registry")
        host=urlsplit(source["url"]).hostname
        bind_crawl_evidence(
            "candidate-"+source_id,
            (CapturedSource(source_id,document),),(),
            authorized=True,
            policy=CustodyPolicy(max_sources=1,max_evidence=1,
                                 max_document_bytes=_MAX_TEXT_BYTES),
            crawl_policy=CrawlPolicy(allowed_hosts=frozenset({host}),
                                     max_depth=0,max_redirects=0),
        )
        self.db.execute("BEGIN IMMEDIATE")
        try:
            receipt=self._policy(owner,source_id,source["url"],observed_at=observed_at)
            chain=self._history(owner,source_id)
            matched=[x for x in chain if x["capture_id"]==capture_id]
            if matched:
                item=matched[0]
                if (item["content_sha256"]!=document.content_hash or
                    item["observed_at"]!=observed_at or
                    item["policy_receipt"]!=receipt or
                    item["response_body_bytes"]!=response_body_bytes):
                    raise ValueError("conflicting capture idempotency identity")
                self.db.execute("COMMIT")
                return self._summary(item,replayed=True)
            if len(chain)>=_MAX_EVENTS:
                raise ValueError("capture history budget exhausted")
            if chain and observed_at<=chain[-1]["observed_at"]:
                raise ValueError("capture observation clock must advance")
            prior=chain[-1]["content_sha256"] if chain else None
            change=("new" if prior is None else
                    "unchanged" if prior==document.content_hash else "changed")
            passages=(_passages(document.text,set(seed["topics"]))
                      if change!="unchanged" else [])
            note=("(first captured revision; independent source review required)"
                  if change=="new" else
                  "(content changed; previous findings require renewed review)"
                  if change=="changed" else
                  "(unchanged reobservation; no duplicate knowledge credited)")
            body={
                "schema":"skeleton.dragon.source_capture.v1",
                "owner":owner,"source_id":source_id,
                "sequence":len(chain)+1,"capture_id":capture_id,
                "parent_digest":chain[-1]["digest"] if chain else None,
                "source_url":source["url"],"observed_at":observed_at,
                "policy_receipt":receipt,
                "response_body_bytes":response_body_bytes,
                "content_sha256":document.content_hash,"change":change,
                "document":{
                    "canonical_url":document.canonical_url,
                    "fetched_url":document.fetched_url,
                    "title":document.title,"text":document.text,
                    "content_type":document.content_type,
                    "fetched_at":document.fetched_at,
                    "source_score":document.source_score,
                    "provenance":dict(document.provenance),
                },
                "evidence_candidates":passages,
                "improvements":[note],
                "evidence_review_required":True,
                "knowledge_approved":False,
                "training_authorized":False,
            }
            digest=canonical_digest(body)
            self.db.execute(
                "INSERT INTO dragon_technical_captures_v1 VALUES(?,?,?,?,?)",
                (owner,source_id,len(chain)+1,canonical_json(body),digest))
            self.db.execute(
                "INSERT INTO dragon_technical_capture_heads_v1 VALUES(?,?,?,?) "
                "ON CONFLICT(owner,source) DO UPDATE SET "
                "sequence=excluded.sequence,digest=excluded.digest",
                (owner,source_id,len(chain)+1,digest))
            self.db.execute("COMMIT")
            return self._summary({**body,"digest":digest},replayed=False)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def _summary(item: dict, *, replayed: bool) -> dict:
        return {
            "owner":item["owner"],"source_id":item["source_id"],
            "sequence":item["sequence"],"capture_digest":item["digest"],
            "content_sha256":item["content_sha256"],"change":item["change"],
            "observed_at":item["observed_at"],
            "evidence_candidates":len(item["evidence_candidates"]),
            "improvements":item["improvements"],"replayed":replayed,
            "independent_review_required":True,"knowledge_approved":False,
            "training_authorized":False,
        }

    def review_packet(self, owner: str, source_id: str, *,
                      authorized: bool, include_text: bool=False) -> dict | None:
        _auth(owner,authorized)
        if type(include_text) is not bool:
            raise ValueError("explicit bounded content visibility required")
        self._source(owner,source_id)
        chain=self._history(owner,source_id)
        if not chain:
            return None
        last=chain[-1]
        pending=last["change"]!="unchanged"
        return {
            "schema":"skeleton.dragon.capture_review_packet.v1",
            "owner":owner,"source_id":source_id,"source_url":last["source_url"],
            "capture_digest":last["digest"],"content_sha256":last["content_sha256"],
            "observed_at":last["observed_at"],"change":last["change"],
            "previous_capture_digest":last["parent_digest"],
            "source_review_needed":pending,
            "candidate_quotes":last["evidence_candidates"] if pending else [],
            "raw_captured_text":last["document"]["text"] if include_text else None,
            "rights_recheck_required":True,
            "independent_claim_verification_required":True,
            "reviewed_knowledge_inserted":False,
            "training_authorized":False,
        }

    def history(self, owner: str, source_id: str, *, authorized: bool) -> tuple[dict,...]:
        _auth(owner,authorized)
        self._source(owner,source_id)
        events=self._history(owner,source_id)
        return tuple(self._summary(x,replayed=False) for x in events)


    def complete_fetch_stage(self, claim: AlmanacClaim, *,
                             capture_digest: str, now: int,
                             authorized: bool, trusted_worker: bool) -> dict:
        """Advance canonical acquisition using an actual staged page response.

        The caller must first own a live, fenced fetch-stage claim from
        SequentialAlmanacWorker; a mere capture event does not advance a job.
        """
        if not isinstance(claim, AlmanacClaim) or claim.stage!="fetch":
            raise ValueError("live canonical fetch-stage claim required")
        _auth(claim.owner,authorized)
        _integer(now,"stage clock",0,4_102_444_800)
        if trusted_worker is not True:
            raise PermissionError("trusted fetch receipt authority required")
        self._source(claim.owner,claim.source_id)
        chain=self._history(claim.owner,claim.source_id)
        if not chain or chain[-1]["digest"]!=capture_digest:
            raise ValueError("current non-stale captured revision required")
        latest=chain[-1]
        if (latest["source_url"]!=claim.url
            or latest["observed_at"]>now
            or now-latest["observed_at"]>300
            or type(latest["response_body_bytes"]) is not int):
            raise ValueError("current worker-captured HTTP response required")
        output=latest["content_sha256"]
        evidence={
            "url":claim.url,"input_digest":claim.input_digest,
            "output_digest":output,"http_status":200,
            "redirects_rechecked":True,
            "body_bytes":latest["response_body_bytes"],
            "capture_digest":latest["digest"],
            "content_sha256":output,
            "derived_claims_are_unreviewed":True,
        }
        receipt=self.worker.finish(claim,now=now,
                    output_digest=output,evidence=evidence,
                    authorized=True,trusted_worker=True)
        return {"stage":"fetch","receipt_digest":receipt,
                "capture_digest":capture_digest,
                "next_stage":"extract","reviewed_knowledge_added":0,
                "training_authorized":False}

    def complete_extract_stage(self, claim: AlmanacClaim, *,
                               capture_digest: str, now: int,
                               authorized: bool, trusted_worker: bool) -> dict:
        """Promote exact spans to an extract receipt, NOT approved claims."""
        if not isinstance(claim, AlmanacClaim) or claim.stage!="extract":
            raise ValueError("live canonical extract-stage claim required")
        _auth(claim.owner,authorized)
        _integer(now,"stage clock",0,4_102_444_800)
        if trusted_worker is not True:
            raise PermissionError("trusted extract receipt authority required")
        chain=self._history(claim.owner,claim.source_id)
        if not chain or chain[-1]["digest"]!=capture_digest:
            raise ValueError("current non-stale captured revision required")
        current=chain[-1]
        if (current["source_url"]!=claim.url
            or current["content_sha256"]!=claim.input_digest
            or current["observed_at"]>now):
            raise ValueError("extract claim not bound to captured text")
        spans=[[x["start"],x["end"],x["exact_quote"]]
               for x in current["evidence_candidates"]]
        span_digest=canonical_digest({
            "content":current["content_sha256"],"spans":spans
        })
        output=canonical_digest({"schema":"dragon.unreviewed_extract.v1",
                                 "source":claim.source_id,
                                 "capture":capture_digest,
                                 "span_map":span_digest})
        evidence={"url":claim.url,"input_digest":claim.input_digest,
                  "output_digest":output,
                  "parser_version":"dragon-exactspan-v1",
                  "span_map_digest":span_digest,
                  "capture_digest":capture_digest,
                  "derived_claims_are_unreviewed":True}
        receipt=self.worker.finish(claim,now=now,output_digest=output,
                                   evidence=evidence,authorized=True,
                                   trusted_worker=True)
        return {"stage":"extract","receipt_digest":receipt,
                "span_map_digest":span_digest,"candidate_quotes":len(spans),
                "next_stage":"analyze","reviewed_knowledge_added":0,
                "training_authorized":False}
