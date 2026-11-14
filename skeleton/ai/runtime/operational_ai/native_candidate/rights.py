"""Prove training rights and feed existing FLGB governance contracts."""
from __future__ import annotations
from dataclasses import dataclass

from skeleton.ai.training.flgb_training_runtime import DatasetRights
from .records import TrainingExample, SCOPE
from .strict import digest
from .errors import deny


@dataclass(frozen=True, slots=True)
class RightsProof:
    dataset_id: str
    records: int
    source_hash: str
    rights_digest: str
    allowed_scope: str
    license_id: str

    def record(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def verify_rights(examples: tuple[TrainingExample, ...]) -> RightsProof:
    if not examples or len(examples) > 576:
        deny("rights-inventory")
    for example in examples:
        if type(example) is not TrainingExample or example.rights_status != "allowed":
            deny("rights-denied")
        if example.training_scope != SCOPE or example.license_id != "skeleton_original":
            deny("rights-scope")
    ids = [e.item_id for e in examples]
    if len(set(ids)) != len(ids):
        deny("rights-duplicate")
    source_hash = digest([e.record() for e in examples])
    dataset_id = "skeleton_original_" + source_hash[:24]
    rights = DatasetRights(dataset_id, "skeleton_authored_v1", "allowed",
                           "skeleton_original", (SCOPE,), digest(
                               {"owner": "skeleton", "scope": SCOPE,
                                "source_hash": source_hash, "count": len(examples)}
                           ))
    if not rights.permits(SCOPE):
        deny("rights-not-permitted")
    return RightsProof(dataset_id, len(examples), source_hash, rights.digest,
                       SCOPE, rights.license_id)
