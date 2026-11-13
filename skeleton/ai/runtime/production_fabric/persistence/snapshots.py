"""Verified portable snapshots are projections, not an alternate state authority."""
from ..contracts.canonical import digest
from ..contracts.state import GameState
from ..contracts.errors import IntegrityError

def capture(state: GameState, chain_digest: str) -> dict:
    data = {'schema_version': 1, 'state': state.as_data(), 'stream_digest': chain_digest}
    return {'data': data, 'sha256': digest(data)}

def validate(snapshot: dict, state: GameState, chain_digest: str) -> bool:
    if not isinstance(snapshot, dict) or set(snapshot) != {'data', 'sha256'}:
        raise IntegrityError('invalid snapshot format')
    if snapshot['data'] != {'schema_version': 1, 'state': state.as_data(), 'stream_digest': chain_digest} or digest(snapshot['data']) != snapshot['sha256']:
        raise IntegrityError('snapshot does not match authoritative event stream')
    return True
