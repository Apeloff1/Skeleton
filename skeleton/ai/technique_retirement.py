from dataclasses import dataclass


@dataclass(frozen=True)
class Technique:
    technique_id: str
    version: str
    consumers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.technique_id or not self.version:
            raise ValueError("valid technique identity required")
        if (
            len(self.consumers) != len(set(self.consumers))
            or any(not consumer for consumer in self.consumers)
        ):
            raise ValueError("valid technique consumer inventory required")


@dataclass(frozen=True)
class RetirementEvidence:
    reason: str
    replacement: str
    archive: str
    migrated_consumers: frozenset[str]

    def __post_init__(self) -> None:
        if not all((self.reason, self.replacement, self.archive)):
            raise ValueError("retirement evidence incomplete")
        if (
            not isinstance(self.migrated_consumers, frozenset)
            or any(not consumer for consumer in self.migrated_consumers)
        ):
            raise ValueError("valid migrated consumer evidence required")


@dataclass(frozen=True)
class TechniqueRetirement:
    technique: Technique
    evidence: RetirementEvidence
    retired: bool


def retire(
    technique: Technique,
    evidence: RetirementEvidence,
) -> TechniqueRetirement:
    if not isinstance(technique, Technique) or not isinstance(
        evidence, RetirementEvidence
    ):
        raise ValueError("technique and retirement evidence required")
    if evidence.replacement == technique.technique_id:
        raise ValueError("replacement must differ from retired technique")
    if not set(technique.consumers).issubset(evidence.migrated_consumers):
        raise PermissionError("technique still on critical consumer path")
    return TechniqueRetirement(technique, evidence, True)
