"""Immutable human review receipts bound to exact adversarial evidence."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3,math

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_adversarial_review_worker import AdversarialReviewOutput
from .dragon_knowledge_normalization_worker import NormalizedKnowledge
from .dragon_knowledge_manifest import canonical_knowledge_manifest


@dataclass(frozen=True)
class HumanReviewDecision:
    review_id:str
    reviewer_id:str
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
          adversarial_fingerprint TEXT NOT NULL,survivor_digest TEXT NOT NULL,
          survivor_manifest TEXT NOT NULL DEFAULT '',approved INTEGER NOT NULL,reviewed_at REAL NOT NULL,rationale TEXT NOT NULL,
          PRIMARY KEY(owner,review_id))""");db.commit()

    def review(self,owner:str,review:AdversarialReviewOutput,*,reviewer_id:str,
               approved:bool,reviewed_at:float,rationale:str,
               authorized:bool,records:tuple[NormalizedKnowledge,...]=())->tuple[HumanReviewDecision,LayerReceipt]:
        if not authorized: raise PermissionError("human review requires authorization")
        if review.receipt.layer is not AnalysisLayer.ADVERSARIAL_REVIEW:
            raise ValueError("adversarial review evidence required")
        if approved and not review.receipt.passed:
            raise PermissionError("failed adversarial review cannot be approved")
        if not reviewer_id or len(reviewer_id)>128 or not math.isfinite(reviewed_at) or reviewed_at<0:
            raise ValueError("invalid reviewer identity or time")
        if not isinstance(rationale,str) or not 1<=len(rationale)<=2000:
            raise ValueError("review rationale required")
        survivors=tuple(sorted(review.surviving_knowledge_ids))
        survivor_digest=sha256(json.dumps(survivors,separators=(",",":")).encode()).hexdigest()
        by_id={x.knowledge_id:x for x in records}
        if set(survivors)!=set(by_id): raise ValueError("human review requires exact surviving normalized records")
        survivor_manifest=canonical_knowledge_manifest(tuple(by_id[x] for x in survivors))
        rid=sha256(json.dumps([owner,reviewer_id,review.receipt.output_fingerprint,
            survivor_digest,survivor_manifest,approved,reviewed_at,rationale],
            separators=(",",":")).encode()).hexdigest()
        decision=HumanReviewDecision(rid,reviewer_id,
            review.receipt.output_fingerprint,survivor_digest,survivor_manifest,approved,reviewed_at,rationale)
        with self.db:
            existing=self.db.execute("""SELECT reviewer_id,adversarial_fingerprint,
              survivor_digest,survivor_manifest,approved,reviewed_at,rationale FROM dragon_human_reviews
              WHERE owner=? AND review_id=?""",(owner,rid)).fetchone()
            expected=(reviewer_id,review.receipt.output_fingerprint,survivor_digest,survivor_manifest,
                int(approved),reviewed_at,rationale)
            if existing and existing!=expected: raise ValueError("immutable human review conflict")
            self.db.execute("""INSERT OR IGNORE INTO dragon_human_reviews VALUES(?,?,?,?,?,?,?,?,?)""",
                (owner,rid,*expected))
        receipt=LayerReceipt(AnalysisLayer.HUMAN_APPROVAL,
            (review.receipt.output_fingerprint,),rid,
            review.receipt.independent_sources,approved,approved)
        return decision,receipt
