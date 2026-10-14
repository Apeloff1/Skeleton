from dataclasses import dataclass
@dataclass(frozen=True)
class StoreHandle: state_class:str; consistency:str; capabilities:tuple[str,...]
@dataclass(frozen=True)
class TransactionHandle: store:StoreHandle; idempotency_key:str; active:bool=True
@dataclass(frozen=True)
class StorageSDK:
 stores:tuple[StoreHandle,...]
 def __post_init__(self):
  keys=[(s.state_class,s.consistency) for s in self.stores]
  if len(keys)!=len(set(keys)) or any(not s.state_class or not s.consistency or len(s.capabilities)!=len(set(s.capabilities)) for s in self.stores):raise ValueError("ambiguous or invalid storage registry")
 def open(self,state_class,consistency):
  x=next((s for s in self.stores if s.state_class==state_class and s.consistency==consistency),None)
  if not x:raise LookupError("no store satisfies declared state/consistency")
  return x
 def transaction(self,store,key):
  if store not in self.stores:raise PermissionError("store is not registered")
  if "transactions" not in store.capabilities or not key:raise ValueError("transaction/idempotency unsupported")
  return TransactionHandle(store,key)
