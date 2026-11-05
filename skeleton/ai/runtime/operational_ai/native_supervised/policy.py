"""Bounded full native SFT policy: no provider, no hidden source and no hot swap."""
from __future__ import annotations
from dataclasses import dataclass,fields
from .canonical import require_id,require_int,digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class SupervisedPolicy:
    run_id:str="native_sft_001"
    seed:int=29
    dimension:int=16
    context:int=256
    heads:int=2
    layers:int=1
    feed_forward:int=32
    max_vocabulary:int=8192
    epochs:int=1
    batch_examples:int=8
    learning_rate_ppm:int=2500
    max_optimizer_steps:int=48000
    max_wall_ms:int=3600000
    max_checkpoint_bytes:int=256000000
    min_train_known_ppm:int=1000000
    max_validation_loss_ppm:int=10000000
    min_improvement_ppm:int=0
    operator_approved:bool=False
    candidate_only:bool=True
    device:str="cpu"
    loss_scope:str="completion_only"
    source_license:str="skeleton_original"
    training_scope:str="offline_native_candidate_training"

    def __post_init__(self)->None:
        require_id(self.run_id,"run")
        for name,lower,upper in (
            ("seed",0,2**32-1),("dimension",8,256),
            ("context",32,4096),("heads",1,16),
            ("layers",1,16),("feed_forward",0,4096),
            ("max_vocabulary",64,32768),("epochs",1,12),
            ("batch_examples",1,64),("learning_rate_ppm",1,100000),
            ("max_optimizer_steps",1,1000000),("max_wall_ms",1,36000000),
            ("max_checkpoint_bytes",1048576,256000000),
            ("min_train_known_ppm",0,1000000),
            ("max_validation_loss_ppm",1,100000000),
            ("min_improvement_ppm",0,1000000),
        ):
            require_int(getattr(self,name),name,lower,upper)
        if self.dimension%self.heads:
            reject("head-geometry")
        if self.operator_approved is not True:
            reject("operator-approval-required")
        if self.candidate_only is not True:
            reject("candidate-only-required")
        if self.device!="cpu":
            reject("unsupported-sgd-device")
        if self.loss_scope!="completion_only":
            reject("prompt-loss-not-admitted")
        if self.source_license!="skeleton_original" or self.training_scope!="offline_native_candidate_training":
            reject("source-rights-scope")

    def record(self)->dict:
        return {f.name:getattr(self,f.name) for f in fields(self)}

    @classmethod
    def parse(cls,data:dict)->"SupervisedPolicy":
        if type(data) is not dict or set(data)-{f.name for f in fields(cls)}:
            reject("unknown-policy-fields")
        try:
            return cls(**data)
        except TypeError:
            reject("policy-shape")

    @property
    def sha256(self)->str:
        return digest(self.record())
