"""Content-addressed, explicitly licensed operator-curated training data."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,re

class LearningError(ValueError):pass
_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
_SHA=re.compile(r'^[0-9a-f]{64}$')

@dataclass(frozen=True,slots=True)
class TrainingRecord:
    sample_id:str
    prompt:str
    response:str
    license:str
    provenance:str
    source_sha:str
    consent_confirmed:bool

    def __post_init__(self):
        if not _ID.fullmatch(self.sample_id):raise LearningError('invalid sample identity')
        if not isinstance(self.prompt,str) or not 1<=len(self.prompt.encode())<=65536:
            raise LearningError('invalid training prompt bound')
        if not isinstance(self.response,str) or not 1<=len(self.response.encode())<=65536:
            raise LearningError('invalid training response bound')
        if not isinstance(self.license,str) or not self.license.strip() or self.license.lower() in {'unknown','tbd'}:
            raise LearningError('unknown dataset rights')
        if not isinstance(self.provenance,str) or not self.provenance.strip():
            raise LearningError('missing training data source provenance')
        if type(self.consent_confirmed) is not bool or not self.consent_confirmed:
            raise LearningError('training record requires independent consent')
        expected=sha256(json.dumps([self.prompt,self.response],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if not _SHA.fullmatch(self.source_sha) or expected!=self.source_sha:
            raise LearningError('training source digest drift')

    @classmethod
    def admit(cls,sample_id:str,prompt:str,response:str,license:str,provenance:str,
              *,consent_confirmed:bool=False)->'TrainingRecord':
        digest=sha256(json.dumps([prompt,response],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        return cls(sample_id,prompt,response,license,provenance,digest,consent_confirmed)

@dataclass(frozen=True,slots=True)
class TrainingDataset:
    dataset_id:str
    records:tuple[TrainingRecord,...]
    split:str
    revision:int
    dataset_sha:str

    def __post_init__(self):
        if not _ID.fullmatch(self.dataset_id) or self.split not in {'train','validation','test'}:
            raise LearningError('invalid training dataset identity or partition')
        if type(self.revision) is not int or self.revision<1:raise LearningError('invalid dataset revision')
        if not self.records or len(self.records)>50_000 or len(set(x.sample_id for x in self.records))!=len(self.records):
            raise LearningError('empty, huge or duplicate dataset')
        expected=sha256(json.dumps([x.source_sha for x in self.records],sort_keys=False,separators=(',',':')).encode()).hexdigest()
        if expected!=self.dataset_sha:raise LearningError('dataset manifest digest mismatch')

    @classmethod
    def assemble(cls,dataset_id:str,records:tuple[TrainingRecord,...],*,split:str='train',revision:int=1):
        digest=sha256(json.dumps([x.source_sha for x in records],separators=(',',':')).encode()).hexdigest()
        return cls(dataset_id,records,split,revision,digest)
