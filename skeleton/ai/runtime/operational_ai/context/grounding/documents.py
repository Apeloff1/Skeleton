"""Strict, bounded original-source provenance and immutable byte ranges."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
import re

class GroundingError(ValueError):pass
_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
_DIGEST=re.compile(r'^[0-9a-f]{64}$')


def check_id(value:object,label:str)->str:
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise GroundingError(f'invalid {label}')
    return value


@dataclass(frozen=True,slots=True)
class Document:
    doc_id:str
    tenant:str
    user:str
    text:str
    origin:str
    rights:str
    trust:str
    revision:int
    approved:bool
    sha256:str

    def __post_init__(self)->None:
        for key in ('doc_id','tenant','user'):
            check_id(getattr(self,key),key)
        if not isinstance(self.text,str) or len(self.text.encode('utf8'))>2_000_000:
            raise GroundingError('document text too large')
        if type(self.revision) is not int or self.revision<1:
            raise GroundingError('document revision invalid')
        if type(self.approved) is not bool or not self.approved:
            raise GroundingError('document is not independently approved')
        if self.trust not in {'operator-owned','verified-import','untrusted-reference'}:
            raise GroundingError('model-generated text cannot gain memory authority')
        for field in ('origin','rights'):
            val=getattr(self,field)
            if not isinstance(val,str) or not 1<=len(val)<=512:
                raise GroundingError(f'document lacks {field}')
        if not _DIGEST.fullmatch(self.sha256) or sha256(self.text.encode('utf8')).hexdigest()!=self.sha256:
            raise GroundingError('source bytes fail sha256 provenance')

    @classmethod
    def from_text(cls,doc_id:str,tenant:str,user:str,text:str,origin:str,
                  rights:str,*,revision:int=1,approved:bool=False,
                  trust:str='operator-owned')->'Document':
        return cls(doc_id,tenant,user,text,origin,rights,trust,revision,approved,
                   sha256(text.encode('utf8')).hexdigest())

    def to_record(self)->dict[str,Any]:
        return {name:getattr(self,name) for name in self.__dataclass_fields__}


@dataclass(frozen=True,slots=True)
class Passage:
    doc_id:str
    chunk_id:str
    start:int
    end:int
    body:str
    sha256:str
    revision:int
    trust:str

    def __post_init__(self)->None:
        check_id(self.doc_id,'document')
        check_id(self.chunk_id,'chunk')
        if type(self.start) is not int or type(self.end) is not int or not 0<=self.start<self.end:
            raise GroundingError('invalid source span')
        if len(self.body.encode('utf8'))>32_000:
            raise GroundingError('passage too large')
        if not _DIGEST.fullmatch(self.sha256):
            raise GroundingError('invalid source digest')
        if type(self.revision) is not int or self.revision<=0:
            raise GroundingError('invalid passage revision')
