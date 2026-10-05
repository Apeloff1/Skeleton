from dataclasses import dataclass
@dataclass(frozen=True)
class StorageTier: name:str; available:bool; redundancy:int
@dataclass(frozen=True)
class TieringPolicy: min_redundancy:int
@dataclass(frozen=True)
class TierMove: artifact_id:str; digest:str; source:StorageTier; target:StorageTier; metadata_digest:str
def admit_move(m,policy):
 if not m.source.available or not m.target.available:raise IOError("storage tier unavailable")
 if m.target.redundancy<policy.min_redundancy:raise PermissionError("redundancy requirement")
 if not m.digest or not m.metadata_digest:raise ValueError("integrity identity required")
 return m
