"""Source-complete 24-case domain slices allow resumable, nonphantom evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_oracle import DOMAINS
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class Slice:
    ordinal:int
    domain:str
    start:int
    count:int
    source_sha256:str

    def record(self)->dict:
        return {key:getattr(self,key) for key in self.__dataclass_fields__}


def create_slices()->tuple[Slice,...]:
    from .challenge_catalog import iter_challenges
    cases=tuple(iter_challenges())
    if len(cases)!=768:
        reject("slices-incomplete")
    result=[]
    for ordinal,domain in enumerate(DOMAINS):
        block=cases[ordinal*24:(ordinal+1)*24]
        if len(block)!=24 or any(item.domain!=domain for item in block):
            reject("slice-source-domain")
        result.append(Slice(
            ordinal,domain,ordinal*24,24,
            digest([x.record() for x in block]),
        ))
    return tuple(result)


def verify_slices(slices:tuple[Slice,...])->dict:
    expected=create_slices()
    if slices!=expected:
        reject("slices-content-mismatch")
    return {
        "segments":32,"cases":768,
        "source_sha256":digest([x.record() for x in slices]),
        "actually_executed":False,
    }
