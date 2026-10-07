from dataclasses import dataclass

@dataclass(frozen=True)
class StorageTier:
    name: str
    available: bool
    redundancy: int

@dataclass(frozen=True)
class TieringPolicy:
    min_redundancy: int

@dataclass(frozen=True)
class TierMove:
    artifact_id: str
    digest: str
    source: StorageTier
    target: StorageTier
    metadata_digest: str

def admit_move(m, policy):
    if isinstance(policy.min_redundancy, bool) or not isinstance(policy.min_redundancy, int) or policy.min_redundancy <= 0:
        raise ValueError("positive redundancy policy required")
    if not m.artifact_id or m.source == m.target:
        raise ValueError("distinct tier move and artifact identity required")
    if not m.source.available or not m.target.available:
        raise IOError("storage tier unavailable")
    if m.target.redundancy < policy.min_redundancy:
        raise PermissionError("redundancy requirement")
    if not m.digest or not m.metadata_digest:
        raise ValueError("integrity identity required")
    return m
