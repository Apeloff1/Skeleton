from dataclasses import dataclass
import hashlib,json
@dataclass(frozen=True)
class KnowledgeSnapshot: source_watermark:int; index_version:str; model_version:str; schema_version:str
@dataclass(frozen=True)
class KnowledgeSnapshotDigest: digest:str
@dataclass(frozen=True)
class KnowledgeDiff: newer_source:bool; changed:tuple[str,...]
def digest(s):
 raw=json.dumps(s.__dict__,sort_keys=True,separators=(",",":")).encode();return KnowledgeSnapshotDigest(hashlib.sha256(raw).hexdigest())
def diff(s,current_source):
 return KnowledgeDiff(current_source>s.source_watermark,("source_watermark",) if current_source!=s.source_watermark else ())
def restore_allowed(s,current_source,current_index=None,current_model=None,current_schema=None):
 if current_source>s.source_watermark:return False
 return all(x is None or x==expected for x,expected in ((current_index,s.index_version),(current_model,s.model_version),(current_schema,s.schema_version)))
