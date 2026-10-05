"""Proof contract for deletion across canonical and derived stores."""
from dataclasses import dataclass
from hashlib import sha256
import json
from .data_lifecycle import LifecycleError
@dataclass(frozen=True,slots=True)
class DerivedStore:
 store_id:str;derived_from:tuple[str,...]
 def __post_init__(self):
  if not isinstance(self.store_id,str) or not self.store_id:raise LifecycleError("store_id required")
  if not isinstance(self.derived_from,tuple):raise LifecycleError("derived_from must be tuple")
  if self.store_id in self.derived_from:raise LifecycleError("self-derived store")
@dataclass(frozen=True,slots=True)
class DeletionProof:
 record_id:str;required_stores:tuple[str,...];deleted_stores:tuple[str,...];topology_digest:str
 @property
 def complete(self):return self.required_stores==self.deleted_stores
def prove_deletion(*,record_id:str,canonical_store:str,derived_stores:tuple[DerivedStore,...],deleted_stores:tuple[str,...])->DeletionProof:
 stores={canonical_store};pending={canonical_store}
 while pending:
  parent=pending.pop()
  for store in derived_stores:
   if parent in store.derived_from and store.store_id not in stores:stores.add(store.store_id);pending.add(store.store_id)
 required=tuple(sorted(stores));deleted=tuple(sorted(set(deleted_stores)))
 unknown=set(deleted)-set(required)
 if unknown:raise LifecycleError("deletion proof contains unknown store")
 material=json.dumps({"record":record_id,"required":required},sort_keys=True,separators=(",",":")).encode()
 digest=sha256(material).hexdigest()
 return DeletionProof(record_id,required,deleted,digest)
def require_complete_deletion(proof:DeletionProof)->None:
 if not isinstance(proof,DeletionProof) or not proof.complete:raise LifecycleError("derived deletion incomplete")
