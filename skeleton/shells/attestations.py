"""Keyed attestations over execution receipts and arbitrary canonical payloads."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Mapping

from skeleton.shells.receipts import ExecutionReceipt


@dataclass(frozen=True)
class Attestation:
    key_id:str
    algorithm:str
    payload_digest:str
    signature:str

    def to_dict(self)->dict[str,str]:
        return {
            "key_id":self.key_id,
            "algorithm":self.algorithm,
            "payload_digest":self.payload_digest,
            "signature":self.signature,
        }


class AttestationError(ValueError):pass


def canonical_payload(payload:Mapping[str,object])->bytes:
    return json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")


class HMACAttestor:
    """HMAC-SHA256 attestor.

    Keys are provided by the caller and are never serialized into attestation
    objects. This is integrity evidence, not public-key provenance.
    """

    def __init__(self,key_id:str,key:bytes)->None:
        if not key_id or len(key_id)>128:raise AttestationError("invalid key_id")
        if not isinstance(key,bytes) or len(key)<16:raise AttestationError("attestation key must contain at least 16 bytes")
        self.key_id=key_id
        self._key=bytes(key)

    def sign_payload(self,payload:Mapping[str,object])->Attestation:
        encoded=canonical_payload(payload)
        digest=hashlib.sha256(encoded).hexdigest()
        signature=hmac.new(self._key,encoded,hashlib.sha256).hexdigest()
        return Attestation(self.key_id,"hmac-sha256",digest,signature)

    def verify_payload(self,payload:Mapping[str,object],attestation:Attestation)->bool:
        if attestation.key_id!=self.key_id or attestation.algorithm!="hmac-sha256":return False
        encoded=canonical_payload(payload)
        digest=hashlib.sha256(encoded).hexdigest()
        if not hmac.compare_digest(digest,attestation.payload_digest):return False
        expected=hmac.new(self._key,encoded,hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,attestation.signature)

    def sign_receipt(self,receipt:ExecutionReceipt)->Attestation:
        return self.sign_payload(receipt.to_dict())

    def verify_receipt(self,receipt:ExecutionReceipt,attestation:Attestation)->bool:
        return self.verify_payload(receipt.to_dict(),attestation)
