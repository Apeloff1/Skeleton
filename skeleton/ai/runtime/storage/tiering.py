from dataclasses import dataclass


@dataclass(frozen=True)
class StorageTier:
    name: str
    available: bool
    redundancy: int

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.available, bool):
            raise ValueError("valid storage tier required")
        if (
            isinstance(self.redundancy, bool)
            or not isinstance(self.redundancy, int)
            or self.redundancy < 0
        ):
            raise ValueError("nonnegative storage redundancy required")


@dataclass(frozen=True)
class TieringPolicy:
    min_redundancy: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_redundancy, bool)
            or not isinstance(self.min_redundancy, int)
            or self.min_redundancy <= 0
        ):
            raise ValueError("positive redundancy policy required")


@dataclass(frozen=True)
class TierMove:
    artifact_id: str
    digest: str
    source: StorageTier
    target: StorageTier
    metadata_digest: str

    def __post_init__(self) -> None:
        if (
            not self.artifact_id
            or not self.digest
            or not self.metadata_digest
            or not isinstance(self.source, StorageTier)
            or not isinstance(self.target, StorageTier)
        ):
            raise ValueError("complete tier move identity required")


def admit_move(move: TierMove, policy: TieringPolicy) -> TierMove:
    if not isinstance(move, TierMove) or not isinstance(policy, TieringPolicy):
        raise ValueError("tier move and policy required")
    if move.source == move.target or move.source.name == move.target.name:
        raise ValueError("distinct tier move required")
    if not move.source.available or not move.target.available:
        raise IOError("storage tier unavailable")
    if move.target.redundancy < policy.min_redundancy:
        raise PermissionError("redundancy requirement")
    return move
