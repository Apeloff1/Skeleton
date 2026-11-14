"""Model acceptance, candidate creation and user-facing release are distinct."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import refuse


@dataclass(frozen=True,slots=True)
class OperationalBoundaries:
    source_verified:bool
    vocabulary_verified:bool
    native_initialization_done:bool
    sgd_done:bool
    actual_validation_done:bool
    actual_holdout_done:bool
    independent_verifier_approved:bool
    production_install_qualified:bool
    exact_head_ci_green:bool

    def __post_init__(self)->None:
        for item in self.__dataclass_fields__:
            if type(getattr(self,item)) is not bool:
                refuse("boundary-bool")

    def report(self)->dict:
        return {
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "source_ready":self.source_verified and self.vocabulary_verified,
            "candidate_ready":self.source_verified and self.vocabulary_verified
                and self.native_initialization_done and self.sgd_done,
            "independent_quality_ready":self.actual_validation_done
                and self.actual_holdout_done and self.independent_verifier_approved,
            "release_certified":False,
            "automatic_promotion":False,
        }
