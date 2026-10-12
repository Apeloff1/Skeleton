"""Signed canary exposure and independent post-deployment regression watch.

Only verified current/previous retrieval generations from DragonDurableWeightVault
are eligible. A stable cohort digest selects the actual routed version.
An independent assessor signs paired outcomes before they affect exposure.
A regression halts candidate exposure automatically, without rewriting model
parameters or silently promoting a canary to all traffic.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import sqlite3
from threading import RLock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from skeleton.ai.game_builder.contracts import canonical_json, canonical_digest
from .dragon_weight_deployment_vault import DragonDurableWeightVault

HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_SAMPLES = 1000


@dataclass(frozen=True)
class SignedCanaryPlan:
    owner: str
    candidate_digest: str
    control_digest: str
    traffic_percent: int
    min_pairs: int
    max_latency_ratio: float
    operator: str
    operator_key_id: str
    issued_at: int
    expires_at: int
    signature_hex: str

    def body(self):
        return {
            "schema": "skeleton.jeeves.canary_plan.v1",
            "owner": self.owner,
            "candidate_digest": self.candidate_digest,
            "control_digest": self.control_digest,
            "traffic_percent": self.traffic_percent,
            "min_pairs": self.min_pairs,
            "max_latency_ratio": self.max_latency_ratio,
            "operator": self.operator,
            "operator_key_id": self.operator_key_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SignedCanaryPair:
    owner: str
    plan_digest: str
    case_digest: str
    task_family: str
    source_group_digest: str
    baseline_correct: bool
    candidate_correct: bool
    baseline_latency_ms: int
    candidate_latency_ms: int
    assessor: str
    assessor_key_id: str
    observed_at: int
    signature_hex: str

    def body(self):
        return {
            "schema": "skeleton.jeeves.canary_pair.v1",
            "owner": self.owner, "plan_digest": self.plan_digest,
            "case_digest": self.case_digest, "task_family": self.task_family,
            "source_group_digest": self.source_group_digest,
            "baseline_correct": self.baseline_correct,
            "candidate_correct": self.candidate_correct,
            "baseline_latency_ms": self.baseline_latency_ms,
            "candidate_latency_ms": self.candidate_latency_ms,
            "assessor": self.assessor, "assessor_key_id": self.assessor_key_id,
            "observed_at": self.observed_at,
        }


def _verify(pub: bytes, signature: str, body: dict):
    if type(pub) is not bytes or len(pub)!=32:
        raise ValueError("independent Ed25519 key required")
    try:
        raw=bytes.fromhex(signature)
        if len(raw)!=64:
            raise ValueError("Ed25519 signature length invalid")
        Ed25519PublicKey.from_public_bytes(pub).verify(
            raw,canonical_json(body).encode())
    except (ValueError,TypeError,InvalidSignature) as exc:
        raise PermissionError("untrusted canary observation signature") from exc


class DragonWeightCanary:
    """Durable signed rollout plan and paired regression custody."""

    def __init__(self, db: sqlite3.Connection, *, vault: DragonDurableWeightVault,
                 plan: SignedCanaryPlan, operator_public_key: bytes,
                 operator: str, operator_key_id: str,
                 assessor_public_key: bytes, assessor: str,
                 assessor_key_id: str, signing_key: bytes):
        if (not isinstance(db,sqlite3.Connection)
            or not isinstance(vault,DragonDurableWeightVault)
            or not isinstance(plan,SignedCanaryPlan)
            or type(operator) is not str or not operator
            or type(operator_key_id) is not str or not operator_key_id
            or type(signing_key) is not bytes or len(signing_key)<32
            or type(assessor) is not str or not assessor
            or type(assessor_key_id) is not str or not assessor_key_id
            or type(assessor_public_key) is not bytes or len(assessor_public_key)!=32):
            raise ValueError("trusted canary custody and evaluator required")
        if (plan.operator!=operator or plan.operator_key_id!=operator_key_id
            or plan.owner!=vault.owner
            or any(type(x) is not str or not HEX.fullmatch(x)
                   for x in (plan.candidate_digest,plan.control_digest))
            or plan.candidate_digest==plan.control_digest
            or type(plan.traffic_percent) is not int
            or not 1<=plan.traffic_percent<=25
            or type(plan.min_pairs) is not int
            or not 12<=plan.min_pairs<=MAX_SAMPLES
            or type(plan.max_latency_ratio) not in (float,int)
            or not 1<=plan.max_latency_ratio<=1.15
            or type(plan.issued_at) is not int
            or type(plan.expires_at) is not int
            or not plan.issued_at<plan.expires_at<=plan.issued_at+7*86400):
            raise ValueError("bounded signed canary plan invalid")
        _verify(operator_public_key,plan.signature_hex,plan.body())
        self.db=db
        self.vault=vault
        self.plan=plan
        self.plan_digest=canonical_digest(plan.body())
        self.signing_key=signing_key
        self.assessor_public_key=assessor_public_key
        self.assessor=assessor
        self.assessor_key_id=assessor_key_id
        self._lock=RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_canary_plans_v1(
            owner TEXT NOT NULL, plan_digest TEXT NOT NULL,
            plan_json TEXT NOT NULL, signature_hex TEXT NOT NULL,
            mac TEXT NOT NULL, PRIMARY KEY(owner,plan_digest))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_canary_pairs_v1(
            owner TEXT NOT NULL, plan_digest TEXT NOT NULL,
            case_digest TEXT NOT NULL, payload TEXT NOT NULL,
            signature_hex TEXT NOT NULL, mac TEXT NOT NULL,
            PRIMARY KEY(owner,plan_digest,case_digest))""")
        self._init_plan()

    def _mac(self, domain: str, body: dict):
        return hmac.new(self.signing_key,
                        (domain+":"+canonical_json(body)).encode(),
                        hashlib.sha256).hexdigest()

    def _init_plan(self):
        document=canonical_json(self.plan.body())
        mac=self._mac("plan",{"body":document,
                              "signature":self.plan.signature_hex})
        with self._lock:
            row=self.db.execute(
                "SELECT plan_json,signature_hex,mac FROM dragon_canary_plans_v1 "
                "WHERE owner=? AND plan_digest=?",
                (self.plan.owner,self.plan_digest)).fetchone()
            if row is None:
                self.db.execute(
                    "INSERT INTO dragon_canary_plans_v1 VALUES(?,?,?,?,?)",
                    (self.plan.owner,self.plan_digest,document,
                     self.plan.signature_hex,mac))
                self.db.commit()
            elif row!=(document,self.plan.signature_hex,mac):
                raise ValueError("stored signed canary plan altered")

    def _verify_binding(self, now: int):
        if type(now) is not int or now<0:
            raise ValueError("bounded current epoch required")
        if not self.plan.issued_at<=now<self.plan.expires_at:
            raise PermissionError("canary plan not current")
        # The vault checks the COMPLETE hash chain, even after restart.
        with self.vault._lock:
            _,_,_,events=self.vault._verify()
        if (len(events)<2
            or events[-1]["index_digest"]!=self.plan.candidate_digest
            or events[-2]["index_digest"]!=self.plan.control_digest
            or now>=events[-1]["expires_at"]
            or now>=events[-2]["expires_at"]):
            raise PermissionError("canary not bound to two live approved index versions")

    def audit(self, *, now: int) -> dict:
        with self._lock:
            document=canonical_json(self.plan.body())
            mac=self._mac("plan",{"body":document,"signature":self.plan.signature_hex})
            row=self.db.execute(
                "SELECT plan_json,signature_hex,mac FROM dragon_canary_plans_v1 "
                "WHERE owner=? AND plan_digest=?",
                (self.plan.owner,self.plan_digest)).fetchone()
            if row!=(document,self.plan.signature_hex,mac):
                raise ValueError("signed canary plan custody invalid")
            rows=self.db.execute(
                "SELECT case_digest,payload,signature_hex,mac "
                "FROM dragon_canary_pairs_v1 WHERE owner=? AND plan_digest=? "
                "ORDER BY case_digest",
                (self.plan.owner,self.plan_digest)).fetchall()
            if len(rows)>MAX_SAMPLES:
                raise ValueError("unbounded canary evidence backlog")
            cases=set()
            pairs=[]
            for ident,raw,sig,stored_mac in rows:
                try:
                    payload=json.loads(raw)
                except (TypeError,ValueError) as exc:
                    raise ValueError("invalid canary trial custody") from exc
                if (not isinstance(payload,dict)
                    or canonical_json(payload)!=raw
                    or ident!=payload.get("case_digest")
                    or ident in cases
                    or not hmac.compare_digest(stored_mac,self._mac(
                        "pair",{"body":raw,"signature":sig}))):
                    raise ValueError("canary trial custody corrupted")
                pair=SignedCanaryPair(**{**payload,"signature_hex":sig,
                    "owner":payload["owner"],
                    "plan_digest":payload["plan_digest"]})
                self._validate_pair(pair,now,check_fresh=False)
                cases.add(ident)
                pairs.append(pair)
        wrong=sum(p.baseline_correct and not p.candidate_correct for p in pairs)
        gained=sum(p.candidate_correct and not p.baseline_correct for p in pairs)
        families={p.task_family for p in pairs}
        sources={p.source_group_digest for p in pairs}
        ratio=max((p.candidate_latency_ms/p.baseline_latency_ms
                   for p in pairs),default=1)
        if now<self.plan.issued_at:
            status="not_started"
        elif now>=self.plan.expires_at:
            status="expired"
        elif wrong or ratio>self.plan.max_latency_ratio:
            status="halted_regression"
        elif (len(pairs)>=self.plan.min_pairs and gained>=2
              and len(families)>=3 and len(sources)>=3):
            status="ready_for_operator_review"
        else:
            status="canary_running"
        return {"schema":"skeleton.jeeves.canary_status.v1",
                "owner":self.plan.owner,"plan_digest":self.plan_digest,
                "status":status,"candidate_pairs":len(pairs),
                "newly_correct":gained,"regressions":wrong,
                "max_latency_ratio_observed":round(ratio,5),
                "task_families":len(families),"source_groups":len(sources),
                "candidate_exposure_permitted":status in (
                    "canary_running","ready_for_operator_review"),
                "full_rollout_authorized":False,
                "neural_training_authorized":False}

    def _validate_pair(self, p: SignedCanaryPair, now: int, *, check_fresh: bool):
        if (p.owner!=self.plan.owner or p.plan_digest!=self.plan_digest
            or type(p.case_digest) is not str or not HEX.fullmatch(p.case_digest)
            or type(p.source_group_digest) is not str
            or not HEX.fullmatch(p.source_group_digest)
            or type(p.task_family) is not str or
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,39}",p.task_family)
            or type(p.baseline_correct) is not bool
            or type(p.candidate_correct) is not bool
            or any(type(x) is not int or not 1<=x<=60000 for x in (
                p.baseline_latency_ms,p.candidate_latency_ms))
            or p.assessor!=self.assessor or p.assessor_key_id!=self.assessor_key_id
            or type(p.observed_at) is not int
            or not self.plan.issued_at<=p.observed_at<self.plan.expires_at
            or (check_fresh and p.observed_at>now)):
            raise ValueError("paired independent canary measurement invalid")
        _verify(self.assessor_public_key,p.signature_hex,p.body())

    def observe(self, pair: SignedCanaryPair, *, now: int):
        if not isinstance(pair,SignedCanaryPair):
            raise TypeError("independently signed canary pair required")
        self._validate_pair(pair,now,check_fresh=True)
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                # Recalculate from immutable signed receipts INSIDE the same
                # transaction used for the new observation, avoiding TOCTOU.
                if self.audit(now=now)["status"] not in (
                    "canary_running","ready_for_operator_review"):
                    raise PermissionError("canary exposure already halted")
                if self.db.execute(
                    "SELECT COUNT(*) FROM dragon_canary_pairs_v1 "
                    "WHERE owner=? AND plan_digest=?",
                    (self.plan.owner,self.plan_digest)).fetchone()[0]>=MAX_SAMPLES:
                    raise ValueError("canary sample capacity exceeded")
                raw=canonical_json(pair.body())
                self.db.execute(
                    "INSERT INTO dragon_canary_pairs_v1 VALUES(?,?,?,?,?,?)",
                    (self.plan.owner,self.plan_digest,pair.case_digest,raw,
                     pair.signature_hex,self._mac(
                         "pair",{"body":raw,"signature":pair.signature_hex})))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return self.audit(now=now)

    def select(self, query: str, *, cohort_digest: str, now: int,
               limit: int = 5):
        if type(cohort_digest) is not str or not HEX.fullmatch(cohort_digest):
            raise ValueError("privacy-preserving cohort digest required")
        self._verify_binding(now)
        status=self.audit(now=now)
        hashed=canonical_digest({
            "owner":self.plan.owner,"plan":self.plan_digest,
            "cohort":cohort_digest})
        selected=(self.plan.candidate_digest
                  if status["candidate_exposure_permitted"]
                  and int(hashed[:8],16)%10000<self.plan.traffic_percent*100
                  else self.plan.control_digest)
        result=self.vault.route_version(query,index_digest=selected,
                                        now=now,limit=limit)
        return {**result,"canary_plan_digest":self.plan_digest,
                "canary_status":status["status"],
                "candidate_selected":selected==self.plan.candidate_digest,
                "full_rollout_authorized":False}
