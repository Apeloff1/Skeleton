"""Independent train/evaluation/rollback/release actors with no self-promotion."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_id
from .errors import reject


@dataclass(frozen=True,slots=True)
class RoleAssignments:
    trainer:str
    evaluator:str
    rollback_verifier:str
    release_officer:str

    def __post_init__(self):
        actors=[getattr(self,k) for k in self.__dataclass_fields__]
        for value in actors:
            require_id(value,"authority")
        if len(set(actors))!=4:
            reject("authority-collision")

    def report(self)->dict:
        return {
            **{key:getattr(self,key) for key in self.__dataclass_fields__},
            "independent_actors":True,
            "candidate_only":True,
            "model_activation_granted":False,
        }
