"""Short-lived, revocable source-specific research capture permits.

The issuer must authenticate a human reviewer and independently verify site
terms/robots/reference-use evidence OUTSIDE this module. Boolean assertions
are never remote permission evidence by themselves. Signed grants only let an
already-authorized local worker use its existing policy/source/resource gates.
Neither this API nor an HMAC can create copyright or site access rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from secrets import token_hex

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_technical_source_captures import DragonSourceCaptures
from .reviewed_knowledge import _id, _integer

_MAX_EPOCH=4_102_444_800
_ACTION="reference_capture"


@dataclass(frozen=True,slots=True)
class SourceCaptureGrant:
    owner: str
    source_id: str
    source_url: str
    policy_receipt: str
    source_registry_digest: str
    evidence_digest: str
    reviewer: str
    issuer: str
    key_id: str
    issued_at: int
    expires_at: int
    nonce: str
    signature: str
    action: str=_ACTION

    def body(self) -> dict:
        return {
            "schema":"skeleton.dragon.source_capture_grant.v1",
            "owner":self.owner,"source_id":self.source_id,
            "source_url":self.source_url,
            "policy_receipt":self.policy_receipt,
            "source_registry_digest":self.source_registry_digest,
            "evidence_digest":self.evidence_digest,
            "reviewer":self.reviewer,"issuer":self.issuer,
            "key_id":self.key_id,"issued_at":self.issued_at,
            "expires_at":self.expires_at,"nonce":self.nonce,
            "action":self.action,
            "model_training_authorized":False,
            "rights_granted_by_token":False,
        }

    @property
    def digest(self)->str:
        return canonical_digest({**self.body(),"signature":self.signature})


class DragonSourcePermissionAuthority:
    """A *sealed-server-only* HMAC issuer with durable grant/revocation custody."""

    def __init__(self,captures:DragonSourceCaptures,*,key:bytes,
                 issuer:str,key_id:str):
        if not isinstance(captures,DragonSourceCaptures):
            raise TypeError("canonical source-capture authority required")
        if type(key) is not bytes or len(key)<32:
            raise ValueError("separate source permission key of 256 bits required")
        _id(issuer,"permission issuer");_id(key_id,"permission key identity")
        self.captures=captures
        self.db=captures.db
        self.key=key
        self.issuer=issuer
        self.key_id=key_id
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_grants_v1(
            owner TEXT NOT NULL, grant_digest TEXT NOT NULL,
            body TEXT NOT NULL, issued_at INTEGER NOT NULL,
            PRIMARY KEY(owner,grant_digest))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_pilot_control_events_v1(
            owner TEXT NOT NULL, sequence INTEGER NOT NULL,
            body TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(owner,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_pilot_control_heads_v1(
            owner TEXT PRIMARY KEY, sequence INTEGER NOT NULL,
            digest TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_source_grant_revocations_v1(
            owner TEXT NOT NULL, grant_digest TEXT NOT NULL,
            at INTEGER NOT NULL, reason TEXT NOT NULL,
            PRIMARY KEY(owner,grant_digest))""")

    def _mac(self,body:dict)->str:
        return hmac.new(self.key,canonical_json(body).encode(),sha256).hexdigest()

    def _scope(self,owner:str,source_id:str,now:int):
        source,_=self.captures._source(owner,source_id)
        row=self.db.execute(
            "SELECT digest FROM dragon_almanac_sources "
            "WHERE owner=? AND source=?",(owner,source_id)).fetchone()
        if row is None:
            raise ValueError("no canonical source snapshot")
        policy=self.captures._policy(
            owner,source_id,source["url"],observed_at=now)
        evidence=self.db.execute(
            "SELECT body FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=0",
            (owner,source_id)).fetchone()
        if evidence is None:
            raise PermissionError("missing canonical permission receipt")
        expiry=json.loads(evidence[0])["evidence"]["expires_at"]
        return source,row[0],policy,expiry

    def issue(self,owner:str,source_id:str,*,reviewer:str,evidence_digest:str,
              now:int,expires_at:int,authorized:bool,trusted_issuer:bool,
              identity_verified:bool,external_rights_verified:bool,
              robots_verified:bool,terms_verified:bool,
              reference_retention_verified:bool)->SourceCaptureGrant:
        _auth(owner,authorized)
        if (trusted_issuer is not True or identity_verified is not True
            or external_rights_verified is not True
            or robots_verified is not True or terms_verified is not True
            or reference_retention_verified is not True):
            raise PermissionError("independent external rights reviewer attestation required")
        _id(reviewer,"source policy reviewer")
        if reviewer==self.issuer:
            raise PermissionError("reviewer must differ from token issuer")
        if (not isinstance(evidence_digest,str) or len(evidence_digest)!=64
            or any(c not in "0123456789abcdef" for c in evidence_digest)):
            raise ValueError("exact external rights-evidence hash required")
        _integer(now,"grant issue time",0,_MAX_EPOCH)
        _integer(expires_at,"grant expiry",now+1,_MAX_EPOCH)
        if expires_at>now+3600:
            raise ValueError("reference-capture grant cannot exceed one hour")
        # Scope to a currently accepted *external* policy receipt. The
        # matching text must not be replaced after grant issue.
        source,registry_digest,policy,policy_expires=self._scope(
            owner,source_id,now)
        if expires_at>policy_expires:
            raise ValueError("grant cannot outlive reviewed robots/rights receipt")
        body={
            "schema":"skeleton.dragon.source_capture_grant.v1",
            "owner":owner,"source_id":source_id,
            "source_url":source["url"],
            "policy_receipt":policy,
            "source_registry_digest":registry_digest,
            "evidence_digest":evidence_digest,
            "reviewer":reviewer,"issuer":self.issuer,
            "key_id":self.key_id,"issued_at":now,"expires_at":expires_at,
            "nonce":token_hex(16),"action":_ACTION,
            "model_training_authorized":False,
            "rights_granted_by_token":False,
        }
        grant=SourceCaptureGrant(
            owner,source_id,source["url"],policy,registry_digest,
            evidence_digest,reviewer,self.issuer,self.key_id,
            now,expires_at,body["nonce"],self._mac(body))
        self.db.execute(
            "INSERT INTO dragon_source_grants_v1 VALUES(?,?,?,?)",
            (owner,grant.digest,canonical_json({**body,"signature":grant.signature}),now))
        return grant

    def verify(self,grant:SourceCaptureGrant,*,owner:str,source_id:str,
               now:int,authorized:bool)->str:
        _auth(owner,authorized)
        _integer(now,"source grant verification clock",0,_MAX_EPOCH)
        if not isinstance(grant,SourceCaptureGrant):
            raise PermissionError("typed signed source grant required")
        if (grant.owner!=owner or grant.source_id!=source_id
            or type(grant.nonce) is not str
            or type(grant.signature) is not str
            or grant.action!=_ACTION or grant.issuer!=self.issuer
            or grant.key_id!=self.key_id
            or not grant.issued_at<=now<grant.expires_at
            or grant.expires_at>grant.issued_at+3600
            or len(grant.nonce)!=32):
            raise PermissionError("source permit identity or expiry invalid")
        if not self.control_state(owner,authorized=True)["enabled"]:
            raise PermissionError("owner pilot kill switch disabled")
        if not hmac.compare_digest(grant.signature,self._mac(grant.body())):
            raise PermissionError("source permit signature invalid")
        record=self.db.execute(
            "SELECT body FROM dragon_source_grants_v1 "
            "WHERE owner=? AND grant_digest=?",(owner,grant.digest)).fetchone()
        if record is None or record[0]!=canonical_json({
            **grant.body(),"signature":grant.signature}):
            raise PermissionError("source permit was not issued by this ledger")
        if self.db.execute(
            "SELECT 1 FROM dragon_source_grant_revocations_v1 "
            "WHERE owner=? AND grant_digest=?",(owner,grant.digest)).fetchone():
            raise PermissionError("source permit revoked")
        source,registry_digest,policy,_=self._scope(owner,source_id,now)
        if (source["url"]!=grant.source_url
            or registry_digest!=grant.source_registry_digest
            or policy!=grant.policy_receipt):
            raise PermissionError("source or policy changed after attestation")
        return grant.digest

    def revoke(self,grant:SourceCaptureGrant,*,now:int,reason:str,
               authorized:bool,trusted_issuer:bool)->dict:
        if trusted_issuer is not True:
            raise PermissionError("independent issuer revocation required")
        if not isinstance(grant,SourceCaptureGrant):
            raise PermissionError("typed issued grant required for revocation")
        _auth(grant.owner,authorized)
        _integer(now,"revocation clock",grant.issued_at,_MAX_EPOCH)
        if not isinstance(reason,str) or not 1<=len(reason)<=200:
            raise ValueError("bounded revocation reason required")
        if (grant.issuer!=self.issuer or grant.key_id!=self.key_id
            or not hmac.compare_digest(grant.signature,self._mac(grant.body()))):
            raise PermissionError("foreign or forged grant cannot be revoked")
        record=self.db.execute(
            "SELECT 1 FROM dragon_source_grants_v1 "
            "WHERE owner=? AND grant_digest=?",
            (grant.owner,grant.digest)).fetchone()
        if record is None:
            raise PermissionError("grant not issued by this authority")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO dragon_source_grant_revocations_v1 VALUES(?,?,?,?)",
                (grant.owner,grant.digest,now,reason))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"status":"revoked","grant_digest":grant.digest,
                "training_authorized":False,"network_requests":0}


    def audit(self,owner:str,*,now:int,authorized:bool,
              limit:int=100)->dict:
        """Read-only signed permit census. Never implies site rights or success."""
        _auth(owner,authorized)
        _integer(now,"source grant audit clock",0,_MAX_EPOCH)
        _integer(limit,"source grant audit limit",1,100)
        rows=self.db.execute(
            "SELECT grant_digest,body FROM dragon_source_grants_v1 "
            "WHERE owner=? ORDER BY issued_at,grant_digest LIMIT ?",
            (owner,limit+1)).fetchall()
        if len(rows)>limit:
            raise ValueError("bounded source grant audit page exceeded")
        items=[]
        for digest,raw in rows:
            if type(raw) is not str or len(raw.encode())>4096:
                raise ValueError("stored signed source grant oversized")
            payload=json.loads(raw)
            if (not isinstance(payload,dict)
                or canonical_digest(payload)!=digest
                or payload.get("owner")!=owner
                or payload.get("issuer")!=self.issuer
                or payload.get("key_id")!=self.key_id):
                raise ValueError("stored source grant integrity invalid")
            unsigned={k:v for k,v in payload.items() if k!="signature"}
            signature=payload.get("signature")
            if (type(signature) is not str
                or not hmac.compare_digest(signature,self._mac(unsigned))):
                raise ValueError("stored source grant signature invalid")
            revoked=self.db.execute(
                "SELECT at,reason FROM dragon_source_grant_revocations_v1 "
                "WHERE owner=? AND grant_digest=?",(owner,digest)).fetchone()
            if revoked:
                state="revoked"
            elif now>=payload["expires_at"]:
                state="expired"
            else:
                # An apparently unexpired token can still have a superseded
                # site/terms/robots policy. No network checks take place.
                try:
                    _,reg,policy,_=self._scope(
                        owner,payload["source_id"],now)
                    state=("live_scope" if
                           reg==payload["source_registry_digest"] and
                           policy==payload["policy_receipt"]
                           else "superseded_policy")
                except (PermissionError,ValueError):
                    state="policy_not_current"
            items.append({
                "grant_digest":digest,"source_id":payload["source_id"],
                "reviewer":payload["reviewer"],
                "issued_at":payload["issued_at"],
                "expires_at":payload["expires_at"],
                "state":state,
                "training_authorized":False,
            })
        return {
            "schema":"skeleton.dragon.source_grant_audit.v1",
            "owner":owner,"grants":items,
            "active_scope_count":sum(x["state"]=="live_scope" for x in items),
            "revoked_count":sum(x["state"]=="revoked" for x in items),
            "network_requests":0,"model_training_authorized":False,
        }


    def _control_events(self,owner:str)->list[dict]:
        rows=self.db.execute(
            "SELECT sequence,body,digest FROM "
            "dragon_source_pilot_control_events_v1 "
            "WHERE owner=? ORDER BY sequence LIMIT 257",(owner,)
        ).fetchall()
        if len(rows)>256:
            raise ValueError("pilot control audit capacity exhausted")
        records=[];prev=None
        for i,(seq,raw,digest) in enumerate(rows):
            if type(raw) is not str or len(raw.encode())>2000:
                raise ValueError("corrupt owner pilot control event")
            event=json.loads(raw)
            if (not isinstance(event,dict)
                or seq!=i or event.get("sequence")!=i
                or event.get("owner")!=owner
                or event.get("parent_digest")!=prev
                or canonical_digest(event)!=digest
                or event.get("schema")!="skeleton.dragon.pilot_control.v1"
                or type(event.get("enabled")) is not bool
                or type(event.get("at")) is not int
                or (records and event["at"]<records[-1]["at"])
                or event.get("training_authorized") is not False):
                raise ValueError("owner pilot control lineage corrupt")
            records.append({**event,"digest":digest})
            prev=digest
        head=self.db.execute(
            "SELECT sequence,digest FROM dragon_source_pilot_control_heads_v1 "
            "WHERE owner=?",(owner,)).fetchone()
        if bool(head)!=bool(records):
            raise ValueError("pilot control head missing or forged")
        if records and head!=(records[-1]["sequence"],records[-1]["digest"]):
            raise ValueError("pilot control head does not match append-only events")
        return records

    def control_state(self,owner:str,*,authorized:bool)->dict:
        """Default OFF even when source metadata and signed grants exist."""
        _auth(owner,authorized)
        rows=self._control_events(owner)
        return {
            "schema":"skeleton.dragon.pilot_control_status.v1",
            "owner":owner,
            "enabled":rows[-1]["enabled"] if rows else False,
            "generation":len(rows),
            "head_digest":rows[-1]["digest"] if rows else None,
            "network_requests":0,"model_training_authorized":False,
        }

    def set_pilot_enabled(self,owner:str,*,enabled:bool,now:int,
                          expected_head_digest:str|None,reason:str,
                          authorized:bool,trusted_issuer:bool,
                          owner_consent_verified:bool=False)->dict:
        """Only the sealed issuer may change the cross-process kill switch.

        Never infer owner consent from a network source or a source grant.
        Disabled is the absence/default state; disabling needs no new consent.
        """
        _auth(owner,authorized)
        _integer(now,"pilot control clock",0,_MAX_EPOCH)
        if trusted_issuer is not True:
            raise PermissionError("trusted source pilot issuer required")
        if type(enabled) is not bool:
            raise ValueError("explicit pilot enabled flag required")
        if enabled and owner_consent_verified is not True:
            raise PermissionError("independently verified pilot owner consent required")
        if not isinstance(reason,str) or not 1<=len(reason)<=160:
            raise ValueError("bounded owner pilot control reason required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._control_events(owner)
            prev=rows[-1]["digest"] if rows else None
            if expected_head_digest!=prev:
                raise ValueError("stale pilot kill-switch compare-and-swap")
            if len(rows)>=256:
                raise ValueError("pilot control event retention capacity reached")
            if rows and now<rows[-1]["at"]:
                raise ValueError("pilot control clock rollback")
            if rows and rows[-1]["enabled"]==enabled:
                raise ValueError("pilot control requires a real state transition")
            event={
                "schema":"skeleton.dragon.pilot_control.v1",
                "owner":owner,"sequence":len(rows),
                "parent_digest":prev,"enabled":enabled,
                "at":now,"reason":reason,
                "training_authorized":False,
            }
            digest=canonical_digest(event)
            self.db.execute(
                "INSERT INTO dragon_source_pilot_control_events_v1 "
                "VALUES(?,?,?,?)",
                (owner,len(rows),canonical_json(event),digest))
            self.db.execute(
                "INSERT INTO dragon_source_pilot_control_heads_v1 "
                "VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET "
                "sequence=excluded.sequence,digest=excluded.digest",
                (owner,len(rows),digest))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "owner":owner,"enabled":enabled,"head_digest":digest,
            "generation":len(rows)+1,
            "network_requests":0,"training_authorized":False,
        }
