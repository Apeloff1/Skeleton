"""Idle-only RSS update queue with signed fetched-snapshot custody.

The fetcher is elsewhere: a trusted, rights-approved transport obtains XML.
An Updates worker must pass the original admission.authorize_chunk check
at ingestion time; no standalone network access or source license is granted.
"""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import nullcontext
from hashlib import sha256
from datetime import datetime,timezone
import re,sqlite3
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from skeleton.ai.game_builder.contracts import canonical_digest,canonical_json
from .dragon_nest_worker_admission import HatchlingWorkerTicket,DragonNestWorkerAdmission

HEX=re.compile(r"[0-9a-f]{64}\Z")
MAX_XML=1_000_000
MAX_ITEMS=80

@dataclass(frozen=True)
class SignedRssSnapshot:
    owner:str
    source_id:str
    feed_url:str
    body_sha256:str
    issued_at:int
    expires_at:int
    issuer:str
    key_id:str
    rights_receipt_digest:str
    signature_hex:str

    def body(self):
        return {
            "schema":"skeleton.dragon.rss_fetch_receipt.v1",
            "owner":self.owner,"source_id":self.source_id,
            "feed_url":self.feed_url,"body_sha256":self.body_sha256,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
            "issuer":self.issuer,"key_id":self.key_id,
            "rights_receipt_digest":self.rights_receipt_digest,
        }


def _parse_feed(raw:bytes,source_url:str)->tuple[dict,...]:
    if (type(raw) is not bytes or len(raw)>MAX_XML or not raw.strip()
        or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper()):
        raise ValueError("RSS XML size/DTD/ENTITY refused")
    try:
        root=ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("invalid RSS/Atom XML") from exc
    kind=root.tag.rsplit("}",1)[-1].lower()
    if kind=="rss":
        nodes=root.findall("./channel/item")
        def child(n,tag):return (n.findtext(tag) or "").strip()
    elif kind=="feed":
        ns="{http://www.w3.org/2005/Atom}"
        nodes=root.findall(ns+"entry")
        def child(n,tag):
            if tag=="link":
                link=n.find(ns+"link")
                return link.get("href","").strip() if link is not None else ""
            return (n.findtext(ns+tag) or "").strip()
    else:
        raise ValueError("supported RSS or Atom feed required")
    if len(nodes)>MAX_ITEMS:
        raise ValueError("RSS entry budget exceeded")
    out=[]
    seen=set()
    for node in nodes:
        title=child(node,"title")[:240]
        link=child(node,"link")
        guid=child(node,"guid") if kind=="rss" else child(node,"id")
        published=child(node,"pubDate") if kind=="rss" else child(node,"updated")
        if (not title or len(title)>240 or not link.startswith("https://")
            or len(link)>2048 or not urlsplit(link).hostname
            or len(guid)>400 or len(published)>120):
            raise ValueError("unsafe RSS entry metadata")
        identity=canonical_digest({"url":link,"guid":guid or link})
        if identity in seen:continue
        seen.add(identity)
        out.append({"item_digest":identity,"title":title,"url":link,
                    "published":published[:120],
                    "feed_source_url":source_url,
                    "review_status":"unverified_update_lead",
                    "independent_fact_review_required":True,
                    "rights_for_entry_not_established":True})
    return tuple(out)


