from dataclasses import dataclass
import hashlib
import unicodedata
@dataclass(frozen=True)
class ClaimFingerprint: text_hash:str; scope:str; valid_time:str
@dataclass(frozen=True)
class ClaimCluster: canonical_id:str; originals:tuple[str,...]; fingerprint:ClaimFingerprint
@dataclass(frozen=True)
class ClaimMerge: cluster:ClaimCluster; lineage:tuple[str,...]
def fingerprint(text,scope,valid_time):
 normalized=" ".join(unicodedata.normalize("NFKC",text).casefold().split())
 if not normalized or not scope or not valid_time:raise ValueError("claim fingerprint inputs required")
 return ClaimFingerprint(hashlib.sha256(normalized.encode()).hexdigest(),scope,valid_time)
def merge_claims(items):
 items=tuple(items)
 if not items:raise ValueError("claim merge requires items")
 ids=[x[0] for x in items]
 if len(ids)!=len(set(ids)):raise ValueError("duplicate claim identity")
 fps={x[1] for x in items}
 if len(fps)!=1:raise ValueError("claims with different scope/time cannot merge")
 ids=tuple(x[0] for x in items);return ClaimMerge(ClaimCluster(ids[0],ids,next(iter(fps))),ids)
