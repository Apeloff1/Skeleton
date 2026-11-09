"""Approved cryptography-backed provenance signers."""
from __future__ import annotations
from dataclasses import dataclass
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from .commitments import Commitment

@dataclass(frozen=True,slots=True)
class Ed25519Keypair:
    key_id:str
    private_key:Ed25519PrivateKey
    public_key:Ed25519PublicKey
    def __post_init__(self)->None:
        if not self.key_id.strip(): raise ValueError("key_id required")
    @classmethod
    def generate(cls)->"Ed25519Keypair":
        private=Ed25519PrivateKey.generate(); public=private.public_key()
        raw=public.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        key_id="ed25519:"+Commitment.of({"public_key":raw.hex()}).value[:32]
        return cls(key_id,private,public)
    def sign(self,payload:bytes)->bytes: return self.private_key.sign(payload)
    def verify(self,payload:bytes,signature:bytes)->bool:
        try: self.public_key.verify(signature,payload); return True
        except InvalidSignature: return False
    def public_bytes(self)->bytes:
        return self.public_key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)

def verifier_from_public_bytes(raw:bytes):
    public=Ed25519PublicKey.from_public_bytes(raw)
    def verify(payload:bytes,signature:bytes)->bool:
        try: public.verify(signature,payload); return True
        except InvalidSignature: return False
    return verify

__all__=["Ed25519Keypair","verifier_from_public_bytes"]
