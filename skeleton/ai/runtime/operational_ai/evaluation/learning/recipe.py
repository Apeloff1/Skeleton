"""Reproducible resource-bounded fine-tuning *plan*, not a claim weights were trained."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .dataset import LearningError

@dataclass(frozen=True,slots=True)
class TrainingRecipe:
    method:str
    learning_rate:float
    epochs:int
    batch_size:int
    accumulation:int
    seed:int
    dataset_sha:str
    base_sha:str
    optimizer:str

    def __post_init__(self):
        if self.method not in {'lora','qlora','full'} or self.optimizer not in {'adamw','sgd'}:
            raise LearningError('unsupported recorded training method')
        if type(self.learning_rate) is not float or not 1e-7<=self.learning_rate<=1e-2:
            raise LearningError('learning rate outside bounded envelope')
        for name,high in (('epochs',100),('batch_size',4096),('accumulation',1024)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=high:
                raise LearningError('invalid training resource plan')
        if type(self.seed) is not int or not 0<=self.seed<=2**32-1:
            raise LearningError('invalid training RNG seed')
        if any(not isinstance(x,str) or len(x)!=64 for x in (self.dataset_sha,self.base_sha)):
            raise LearningError('training recipe missing immutable source identities')

    @property
    def digest(self)->str:
        return sha256(json.dumps(self.__dict__ if hasattr(self,'__dict__') else
          {key:getattr(self,key) for key in self.__dataclass_fields__},sort_keys=True,separators=(',',':')).encode()).hexdigest()