class DragonRssUpdateQueue:
    def __init__(self,db:sqlite3.Connection):
        if not isinstance(db,sqlite3.Connection):
            raise TypeError("canonical operator-owned SQLite queue required")
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_rss_updates_v1(
            owner TEXT NOT NULL,source_id TEXT NOT NULL,item_digest TEXT NOT NULL,
            payload TEXT NOT NULL,payload_digest TEXT NOT NULL,seen_at INTEGER NOT NULL,
            PRIMARY KEY(owner,source_id,item_digest))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_rss_poll_v1(
            owner TEXT NOT NULL,source_id TEXT NOT NULL,xml_sha TEXT NOT NULL,
            observed_at INTEGER NOT NULL,receipt_digest TEXT NOT NULL,
            PRIMARY KEY(owner,source_id,xml_sha))""")

    def ingest(self,ticket:HatchlingWorkerTicket,admission:DragonNestWorkerAdmission,
               xml:bytes,receipt:SignedRssSnapshot,*,reviewer_public_key:bytes,
               trusted_issuer:str,key_id:str,now:int,
               admission_kwargs:dict,authorized:bool,
               transaction_managed:bool=False)->dict:
        if type(transaction_managed) is not bool:
            raise TypeError("trusted transaction ownership required")
        if (authorized is not True or not isinstance(ticket,HatchlingWorkerTicket)
            or ticket.lane!="updates" or not isinstance(admission,DragonNestWorkerAdmission)
            or not isinstance(receipt,SignedRssSnapshot)):
            raise PermissionError("trusted Updates hatchling required")
        if (type(now) is not int or now<0
            or type(reviewer_public_key) is not bytes or len(reviewer_public_key)!=32
            or receipt.owner!=ticket.owner or receipt.source_id!=ticket.source_id
            or receipt.feed_url!=ticket.source_url
            or receipt.issuer!=trusted_issuer or receipt.key_id!=key_id
            or receipt.issued_at>now or now>=receipt.expires_at
            or receipt.expires_at-receipt.issued_at>3600
            or not HEX.fullmatch(receipt.body_sha256)
            or not HEX.fullmatch(receipt.rights_receipt_digest)
            or receipt.body_sha256!=sha256(xml).hexdigest()):
            raise PermissionError("RSS signed snapshot scope or current rights absent")
        try:
            Ed25519PublicKey.from_public_bytes(reviewer_public_key).verify(
                bytes.fromhex(receipt.signature_hex),
                canonical_json(receipt.body()).encode())
        except (InvalidSignature,ValueError,TypeError) as exc:
            raise PermissionError("RSS external authorization receipt invalid") from exc
        if (type(admission_kwargs) is not dict or
            not admission.authorize_chunk(ticket,**admission_kwargs)):
            raise PermissionError("Updates hatchling must still be idle and admitted")
        entries=_parse_feed(xml,ticket.source_url)
        # Verify admission again BEFORE durable effects: a foreground
        # request may preempt the worker during potentially costly parsing.
        if not admission.authorize_chunk(ticket,**admission_kwargs):
            raise PermissionError("Updates idle permission revoked before commit")
        receipt_digest=canonical_digest(receipt.body())
        with (nullcontext() if transaction_managed else self.db):
            row=self.db.execute(
                "SELECT receipt_digest FROM dragon_rss_poll_v1 "
                "WHERE owner=? AND source_id=? AND xml_sha=?",
                (ticket.owner,ticket.source_id,receipt.body_sha256)).fetchone()
            if row is not None and row[0]!=receipt_digest:
                raise ValueError("conflicting signed poll receipt")
            if row is None:
                self.db.execute(
                    "INSERT INTO dragon_rss_poll_v1 VALUES(?,?,?,?,?)",
                    (ticket.owner,ticket.source_id,receipt.body_sha256,
                     now,receipt_digest))
            added=0
            for item in entries:
                payload=canonical_json(item)
                cur=self.db.execute(
                    "INSERT OR IGNORE INTO dragon_rss_updates_v1 VALUES(?,?,?,?,?,?)",
                    (ticket.owner,ticket.source_id,item["item_digest"],
                     payload,canonical_digest(item),now))
                added+=cur.rowcount
        return {"schema":"skeleton.dragon.rss_update_ingest.v1",
                "owner":ticket.owner,"source_id":ticket.source_id,
                "feed_snapshot_digest":receipt.body_sha256,
                "items_seen":len(entries),"new_unverified_leads":added,
                "idempotent":added==0,
                "network_requests":0,"worker_ticket_rechecked":True,
                "rights_granted":False,"knowledge_approved":False,
                "shadow_weights_promoted":False}

    def pending(self,owner:str,*,authorized:bool,limit:int=60)->dict:
        if authorized is not True or not isinstance(owner,str) or not owner:
            raise PermissionError("tenant access required")
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("bounded queue page required")
        rows=self.db.execute(
            "SELECT payload,payload_digest,source_id,seen_at "
            "FROM dragon_rss_updates_v1 WHERE owner=? "
            "ORDER BY seen_at DESC,source_id,item_digest LIMIT ?",
            (owner,limit)).fetchall()
        items=[]
        import json
        for payload,digest,source,seen in rows:
            obj=json.loads(payload)
            if canonical_json(obj)!=payload or canonical_digest(obj)!=digest:
                raise ValueError("RSS custody tampering detected")
            items.append({**obj,"source_id":source,"observed_at":seen})
        return {"schema":"skeleton.dragon.rss_updates_queue.v1",
                "owner":owner,"entries":items,"count":len(items),
                "read_only":True,"all_items_require_independent_review":True,
                "network_requests":0,"training_authorized":False}
