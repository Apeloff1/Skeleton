"""Explicit rights ledger: unknown licensing, derivative status or attribution fails closed."""
from dataclasses import dataclass
from ..contracts.errors import AuthorizationError, ContractError

@dataclass(frozen=True)
class AssetRights:
    source: str
    license: str
    original: bool
    redistributable: bool
    reviewed: bool
    attribution: str

def admit(asset: AssetRights, *, redistribution: bool) -> bool:
    if not isinstance(asset, AssetRights) or any((not isinstance(v, str) or not v.strip() for v in (asset.source, asset.license))):
        raise ContractError('asset rights metadata missing')
    if not asset.reviewed or (redistribution and (not asset.redistributable)):
        raise AuthorizationError('unreviewed or nonredistributable asset')
    if not asset.original and (not asset.attribution):
        raise AuthorizationError('nonoriginal asset missing attribution')
    return True
