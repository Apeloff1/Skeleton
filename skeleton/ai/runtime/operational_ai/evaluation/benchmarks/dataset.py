"""Rights-approved, schema-versioned evaluation fixtures and contamination lineage."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,re
from typing import Any

class EvalError(ValueError):pass
_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
_SHA=re.compile(r'^[0-9a-f]{64}$')

@dataclass(frozen=True,slots=True)
class EvalCase:
    case_id:str
    prompt:str
    expected:str
    category:str
    seed:int
    license:str
    provenance:str
    input_sha:str

    def __post_init__(self):
        if not _ID.fullmatch(self.case_id) or not _ID.fullmatch(self.category):
            raise EvalError('invalid evaluation ID or category')
        if not isinstance(self.prompt,str) or not 1<=len(self.prompt.encode())<=16_000:
            raise EvalError('prompt size outside bounded evaluation')
        if not isinstance(self.expected,str) or len(self.expected.encode())>32_000:
            raise EvalError('invalid evaluation reference')
        if type(self.seed) is not int or not 0<=self.seed<=2**32-1:
            raise EvalError('invalid evaluation seed')
        if not isinstance(self.license,str) or not self.license.strip() or not isinstance(self.provenance,str) or not self.provenance.strip():
            raise EvalError('evaluation item provenance and rights required')
        if not _SHA.fullmatch(self.input_sha) or sha256(self.prompt.encode()).hexdigest()!=self.input_sha:
            raise EvalError('evaluation input hash mismatch')

    @classmethod
    def create(cls,case_id:str,prompt:str,expected:str,category:str,
               *,seed:int=0,license:str='original-operator-owned',provenance:str='generated:eval-fixture')->'EvalCase':
        return cls(case_id,prompt,expected,category,seed,license,provenance,sha256(prompt.encode()).hexdigest())

@dataclass(frozen=True,slots=True)
class EvalSet:
    set_id:str
    cases:tuple[EvalCase,...]
    version:int
    approved:bool
    split:str
    source_sha:str

    def __post_init__(self):
        if not _ID.fullmatch(self.set_id) or self.split not in {'train','validation','test','holdout'}:
            raise EvalError('invalid evaluation set ID or partition')
        if type(self.version) is not int or not 1<=self.version<=100000:
            raise EvalError('invalid benchmark revision')
        if type(self.approved) is not bool or not self.approved:
            raise EvalError('benchmark admission requires human-approved dataset')
        if not self.cases or len(self.cases)>10_000 or len(set(x.case_id for x in self.cases))!=len(self.cases):
            raise EvalError('empty, huge, or duplicate benchmark items')
        if not _SHA.fullmatch(self.source_sha):raise EvalError('invalid benchmark source SHA')
        if self.source_sha!=self.computed_sha():raise EvalError('benchmark contents do not match source identity')

    def computed_sha(self)->str:
        canonical=[{'case_id':x.case_id,'input_sha':x.input_sha,'expected':x.expected,
                    'category':x.category,'seed':x.seed,'license':x.license,'provenance':x.provenance} for x in self.cases]
        return sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @classmethod
    def admitted(cls,set_id:str,cases:tuple[EvalCase,...],*,version:int=1,split:str='holdout',approved:bool=False)->'EvalSet':
        proto=object.__new__(cls)
        object.__setattr__(proto,'cases',cases)
        source_sha=cls.computed_sha(proto)
        return cls(set_id,cases,version,approved,split,source_sha)
