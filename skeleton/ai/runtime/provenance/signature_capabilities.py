"""Signature capability negotiation for provenance envelopes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable,Final

@dataclass(frozen=True,slots=True)
class SignatureCapability:
    algorithm:str
    standard:str
    post_quantum:bool
    serialization:tuple[str,...]
    def __post_init__(self)->None:
        if not self.algorithm.strip() or not self.standard.strip() or not self.serialization: raise ValueError("signature capability metadata required")

CAPABILITIES: Final=(
    SignatureCapability("ed25519","RFC 8032",False,("raw","jose","cose")),
    SignatureCapability("ml-dsa-44","FIPS 204 / RFC 9964",True,("jose","cose")),
    SignatureCapability("ml-dsa-65","FIPS 204 / RFC 9964",True,("jose","cose")),
    SignatureCapability("ml-dsa-87","FIPS 204 / RFC 9964",True,("jose","cose")),
    SignatureCapability("slh-dsa","FIPS 205",True,("provider-native",)),
)
_BY_ID: Final={item.algorithm:item for item in CAPABILITIES}

class SignerRegistry:
    def __init__(self)->None: self._signers:dict[str,Callable[[bytes],bytes]]={}
    def register(self,algorithm:str,signer:Callable[[bytes],bytes])->None:
        if algorithm not in _BY_ID: raise ValueError("unknown signature capability")
        if not callable(signer): raise TypeError("signer must be callable")
        self._signers[algorithm]=signer
    def available(self)->tuple[str,...]: return tuple(sorted(self._signers))
    def sign(self,algorithm:str,payload:bytes)->bytes:
        if algorithm not in _BY_ID: raise ValueError("unknown signature capability")
        signer=self._signers.get(algorithm)
        if signer is None: raise RuntimeError("signature implementation is not installed")
        signature=signer(payload)
        if not isinstance(signature,bytes) or not signature: raise RuntimeError("signature backend returned invalid signature")
        return signature

def negotiate(preferred:tuple[str,...],available:tuple[str,...])->SignatureCapability:
    available_set=set(available)
    for algorithm in preferred:
        if algorithm in available_set and algorithm in _BY_ID: return _BY_ID[algorithm]
    raise RuntimeError("no mutually supported signature capability")

__all__=["CAPABILITIES","SignatureCapability","SignerRegistry","negotiate"]
