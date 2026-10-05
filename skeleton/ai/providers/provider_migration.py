from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderParity:
    capability: bool
    policy: bool
    quality: bool
    cost: bool
    data_boundary: bool

@dataclass(frozen=True)
class ProviderMigration:
    source: str
    target: str
    parity: ProviderParity
    stage: str = "shadow"

@dataclass(frozen=True)
class ProviderCutover:
    source: str
    target: str
    active: str
    rollback: str

def cutover(m):
    if not m.source or not m.target or m.source == m.target or any(not isinstance(x, bool) for x in (m.parity.capability, m.parity.policy, m.parity.quality, m.parity.cost, m.parity.data_boundary)):
        raise ValueError("valid provider migration required")
    if not all((m.parity.capability, m.parity.policy, m.parity.quality, m.parity.cost, m.parity.data_boundary)):
        raise PermissionError("provider parity incomplete")
    if m.stage not in {"shadow", "canary"}:
        raise ValueError("provider must pass staged migration")
    return ProviderCutover(m.source, m.target, m.target, m.source)
