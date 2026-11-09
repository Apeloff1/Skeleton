"""Independent Ed25519 review attestation for Dragon source-capture pilots.

Only PUBLIC attester keys live in the application. The private signing key
must stay in a separately authenticated rights-review service. The signature
binds one human review to one already-issued, source/owner/policy-scoped
capture grant. It is not proof that the website itself granted a license:
the independent authority must inspect its real rights evidence beforehand.
"""
from __future__ import annotations

from dataclasses import dataclass
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_source_permission_authority import SourceCaptureGrant
from .reviewed_knowledge import _id, _integer

_MAX_EPOCH=4_102_444_800


@dataclass(frozen=True,slots=True)
class IndependentRightsAttestation:
    owner:str
    source_id:str
    source_url:str
    grant_digest:str
    policy_receipt:str
    evidence_digest:str
    reviewer:str
    issuer:str
    key_id:str
    issued_at:int
    expires_at:int
    retention_permitted:bool
    signature_hex:str

    def body(self)->dict:
        return {
            "schema":"skeleton.dragon.external_rights_review.v1",
            "owner":self.owner,"source_id":self.source_id,
            "source_url":self.source_url,
            "grant_digest":self.grant_digest,
            "policy_receipt":self.policy_receipt,
            "evidence_digest":self.evidence_digest,
            "reviewer":self.reviewer,
            "issuer":self.issuer,"key_id":self.key_id,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
            "reference_retention_permitted":self.retention_permitted,
            "crawler_training_authorized":False,
            "model_training_authorized":False,
        }

    @property
    def digest(self)->str:
        return canonical_digest({
            **self.body(),"signature_hex":self.signature_hex
        })


class DragonExternalRightsVerifier:
    """Public-key verification ONLY: no rights issuance in crawler runtime."""

    def __init__(self,*,public_key_bytes:bytes,issuer:str,key_id:str):
        if type(public_key_bytes) is not bytes or len(public_key_bytes)!=32:
            raise ValueError("trusted Ed25519 public-key bytes required")
        _id(issuer,"rights review issuer");_id(key_id,"rights signing key")
        self.public_key=Ed25519PublicKey.from_public_bytes(public_key_bytes)
        self.issuer=issuer
        self.key_id=key_id

    def verify(self,attestation:IndependentRightsAttestation,
               grant:SourceCaptureGrant,*,now:int,authorized:bool)->str:
        if not isinstance(grant,SourceCaptureGrant):
            raise PermissionError("signed source grant required for independent review")
        _auth(grant.owner,authorized)
        _integer(now,"independent review verification clock",0,_MAX_EPOCH)
        if not isinstance(attestation,IndependentRightsAttestation):
            raise PermissionError("typed external rights signature required")
        if (attestation.owner!=grant.owner
            or attestation.source_id!=grant.source_id
            or attestation.source_url!=grant.source_url
            or attestation.grant_digest!=grant.digest
            or attestation.policy_receipt!=grant.policy_receipt
            or attestation.evidence_digest!=grant.evidence_digest
            or attestation.reviewer!=grant.reviewer
            or attestation.issuer!=self.issuer
            or attestation.key_id!=self.key_id
            or attestation.retention_permitted is not True
            or type(attestation.signature_hex) is not str
            or len(attestation.signature_hex)!=128
            or not attestation.issued_at<=now<attestation.expires_at
            or attestation.expires_at>attestation.issued_at+3600
            or attestation.issued_at<grant.issued_at
            or attestation.expires_at>grant.expires_at):
            raise PermissionError("independent rights attestation scope or expiry invalid")
        try:
            signature=bytes.fromhex(attestation.signature_hex)
            self.public_key.verify(
                signature,canonical_json(attestation.body()).encode("utf-8")
            )
        except (ValueError,InvalidSignature):
            raise PermissionError("independent rights attestation signature invalid") from None
        return attestation.digest
