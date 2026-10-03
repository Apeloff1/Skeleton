"""Governed lineage policy: trust/classification/deletion propagation."""
from dataclasses import dataclass
LEVEL={"public":0,"internal":1,"confidential":2,"restricted":3}
class LineageGovernanceError(ValueError): pass
@dataclass(frozen=True, slots=True)
class LineageAsset: asset_id:str; classification:str; trust:str; deleted:bool=False
@dataclass(frozen=True, slots=True)
class TransformationReceipt: transformation_id:str; version:str; environment_digest:str; inputs:tuple[str,...]; outputs:tuple[str,...]; classification:str; trust:str
class GovernedLineage:
    def __init__(self): self._assets={}; self._receipts=[]
    def register(self,a):
        if not a.asset_id or a.classification not in LEVEL or a.trust not in {"trusted","untrusted"}: raise LineageGovernanceError("invalid asset")
        old=self._assets.get(a.asset_id)
        if old is not None and old!=a: raise LineageGovernanceError("asset identity cannot be rebound")
        self._assets[a.asset_id]=a
    def transform(self,*,transformation_id,version,environment_digest,inputs,outputs,classification,trust):
        ins=tuple(dict.fromkeys(inputs)); outs=tuple(dict.fromkeys(outputs))
        if not transformation_id or not version or len(environment_digest)!=64 or not ins or not outs or set(ins)&set(outs): raise LineageGovernanceError("invalid transform")
        src=[]
        for i in ins:
            a=self._assets.get(i)
            if a is None or a.deleted: raise LineageGovernanceError("input unavailable")
            src.append(a)
        inherited=max(src,key=lambda a:LEVEL[a.classification]).classification
        if classification not in LEVEL or LEVEL[classification]<LEVEL[inherited]: raise LineageGovernanceError("classification laundering is forbidden")
        if trust not in {"trusted","untrusted"} or (any(a.trust=="untrusted" for a in src) and trust=="trusted"): raise LineageGovernanceError("trust upgrade is forbidden")
        for o in outs:
            if o in self._assets: raise LineageGovernanceError("output exists")
            self._assets[o]=LineageAsset(o,classification,trust,False)
        r=TransformationReceipt(transformation_id,version,environment_digest,ins,outs,classification,trust); self._receipts.append(r); return r
    def downstream(self,asset_id):
        seen=set(); q=[asset_id]
        while q:
            cur=q.pop()
            for r in self._receipts:
                if cur in r.inputs:
                    for o in r.outputs:
                        if o not in seen: seen.add(o); q.append(o)
        return tuple(sorted(seen))
    def mark_deleted(self,asset_id):
        if asset_id not in self._assets: raise KeyError(asset_id)
        affected=(asset_id,*self.downstream(asset_id))
        for i in affected:
            a=self._assets[i]; self._assets[i]=LineageAsset(a.asset_id,a.classification,a.trust,True)
        return affected
    def asset(self,asset_id): return self._assets[asset_id]
