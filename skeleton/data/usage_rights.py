from dataclasses import dataclass
@dataclass(frozen=True)
class UsageGrant: purpose:str; geography:frozenset[str]; retain_until:int; training:bool
@dataclass(frozen=True)
class DataRights: data_id:str; grants:tuple[UsageGrant,...]; lineage:tuple[str,...]=()
@dataclass(frozen=True)
class RightsDecision: allowed:bool; reason:str
def decide(r,purpose,geo,now,training=False):
 ok=any(g.purpose==purpose and geo in g.geography and now<=g.retain_until and (not training or g.training) for g in r.grants)
 return RightsDecision(ok,"grant matched" if ok else "no compatible grant")
def derive(parent,new_id):return DataRights(new_id,parent.grants,parent.lineage+(parent.data_id,))
