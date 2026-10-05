from dataclasses import dataclass
import hashlib
@dataclass(frozen=True)
class ClaimFingerprint: text_hash:str; scope:str; valid_time:str
@dataclass(frozen=True)
class ClaimCluster: canonical_id:str; originals:tuple[str,...]; fingerprint:ClaimFingerprint
@dataclass(frozen=True)
class ClaimMerge: cluster:ClaimCluster; lineage:tuple[str,...]
def fingerprint(text,scope,valid_time):return ClaimFingerprint(hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest(),scope,valid_time)
def merge_claims(items):
 fps={x[1] for x in items}
 if len(fps)!=1:raise ValueError("claims with different scope/time cannot merge")
 ids=tuple(x[0] for x in items);return ClaimMerge(ClaimCluster(ids[0],ids,next(iter(fps))),ids)
