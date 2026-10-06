from dataclasses import dataclass

@dataclass(frozen=True)
class UsageGrant:
    purpose: str
    geography: frozenset[str]
    retain_until: int
    training: bool

@dataclass(frozen=True)
class DataRights:
    data_id: str
    grants: tuple[UsageGrant, ...]
    lineage: tuple[str, ...] = ()

@dataclass(frozen=True)
class RightsDecision:
    allowed: bool
    reason: str

def decide(r, purpose, geo, now, training=False):
    if not r.data_id or not purpose or not geo or isinstance(now, bool) or not isinstance(now, int) or now < 0 or not isinstance(training, bool):
        return RightsDecision(False, "invalid rights query")
    if any(not g.purpose or not g.geography or isinstance(g.retain_until, bool) or not isinstance(g.retain_until, int) or g.retain_until < 0 or not isinstance(g.training, bool) for g in r.grants):
        return RightsDecision(False, "invalid grant")
    ok = any(g.purpose == purpose and geo in g.geography and now <= g.retain_until and (not training or g.training) for g in r.grants)
    return RightsDecision(ok, "grant matched" if ok else "no compatible grant")

def derive(parent, new_id):
    if not new_id or new_id == parent.data_id or new_id in parent.lineage:
        raise ValueError("derived data requires new lineage identity")
    return DataRights(new_id, parent.grants, parent.lineage + (parent.data_id,))
