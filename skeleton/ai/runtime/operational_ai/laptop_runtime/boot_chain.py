"""Source-bound ordered activation proofs for one laptop inference epoch."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .contracts import canonical,refuse,identity_hash

@dataclass(frozen=True,slots=True)
class BootProof:
    stage:str
    previous_sha256:str
    content_sha256:str
    stage_sha256:str

_STAGES=("source-reviewed","installer-receipt-verified",
         "private-state-verified","native-backend-activated",
         "principal-bound","loopback-authorized")

class BootChain:
    def __init__(self):
        self._proofs=[];self._head="0"*64

    def add(self,stage,content_sha256):
        if len(self._proofs)>=len(_STAGES):refuse("boot evidence already terminal")
        if stage!=_STAGES[len(self._proofs)]:
            refuse("boot sequence skipped or reordered")
        content_sha256=identity_hash(content_sha256)
        if content_sha256=="0"*64:refuse("empty boot evidence")
        raw=canonical({"schema":"laptop-boot-proof.v1","stage":stage,
                       "previous_sha256":self._head,
                       "content_sha256":content_sha256})
        digest=sha256(raw).hexdigest()
        result=BootProof(stage,self._head,content_sha256,digest)
        self._head=digest;self._proofs.append(result)
        return result

    def audit(self):
        previous="0"*64
        for index,proof in enumerate(self._proofs):
            if proof.stage!=_STAGES[index] or proof.previous_sha256!=previous:
                refuse("boot proof chain fork")
            digest=sha256(canonical({"schema":"laptop-boot-proof.v1",
                "stage":proof.stage,"previous_sha256":proof.previous_sha256,
                "content_sha256":proof.content_sha256})).hexdigest()
            if digest!=proof.stage_sha256:refuse("boot proof tampered")
            previous=digest
        return {"stage_count":len(self._proofs),
                "complete":len(self._proofs)==len(_STAGES),
                "head_sha256":previous,
                "release_certified":False}
