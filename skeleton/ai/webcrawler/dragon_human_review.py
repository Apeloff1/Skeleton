"""Immutable human review receipts bound to exact adversarial evidence and reviewer identity."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3,math
from typing import Callable

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_adversarial_review_worker import AdversarialReviewOutput
from .dragon_knowledge_normalization_worker import NormalizedKnowledge
from .dragon_knowledge_manifest import canonical_knowledge_manifest


@dataclass(frozen=True)
class ReviewerPrincipal:
    reviewer_id:str
    issuer:str
    subject:str
    authenticated_at:float
    credential_fingerprint:str


def reviewer_principal_fingerprint(principal:ReviewerPrincipal)->str:
    if not isinstance(principal.reviewer_id,str) or not 1<=len(principal.reviewer_id)<=128:
        raise ValueError("invalid reviewer principal identity")
    if not isinstance(principal.issuer,str) or not 1<=len(principal.issuer)<=256:
        raise ValueError("invalid reviewer principal issuer")
    if not isinstance(principal.subject,str) or not 1<=len(principal.subject)<=256:
        raise ValueError("invalid reviewer principal subject")
    if not math.isfinite(principal.authenticated_at) or principal.authenticated_at<0:
        raise ValueError("invalid reviewer authentication time")
    value=principal.credential_fingerprint
    if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid reviewer credential fingerprint")
    return sha256(json.dumps([
        principal.reviewer_id,principal.issuer,principal.subject,
        principal.authenticated_at,principal.credential_fingerprint,
    ],separators=(",",":")).encode()).hexdigest()


@dataclass(frozen=True)
class HumanReviewDecision:
    review_id:str
    reviewer_id:str
    reviewer_principal_fingerprint:str
    adversarial_fingerprint:str
    survivor_digest:str
    survivor_manifest:str
    approved:bool
    reviewed_at:float
    rationale:str


class DragonHumanReviewLedger:
    def __init__(self,db:sqlite3.Connection):
        self.db=db
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_human_reviews(
          owner TEXT NOT NULL,review_id TEXT NOT NULL,reviewer_id TEXT NOT NULL,
          reviewer_principal_fingerprint TEXT NOT NULL DEFAULT '',
          adversarial_fingerprint TEXT NOT NULL,survivor_digest TEXT NOT NULL,
          survivor_manifest TEXT NOT NULL DEFAULT '',approved INTEGER NOT NULL,
          reviewed_at REAL NOT NULL,rationale TEXT NOT NULL,
          PRIMARY KEY(owner,review_id))""")
        columns={row[1] for row in db.execute("PRAGMA table_info(dragon_human_reviews)")}
        if "survivor_manifest" not in columns:
            db.execute("ALTER TABLE dragon_human_reviews ADD COLUMN survivor_manifest TEXT NOT NULL DEFAULT ''")
        if "reviewer_principal_fingerprint" not in columns:
            db.execute("ALTER TABLE dragon_human_reviews ADD COLUMN reviewer_principal_fingerprint TEXT NOT NULL DEFAULT ''")
        db.commit()

    def get(self,owner:str,review_id:str,*,authorized:bool)->HumanReviewDecision:
        if not authorized:
            raise PermissionError("human review reading requires authorization")
        row=self.db.execute("""SELECT reviewer_id,reviewer_principal_fingerprint,
          adversarial_fingerprint,survivor_digest,survivor_manifest,approved,
          reviewed_at,rationale FROM dragon_human_reviews
          WHERE owner=? AND review_id=?""",(owner,review_id)).fetchone()
        if not row:
            raise KeyError("human review not found")
        if not row[4]:
            raise PermissionError("legacy human review lacks survivor manifest")
        if not row[1]:
            raise PermissionError("legacy human review lacks verified reviewer principal")
        return HumanReviewDecision(review_id,row[0],row[1],row[2],row[3],row[4],
            bool(row[5]),row[6],row[7])

    def review(self,owner:str,review:AdversarialReviewOutput,*,reviewer_id:str,
               approved:bool,reviewed_at:float,rationale:str,authorized:bool,
               records:tuple[NormalizedKnowledge,...]=(),
               reviewer_principal:ReviewerPrincipal|None=None,
               principal_verifier:Callable[[ReviewerPrincipal],bool]|None=None
               )->tuple[HumanReviewDecision,LayerReceipt]:
        if not authorized:
            raise PermissionError("human review requires authorization")
        if review.receipt.layer is not AnalysisLayer.ADVERSARIAL_REVIEW:
            raise ValueError("adversarial review evidence required")
        if approved and not review.receipt.passed:
            raise PermissionError("failed adversarial review cannot be approved")
        if not reviewer_id or len(reviewer_id)>128 or not math.isfinite(reviewed_at) or reviewed_at<0:
            raise ValueError("invalid reviewer identity or time")
        if not isinstance(rationale,str) or not 1<=len(rationale)<=2000:
            raise ValueError("review rationale required")
        if reviewer_principal is None or principal_verifier is None:
            raise PermissionError("verified reviewer principal required")
        if reviewer_principal.reviewer_id!=reviewer_id:
            raise PermissionError("reviewer principal identity mismatch")
        if principal_verifier(reviewer_principal) is not True:
            raise PermissionError("reviewer principal verification failed")
        principal_fp=reviewer_principal_fingerprint(reviewer_principal)
        survivors=tuple(sorted(review.surviving_knowledge_ids))
        survivor_digest=sha256(json.dumps(survivors,separators=(",",":")).encode()).hexdigest()
        by_id={x.knowledge_id:x for x in records}
        if set(survivors)!=set(by_id):
            raise ValueError("human review requires exact surviving normalized records")
        survivor_manifest=canonical_knowledge_manifest(tuple(by_id[x] for x in survivors))
        rid=sha256(json.dumps([owner,reviewer_id,principal_fp,
            review.receipt.output_fingerprint,survivor_digest,survivor_manifest,
            approved,reviewed_at,rationale],separators=(",",":")).encode()).hexdigest()
        decision=HumanReviewDecision(rid,reviewer_id,principal_fp,
            review.receipt.output_fingerprint,survivor_digest,survivor_manifest,
            approved,reviewed_at,rationale)
        with self.db:
            existing=self.db.execute("""SELECT reviewer_id,reviewer_principal_fingerprint,
              adversarial_fingerprint,survivor_digest,survivor_manifest,approved,
              reviewed_at,rationale FROM dragon_human_reviews
              WHERE owner=? AND review_id=?""",(owner,rid)).fetchone()
            expected=(reviewer_id,principal_fp,review.receipt.output_fingerprint,
                survivor_digest,survivor_manifest,int(approved),reviewed_at,rationale)
            if existing and existing!=expected:
                raise ValueError("immutable human review conflict")
            self.db.execute("""INSERT OR IGNORE INTO dragon_human_reviews(
              owner,review_id,reviewer_id,reviewer_principal_fingerprint,
              adversarial_fingerprint,survivor_digest,survivor_manifest,approved,
              reviewed_at,rationale) VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (owner,rid,*expected))
        receipt=LayerReceipt(AnalysisLayer.HUMAN_APPROVAL,
            (review.receipt.output_fingerprint,),rid,
            review.receipt.independent_sources,approved,approved)
        return decision,receipt
