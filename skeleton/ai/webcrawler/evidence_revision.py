"""Auditable receipts for retroactive evidence-set revisions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
@dataclass(frozen=True)
class RevisionReceipt:
 revision_id:str;query:str;previous_digest:str;current_digest:str
 added:tuple[str,...];removed:tuple[str,...];reason:str;recorded_at:float
def _digest(ids):return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
def revision_receipt(query,previous_ids,current_ids,*,reason,recorded_at):
 prev=set(previous_ids);cur=set(current_ids)
 payload={"query":query,"previous":_digest(prev),"current":_digest(cur),"added":sorted(cur-prev),"removed":sorted(prev-cur),"reason":reason,"recorded_at":float(recorded_at)}
 rid=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return RevisionReceipt(rid,query,payload["previous"],payload["current"],tuple(payload["added"]),tuple(payload["removed"]),reason,float(recorded_at))
