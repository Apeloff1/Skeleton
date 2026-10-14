"""Proof contract for deletion across canonical and derived stores."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from .data_lifecycle import LifecycleError

_SHA=re.compile(r"^[0-9a-f]{64}$")

def _token(value:str,field:str)->str:
 if not isinstance(value,str) or not value.strip() or value!=value.strip():raise LifecycleError(f"{field} required")
 return value

def _proof_digest(record_id:str,required_stores:tuple[str,...])->str:
 material=json.dumps({"record":record_id,"required":required_stores},sort_keys=True,separators=(",",":")).encode()
 return sha256(material).hexdigest()

@dataclass(frozen=True,slots=True)
class DerivedStore:
 store_id:str;derived_from:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"store_id",_token(self.store_id,"store_id"))
  if not isinstance(self.derived_from,tuple):raise LifecycleError("derived_from must be tuple")
  parents=tuple(_token(x,"derived_from") for x in self.derived_from)
  if len(parents)!=len(set(parents)):raise LifecycleError("derived_from contains duplicate store")
  if self.store_id in parents:raise LifecycleError("self-derived store")
  object.__setattr__(self,"derived_from",tuple(sorted(parents)))

@dataclass(frozen=True,slots=True)
class DeletionProof:
 record_id:str;required_stores:tuple[str,...];deleted_stores:tuple[str,...];topology_digest:str
 def __post_init__(self):
  object.__setattr__(self,"record_id",_token(self.record_id,"record_id"))
  for field in ("required_stores","deleted_stores"):
   raw=getattr(self,field)
   if not isinstance(raw,tuple):raise LifecycleError(f"{field} must be tuple")
   values=tuple(_token(x,field) for x in raw)
   if tuple(sorted(set(values)))!=values:raise LifecycleError(f"{field} must be sorted unique canonical tuple")
  if not self.required_stores:raise LifecycleError("required_stores cannot be empty")
  if not set(self.deleted_stores)<=set(self.required_stores):raise LifecycleError("deleted_stores must be subset of required_stores")
  if not isinstance(self.topology_digest,str) or not _SHA.fullmatch(self.topology_digest):raise LifecycleError("topology_digest must be sha256")
  if self.topology_digest!=_proof_digest(self.record_id,self.required_stores):raise LifecycleError("deletion proof digest mismatch")
 @property
 def complete(self):return self.required_stores==self.deleted_stores

def prove_deletion(*,record_id:str,canonical_store:str,derived_stores:tuple[DerivedStore,...],deleted_stores:tuple[str,...])->DeletionProof:
 record_id=_token(record_id,"record_id");canonical_store=_token(canonical_store,"canonical_store")
 if not isinstance(derived_stores,tuple) or any(not isinstance(x,DerivedStore) for x in derived_stores):raise LifecycleError("derived_stores must be typed tuple")
 if not isinstance(deleted_stores,tuple):raise LifecycleError("deleted_stores must be tuple")
 stores={canonical_store};pending={canonical_store}
 while pending:
  parent=pending.pop()
  for store in derived_stores:
   if parent in store.derived_from and store.store_id not in stores:stores.add(store.store_id);pending.add(store.store_id)
 required=tuple(sorted(stores));deleted=tuple(sorted(set(_token(x,"deleted_store") for x in deleted_stores)))
 unknown=set(deleted)-set(required)
 if unknown:raise LifecycleError("deletion proof contains unknown store")
 return DeletionProof(record_id,required,deleted,_proof_digest(record_id,required))

def require_complete_deletion(proof:DeletionProof)->None:
 if not isinstance(proof,DeletionProof) or not proof.complete:raise LifecycleError("derived deletion incomplete")
