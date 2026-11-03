"""Ordered, hash-linked epoch attestations; no gaps or claimed extra steps."""
from __future__ import annotations
from dataclasses import dataclass
from .trainer import EpochResult
from .canonical import digest,require_sha
from .errors import reject

GENESIS="0"*64


@dataclass(frozen=True,slots=True)
class ChainLink:
    ordinal:int
    previous:str
    epoch_sha256:str
    current:str

    def record(self)->dict:
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


def build(epochs:tuple[EpochResult,...])->tuple[ChainLink,...]:
    if type(epochs) is not tuple or not epochs or len(epochs)>12:
        reject("epoch-chain-count")
    previous=GENESIS
    chain=[]
    for index,epoch in enumerate(epochs):
        if type(epoch) is not EpochResult or epoch.ordinal!=index:
            reject("epoch-chain-ordinal")
        sha=digest(epoch.report())
        current=digest({"previous":previous,"ordinal":index,
                        "epoch_sha256":sha})
        chain.append(ChainLink(index,previous,sha,current))
        previous=current
    return tuple(chain)


def verify(links:tuple[ChainLink,...],epochs:tuple[EpochResult,...],
           *,expected_head:str|None=None)->dict:
    if type(links) is not tuple or len(links)!=len(epochs):
        reject("epoch-chain-length")
    expected=build(epochs)
    if links!=expected:
        reject("epoch-chain-mismatch")
    head=links[-1].current
    if expected_head is not None:
        require_sha(expected_head,"epoch-head")
        if head!=expected_head:
            reject("epoch-chain-pinned-head")
    return {"links":len(links),"head":head,
            "verified":True,"external_head_pin_required":True}
