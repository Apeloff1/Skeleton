"""Separately authenticated Wiki review and memory approval receipts.

A trusted identity issuer signs short-lived, scope-bound authorizations after
validating the human principal. This module neither authenticates passwords
nor exposes a browser signing endpoint; only a sealed worker holding the keys
may invoke this API. The two roles MUST have different signing keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets
from typing import Literal

from .contracts import canonical_digest, canonical_json
from .dragon_wisdom_pyramid import DragonWisdomPyramid, _hash, _id, _time
from .reviewed_knowledge import KnowledgeBrief

_ROLE = ("wiki_reviewer", "memory_approver")


@dataclass(frozen=True, slots=True)
class WisdomGrant:
    owner: str
    subject: str
    affiliation: str
    role: str
    target_digest: str
    issued_at: int
    expires_at: int
    nonce: str
    issuer: str
    signature: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.dragon.wisdom_grant.v1",
            "owner": self.owner, "subject": self.subject,
            "affiliation": self.affiliation, "role": self.role,
            "target_digest": self.target_digest, "issued_at": self.issued_at,
            "expires_at": self.expires_at, "nonce": self.nonce,
            "issuer": self.issuer,
        }

    @property
    def digest(self) -> str:
        return canonical_digest({**self.body(), "signature": self.signature})


class DragonWisdomAuthority:
    """Trusted, role-separated receipt gateway into the existing Wiki ledger.

    issuer sign-off is only as trustworthy as the external principal verifier.
    A subject string/affiliation supplied directly by an untrusted caller must
    NEVER be passed to issue_grant with identity_verified=True.
    """

    def __init__(self, pyramid: DragonWisdomPyramid, *,
                 wiki_signing_key: bytes, approval_signing_key: bytes,
                 issuer: str):
        if not isinstance(pyramid, DragonWisdomPyramid):
            raise TypeError("canonical Wiki ledger required")
        if (type(wiki_signing_key) is not bytes or len(wiki_signing_key) < 32
                or type(approval_signing_key) is not bytes or len(approval_signing_key) < 32
                or hmac.compare_digest(wiki_signing_key, approval_signing_key)):
            raise ValueError("independent 256-bit role keys required")
        self.pyramid = pyramid
        self.keys = {"wiki_reviewer": wiki_signing_key,
                     "memory_approver": approval_signing_key}
        self.issuer = _id(issuer)

    def _mac(self, role: str, body: dict) -> str:
        return hmac.new(self.keys[role],
                        canonical_json(body).encode("utf-8"), sha256).hexdigest()

    def issue_grant(self, owner: str, subject: str, affiliation: str,
                    role: Literal["wiki_reviewer", "memory_approver"],
                    target_digest: str, *, now: int, expires_at: int,
                    identity_verified: bool, authorized: bool) -> WisdomGrant:
        if identity_verified is not True or authorized is not True:
            raise PermissionError("authenticated independent reviewer identity required")
        _id(owner); _id(subject); _id(affiliation)
        _hash(target_digest); _time(now); _time(expires_at)
        if role not in self.keys or not now < expires_at <= now + 3600:
            raise ValueError("invalid role or grant expiration")
        # Random nonces prevent accidentally equating two separate review acts.
        body = {
            "schema": "skeleton.dragon.wisdom_grant.v1",
            "owner": owner, "subject": subject, "affiliation": affiliation,
            "role": role, "target_digest": target_digest,
            "issued_at": now, "expires_at": expires_at,
            "nonce": secrets.token_hex(16), "issuer": self.issuer,
        }
        return WisdomGrant(owner, subject, affiliation, role,
                           target_digest, now, expires_at, body["nonce"],
                           self.issuer, self._mac(role, body))

    def verify_grant(self, grant: WisdomGrant, *, role: str, owner: str,
                     target_digest: str, now: int) -> None:
        if not isinstance(grant, WisdomGrant):
            raise PermissionError("signed role grant required")
        _time(now); _id(owner); _hash(target_digest)
        if role not in self.keys or grant.role != role or grant.owner != owner:
            raise PermissionError("grant role or tenant mismatch")
        if grant.issuer != self.issuer or grant.target_digest != target_digest:
            raise PermissionError("grant evidence scope mismatch")
        _id(grant.subject); _id(grant.affiliation)
        _time(grant.issued_at); _time(grant.expires_at)
        if (not grant.issued_at <= now < grant.expires_at
                or grant.expires_at > grant.issued_at + 3600
                or not isinstance(grant.nonce, str) or len(grant.nonce) != 32
                or any(c not in "0123456789abcdef" for c in grant.nonce)):
            raise PermissionError("grant expired, forged or malformed")
        _hash(grant.signature)
        if not hmac.compare_digest(grant.signature, self._mac(role, grant.body())):
            raise PermissionError("grant signature does not verify")

    def review(self, owner: str, brief: KnowledgeBrief, *, mechanic: str,
               disposition: str, review_evidence_digest: str,
               grant: WisdomGrant, now: int, expires_at: int,
               authorized: bool, trusted_worker: bool) -> dict:
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted Wiki reviewer required")
        if not isinstance(brief, KnowledgeBrief):
            raise ValueError("typed knowledge brief required")
        target = brief.to_payload()["brief_digest"]
        self.verify_grant(grant, role="wiki_reviewer", owner=owner,
                          target_digest=target, now=now)
        _id(mechanic); _hash(review_evidence_digest)
        # A reviewer must be outside the organizations controlling the source
        # and distinct from its named original source reviewer. The issuer
        # remains responsible for verifying actual affiliation.
        source_reviewers: set[str] = set()
        source_groups: set[str] = set()
        for source in self.pyramid.library._rows(owner):
            if source["status"] != "active":
                continue
            if any(entry["note"]["mechanic"] == mechanic for entry in source["notes"]):
                source_reviewers.add(source["reviewer_id"])
                source_groups.update(entry["note"]["dependence_group"]
                                     for entry in source["notes"])
        if grant.subject in source_reviewers or grant.affiliation in source_groups:
            raise PermissionError("Wiki reviewer conflicts with research provenance")
        # Binds the role/identity proof to the independent supporting evidence.
        bound_evidence = canonical_digest({
            "review_evidence": review_evidence_digest, "grant": grant.digest,
            "brief_digest": target, "mechanic": mechanic,
        })
        result = self.pyramid.wiki_review(
            owner, brief, mechanic=mechanic, disposition=disposition,
            independent_reviewer_id=grant.subject,
            review_evidence_digest=bound_evidence, now=now,
            expires_at=expires_at, authorized=True, trusted_worker=True,
        )
        return {**result, "reviewer_grant_digest": grant.digest}

    def approve(self, owner: str, review_digest: str, *,
                grant: WisdomGrant, now: int, authorized: bool,
                trusted_worker: bool) -> dict:
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted memory approver required")
        _hash(review_digest)
        self.verify_grant(grant, role="memory_approver", owner=owner,
                          target_digest=review_digest, now=now)
        reviews = self.pyramid._history(owner)
        review = self.pyramid._review(reviews, review_digest)
        if review["reviewer"] == grant.subject:
            raise PermissionError("memory approver must differ from Wiki reviewer")
        if review["disposition"] != "accepted":
            raise PermissionError("only accepted Wiki evidence can be approved")
        result = self.pyramid.promote(
            owner, review_digest, now=now, authorized=True,
            trusted_worker=True, human_approved=True,
            approval_evidence_digest=grant.digest,
        )
        return {**result, "approval_grant_digest": grant.digest}
