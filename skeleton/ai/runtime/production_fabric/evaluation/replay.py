"""Repeat a session replay and compare source-bound digests, not subjective output."""
from ..contracts.canonical import digest
from ..contracts.errors import IntegrityError
from ..persistence.game_store import GameStore

def verify(store: GameStore, stream: str) -> dict:
    first = store.load(stream)
    second = store.load(stream)
    if first != second:
        raise IntegrityError('nondeterministic replay')
    return {'status': 'pass', 'state_sha256': digest(first.as_data()), 'events': first.revision, 'independent_device_validation': False}
