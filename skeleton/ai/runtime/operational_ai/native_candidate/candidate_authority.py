"""Separation of train, independent evaluation, admission, and release roles."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import identity
from .errors import deny

ROLES = frozenset({"trainer", "evaluator", "release_authority", "rollback_verifier"})


@dataclass(frozen=True, slots=True)
class AuthorityAssignment:
    trainer_id: str
    evaluator_id: str
    release_authority_id: str
    rollback_verifier_id: str

    def __post_init__(self) -> None:
        values = [self.trainer_id, self.evaluator_id,
                  self.release_authority_id, self.rollback_verifier_id]
        for item in values:
            identity(item, "role-actor")
        if len(set(values)) != 4:
            deny("authority-role-collision")

    def record(self) -> dict:
        return {
            "trainer_id": self.trainer_id,
            "evaluator_id": self.evaluator_id,
            "release_authority_id": self.release_authority_id,
            "rollback_verifier_id": self.rollback_verifier_id,
            "role_isolation": True, "production_authorized": False,
        }
